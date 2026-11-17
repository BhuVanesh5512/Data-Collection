"""Create analysis-ready features, coverage summaries and evidence-based insights."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("data/processed")
SOURCE = BASE / "global_bank_interest_rates.csv"
VERIFY = BASE / "source_verification_summary.json"
FEATURES = BASE / "analysis_ready_rates.csv"
COUNTRY_SUMMARY = BASE / "country_series_summary.csv"
MONTHLY_SUMMARY = BASE / "monthly_cross_section_summary.csv"
QUALITY = BASE / "data_quality_report.json"
INSIGHTS = BASE / "analysis_insights.md"

REQUIRED = {
    "country", "entity_type", "bank_name", "authority_name", "observation_date",
    "year", "month", "interest_rate", "is_estimated", "rate_type", "rate_name",
    "frequency", "source_name", "series_code", "reference_period",
    "collection_window_start",
}


def main():
    if not SOURCE.exists() or not VERIFY.exists():
        raise FileNotFoundError("Official CSV and source-verification summary are required.")
    df = pd.read_csv(SOURCE)
    verification = json.loads(VERIFY.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED - set(df.columns))
    if missing:
        raise RuntimeError(f"Dataset is missing required columns: {missing}")
    if not verification.get("verification_passed"):
        raise RuntimeError("Independent source verification did not pass; analysis stopped.")
    if int(verification.get("matched_values", -1)) != len(df):
        raise RuntimeError("Verification matched-value count does not equal dataset rows.")
    if int(verification.get("value_mismatches", -1)) or int(verification.get("duplicate_dataset_keys", -1)):
        raise RuntimeError("Verification reports mismatches or duplicate keys.")
    if df["is_estimated"].astype(str).str.lower().isin(["true", "1", "yes"]).any():
        raise RuntimeError("Estimated rows are not allowed in the official dataset.")
    if df[["country", "bank_name", "authority_name", "series_code"]].isna().any().any():
        raise RuntimeError("Missing country, authority or series identity.")
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="raise")
    df["interest_rate"] = pd.to_numeric(df["interest_rate"], errors="raise")
    df["period"] = pd.PeriodIndex(df["reference_period"].astype(str), freq="M")
    if df.duplicated(["series_code", "reference_period"]).any():
        raise RuntimeError("Duplicate series/month observations detected.")

    BASE.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["series_code", "period"]).copy()
    df["previous_period"] = df.groupby("series_code")["period"].shift(1).astype("string")
    df["previous_rate"] = df.groupby("series_code")["interest_rate"].shift(1)
    period_ord = df["period"].astype("int64")
    previous_ord = period_ord.groupby(df["series_code"]).shift(1)
    consecutive = (period_ord - previous_ord).eq(1).fillna(False)
    df["change_from_previous_observation_pp"] = df["interest_rate"] - df["previous_rate"]
    df["change_from_previous_month_pp"] = df["change_from_previous_observation_pp"].where(consecutive)
    df["is_consecutive_month_change"] = consecutive
    df["rolling_12m_mean"] = np.nan
    df["rolling_12m_std"] = np.nan
    for _, idx in df.groupby("series_code").groups.items():
        sub = df.loc[idx].sort_values("period")
        vals = sub["interest_rate"].astype(float).to_numpy()
        ords = sub["period"].astype("int64").to_numpy()
        means = np.full(len(sub), np.nan)
        stds = np.full(len(sub), np.nan)
        for pos in range(11, len(sub)):
            if ords[pos] - ords[pos - 11] == 11:
                window = vals[pos - 11:pos + 1]
                means[pos] = float(np.mean(window))
                stds[pos] = float(np.std(window, ddof=1))
        df.loc[sub.index, "rolling_12m_mean"] = means
        df.loc[sub.index, "rolling_12m_std"] = stds
    latest_by_series = df.groupby("series_code")["period"].transform("max")
    df["is_latest_observation_for_series"] = df["period"].eq(latest_by_series)
    df["is_latest_global_month"] = df["period"].eq(df["period"].max())
    df["high_rate_review_flag"] = df["interest_rate"].gt(50)
    df["large_monthly_change_review_flag"] = df["change_from_previous_month_pp"].abs().gt(5)
    df.drop(columns=["period"], inplace=True)
    df.to_csv(FEATURES, index=False)

    raw = pd.read_csv(SOURCE)
    raw["period"] = pd.PeriodIndex(raw["reference_period"].astype(str), freq="M")
    first_period, last_period = raw["period"].min(), raw["period"].max()
    expected_months = last_period.ordinal - first_period.ordinal + 1
    keys = ["country", "entity_type", "iso3", "series_code", "rate_name", "authority_name", "bank_name"]
    summary_rows = []
    for key, group in raw.groupby(keys, dropna=False):
        group = group.sort_values("reference_period")
        periods = pd.PeriodIndex(group["reference_period"].astype(str), freq="M")
        n_periods = periods.nunique()
        latest = periods.max()
        latest_rate = float(group.iloc[-1]["interest_rate"])
        first_rate = float(group.iloc[0]["interest_rate"])
        missing_months = expected_months - n_periods
        lag_months = last_period.ordinal - latest.ordinal
        summary_rows.append(dict(zip(keys, key)) | {
            "observations": int(len(group)),
            "first_period": str(periods.min()),
            "latest_period": str(latest),
            "first_rate_pct": first_rate,
            "latest_rate_pct": latest_rate,
            "change_since_first_observation_pp": latest_rate - first_rate,
            "mean_rate_pct": float(group["interest_rate"].mean()),
            "median_rate_pct": float(group["interest_rate"].median()),
            "minimum_rate_pct": float(group["interest_rate"].min()),
            "maximum_rate_pct": float(group["interest_rate"].max()),
            "standard_deviation_pp": float(group["interest_rate"].std()) if len(group) > 1 else None,
            "expected_months_in_dataset_window": int(expected_months),
            "observed_months": int(n_periods),
            "missing_months_in_window": int(missing_months),
            "coverage_pct": round(n_periods / expected_months * 100, 2),
            "months_behind_latest_dataset_period": int(lag_months),
            "coverage_status": "complete" if missing_months == 0 else ("stale_or_incomplete" if lag_months > 1 else "recent_gaps"),
        })
    country = pd.DataFrame(summary_rows).sort_values(["entity_type", "country"])
    country.to_csv(COUNTRY_SUMMARY, index=False)

    monthly = raw.groupby("period").agg(
        observations=("interest_rate", "size"),
        entities_reporting=("country", "nunique"),
        cross_sectional_median_pct=("interest_rate", "median"),
        cross_sectional_mean_pct=("interest_rate", "mean"),
        cross_sectional_q1_pct=("interest_rate", lambda x: x.quantile(.25)),
        cross_sectional_q3_pct=("interest_rate", lambda x: x.quantile(.75)),
        cross_sectional_min_pct=("interest_rate", "min"),
        cross_sectional_max_pct=("interest_rate", "max"),
    ).reset_index()
    monthly["period"] = monthly["period"].astype(str)
    complete_codes = set(country.loc[country["coverage_status"] == "complete", "series_code"])
    balanced = raw[raw["series_code"].isin(complete_codes)]
    balanced_monthly = balanced.groupby("period")["interest_rate"].agg(["median", "count"])
    monthly["balanced_panel_median_pct"] = monthly["period"].map(
        {str(k): float(v) for k, v in balanced_monthly["median"].items()}
    )
    monthly["balanced_panel_entities"] = monthly["period"].map(
        {str(k): int(v) for k, v in balanced_monthly["count"].items()}
    )
    monthly["interpretation_note"] = "Unbalanced cross-section uses available observations; balanced panel includes only series with full window coverage. Neither is a weighted global policy rate."
    monthly.to_csv(MONTHLY_SUMMARY, index=False)

    latest_rows = raw.sort_values("period").groupby("series_code").tail(1)
    country_entities = raw.loc[raw["entity_type"].eq("country"), "iso3"].nunique()
    region_entities = raw.loc[raw["entity_type"].eq("region"), "country"].nunique()
    full_coverage = int((country["coverage_status"] == "complete").sum())
    high_values = raw.loc[raw["interest_rate"] > 50, ["country", "reference_period", "interest_rate", "series_code"]]
    negative_values = int((raw["interest_rate"] < 0).sum())
    quality = {
        "verification_passed": True,
        "verified_rows": int(len(raw)),
        "matched_values": int(verification["matched_values"]),
        "value_mismatches": int(verification["value_mismatches"]),
        "duplicate_series_months": int(raw.duplicated(["series_code", "reference_period"]).sum()),
        "estimated_rows": int(raw["is_estimated"].astype(str).str.lower().isin(["true", "1", "yes"]).sum()),
        "countries_with_iso3": int(country_entities),
        "regional_entities_without_iso3": int(region_entities),
        "authority_count": int(raw["authority_name"].nunique()),
        "rate_types": sorted(raw["rate_type"].dropna().unique().tolist()),
        "rate_names": sorted(raw["rate_name"].dropna().unique().tolist()),
        "frequencies": sorted(raw["frequency"].dropna().unique().tolist()),
        "sources": sorted(raw["source_name"].dropna().unique().tolist()),
        "first_month": str(first_period),
        "last_month": str(last_period),
        "expected_months": int(expected_months),
        "series_with_complete_monthly_coverage": full_coverage,
        "series_count": int(len(country)),
        "negative_rate_observations": negative_values,
        "rates_above_50_review_count": int(len(high_values)),
        "rbi_observations_in_dataset": int(raw["source_name"].astype(str).str.contains("Reserve Bank of India").sum()),
        "rbi_observations_available_to_verifier": int(verification.get("rbi_policy_observations_available_for_verification", 0)),
        "coverage_exceptions": country.loc[country["coverage_status"] != "complete", ["country", "latest_period", "observations", "coverage_pct", "months_behind_latest_dataset_period"]].to_dict("records"),
        "high_rate_review_records": high_values.to_dict("records"),
        "latest_rates_by_series": latest_rows[["country", "entity_type", "reference_period", "interest_rate", "rate_name", "authority_name"]].to_dict("records"),
    }
    QUALITY.write_text(json.dumps(quality, indent=2, default=str), encoding="utf-8")

    latest_global = latest_rows.sort_values("interest_rate", ascending=False)
    complete = country[country["coverage_status"] == "complete"].sort_values("change_since_first_observation_pp")
    top_rise = complete.tail(5).sort_values("change_since_first_observation_pp", ascending=False)
    top_fall = complete.head(5)
    exceptions = country[country["coverage_status"] != "complete"].sort_values("coverage_pct")
    lines = [
        "# Dataset analysis and insights",
        "",
        "## Dataset scope",
        f"- {len(raw):,} verified, official observations across {country_entities} ISO3-coded countries and {region_entities} regional entity/entities.",
        f"- Coverage: {first_period} to {last_period} ({expected_months} monthly periods).",
        f"- Rate family: {', '.join(quality['rate_types'])}; instruments: {', '.join(quality['rate_names'])}.",
        f"- Frequency: {', '.join(quality['frequencies'])}; source: {', '.join(quality['sources'])}.",
        "- This extract is a policy-rate dataset. It does not contain commercial-bank loan/deposit rates.",
        "- bank_name is an authority label in this dataset, not a commercial bank name.",
        "",
        "## Key insights",
        f"- The unbalanced cross-sectional median was {monthly.iloc[0]['cross_sectional_median_pct']:.2f}% in {monthly.iloc[0]['period']} and {monthly.iloc[-1]['cross_sectional_median_pct']:.2f}% in {monthly.iloc[-1]['period']}; reporting coverage changes over time.",
        f"- In the balanced panel of {full_coverage} complete series, the median was {monthly.iloc[0]['balanced_panel_median_pct']:.2f}% at the start and {monthly.iloc[-1]['balanced_panel_median_pct']:.2f}% at the end. This compares the same set of series across months.",
        f"- {full_coverage} of {len(country)} authority series have observations in every month of the dataset window.",
        f"- {negative_values} observations are negative. Negative policy rates are retained as published, not treated as missing or errors.",
        f"- {len(high_values)} observations exceed 50%; these are flagged for contextual review, not automatically rejected.",
        "",
        "### Highest latest published observations",
    ]
    for _, row in latest_global.head(5).iterrows():
        lines.append(f"- {row['country']} — {row['interest_rate']:.3f}% ({row['reference_period']}); {row['authority_name']}.")
    lines += ["", "### Largest increases among fully covered series"]
    for _, row in top_rise.iterrows():
        lines.append(f"- {row['country']}: {row['change_since_first_observation_pp']:+.2f} percentage points from {row['first_rate_pct']:.3f}% to {row['latest_rate_pct']:.3f}%.")
    lines += ["", "### Largest decreases among fully covered series"]
    for _, row in top_fall.iterrows():
        lines.append(f"- {row['country']}: {row['change_since_first_observation_pp']:+.2f} percentage points from {row['first_rate_pct']:.3f}% to {row['latest_rate_pct']:.3f}%.")
    lines += ["", "### Coverage exceptions"]
    if exceptions.empty:
        lines.append("- None.")
    else:
        for _, row in exceptions.iterrows():
            lines.append(f"- {row['country']}: {row['observations']} observations, {row['coverage_pct']:.1f}% coverage, latest {row['latest_period']}.")
    lines += [
        "",
        "## Interpretation cautions",
        "- Policy-rate instruments differ across jurisdictions; use rate_name and series_code before comparing.",
        "- The cross-sectional mean can be distorted by high-inflation economies; median and country-level trends are often more robust.",
        "- The latest observation is not necessarily the same month for every entity. Always use latest_period and coverage fields.",
        "- A value can match the source and still be stale or incomplete. Verification and coverage are separate quality dimensions.",
        "- A policy rate is not a commercial lending rate, deposit rate, mortgage rate or bank-specific customer rate.",
        "",
        "## Generated analysis files",
        "- analysis_ready_rates.csv: source rows plus month-on-month changes, 12-month rolling statistics and review flags.",
        "- country_series_summary.csv: per-country/region coverage, latest rate, range and first-to-latest change.",
        "- monthly_cross_section_summary.csv: monthly cross-sectional distribution.",
        "- data_quality_report.json: verification, coverage exceptions and records requiring review.",
        "",
    ]
    INSIGHTS.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "analysis_rows": int(len(raw)), "series": int(len(country)),
        "countries": int(country_entities), "regions": int(region_entities),
        "features": str(FEATURES), "country_summary": str(COUNTRY_SUMMARY),
        "monthly_summary": str(MONTHLY_SUMMARY), "quality_report": str(QUALITY),
        "insights": str(INSIGHTS),
    }, indent=2))


if __name__ == "__main__":
    main()
