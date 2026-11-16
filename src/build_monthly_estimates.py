"""Build a separate, explicitly estimated monthly panel from annual WDI rates.

This never changes the official-observation CSV. It interpolates only between
published annual observations and never extrapolates beyond available anchors.
"""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE = Path("data/processed/global_bank_interest_rates.csv")
OUTPUT = Path("data/processed/global_bank_interest_rates_monthly_estimates.csv")


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    data = pd.read_csv(SOURCE)
    required = {
        "country", "iso3", "rate_type", "series_code", "frequency",
        "year", "interest_rate", "source_url",
    }
    missing = required - set(data.columns)
    if missing:
        raise RuntimeError(f"Source CSV is missing columns: {sorted(missing)}")

    annual = data[
        data["frequency"].eq("annual")
        & data["rate_type"].isin(["deposit", "lending"])
    ].copy()
    annual["year"] = pd.to_numeric(annual["year"], errors="coerce")
    annual["interest_rate"] = pd.to_numeric(annual["interest_rate"], errors="coerce")
    annual = annual.dropna(subset=["iso3", "year", "interest_rate"])

    output_rows = []
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    group_cols = ["iso3", "rate_type", "series_code"]

    for _, group in annual.groupby(group_cols, dropna=False):
        group = group.sort_values("year").drop_duplicates("year")
        records = list(group.to_dict("records"))
        if len(records) < 2:
            continue

        for left, right in zip(records, records[1:]):
            y0, y1 = int(left["year"]), int(right["year"])
            if y1 <= y0:
                continue

            # WDI annual rates are annual observations. Use mid-year anchor
            # dates and interpolate only within the two published anchors.
            t0 = pd.Timestamp(year=y0, month=7, day=1)
            t1 = pd.Timestamp(year=y1, month=7, day=1)
            v0, v1 = float(left["interest_rate"]), float(right["interest_rate"])

            month = t0.to_period("M") + 1
            while month < t1.to_period("M"):
                month_start = month.to_timestamp()
                month_midpoint = month_start + pd.Timedelta(days=14)
                weight = (month_midpoint - t0).total_seconds() / (t1 - t0).total_seconds()
                if 0 < weight < 1:
                    estimated_value = v0 + (v1 - v0) * weight
                    row = dict(left)
                    row.update({
                        "observation_id": None,
                        "observation_date": month_start.strftime("%Y-%m-%d"),
                        "year": int(month_start.year),
                        "month": int(month_start.month),
                        "interest_rate": float(estimated_value),
                        "frequency": "monthly",
                        "original_frequency": "annual",
                        "reference_period": month_start.strftime("%Y-%m"),
                        "source_name": "Derived estimate from World Bank WDI annual observations",
                        "source_retrieved_at": generated_at,
                        "is_estimated": True,
                        "estimation_method": "Linear interpolation between annual mid-year anchors",
                        "anchor_start_year": y0,
                        "anchor_end_year": y1,
                        "anchor_start_value": v0,
                        "anchor_end_value": v1,
                        "methodology_notes": (
                            "ESTIMATED, NOT AN OFFICIAL MONTHLY OBSERVATION. "
                            "Linear interpolation between published annual WDI values "
                            f"anchored at 1 July {y0} and 1 July {y1}. "
                            "No extrapolation is performed."
                        ),
                    })
                    output_rows.append(row)
                month += 1

    estimates = pd.DataFrame(output_rows)
    if estimates.empty:
        estimates = pd.DataFrame(columns=list(data.columns) + [
            "is_estimated", "estimation_method", "anchor_start_year",
            "anchor_end_year", "anchor_start_value", "anchor_end_value",
        ])
    else:
        estimates = estimates.sort_values(
            ["country", "rate_type", "observation_date", "series_code"]
        ).reset_index(drop=True)
        estimates["observation_id"] = range(1, len(estimates) + 1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    estimates.to_csv(OUTPUT, index=False, encoding="utf-8")
    print(f"Estimated monthly rows: {len(estimates):,}")
    print(f"Countries: {estimates['iso3'].nunique() if not estimates.empty else 0:,}")
    print(f"Output: {OUTPUT}")
    print("Official source CSV was not modified.")


if __name__ == "__main__":
    main()
