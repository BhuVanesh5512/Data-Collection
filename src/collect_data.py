import os
from datetime import date, datetime, timezone
from pathlib import Path
import io

import pandas as pd
import pycountry
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

START = os.getenv("START_DATE", "2023-12-01")
END = os.getenv("END_DATE", date.today().isoformat())
OUT = Path("data/processed/global_bank_interest_rates.csv")
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

S = requests.Session()
S.headers["User-Agent"] = "Data-Collection-research/1.0"
retry = Retry(
    total=6, connect=6, read=6, status=6,
    backoff_factor=2,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    respect_retry_after_header=True,
)
adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
S.mount("https://", adapter)
S.mount("http://", adapter)
REQUEST_TIMEOUT = (20, 240)


def country_from_iso2(code):
    code = str(code).strip().upper()
    if code == "XM":
        return "Euro area", None
    country = pycountry.countries.get(alpha_2=code)
    if country:
        return country.name, country.alpha_3
    raise RuntimeError(f"Unrecognized BIS reference area code: {code}")


def country_from_iso3(code):
    code = str(code).strip().upper()
    country = pycountry.countries.get(alpha_3=code)
    if country:
        return country.name, country.alpha_2
    return None, None


def world_bank(indicator, rate_type):
    url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
    observations, page = [], 1
    while True:
        r = S.get(
            url,
            params={
                "date": f"{START[:4]}:{END[:4]}",
                "format": "json",
                "per_page": 2000,
                "page": page,
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            break
        meta, batch = payload
        observations.extend(batch)
        if page >= int(meta.get("pages", 1)):
            break
        page += 1

    rows = []
    for x in observations:
        iso3 = str(x.get("countryiso3code", "")).strip().upper()
        if x.get("value") is None or len(iso3) != 3:
            continue

        source_country_name = x["country"]["value"]
        canonical_name, iso2 = country_from_iso3(iso3)
        if not canonical_name or not iso2:
            raise RuntimeError(
                f"Could not map World Bank country to ISO-2/ISO-3: "
                f"{source_country_name} / {iso3}"
            )

        year = str(x["date"])
        period_start = f"{year}-01-01"
        if START <= period_start <= END:
            rows.append({
                "country": canonical_name,
                "source_country_name": source_country_name,
                "entity_type": "country",
                "country_code": iso2,
                "iso3": iso3,
                "observation_date": period_start,
                "year": int(year),
                "month": None,
                "interest_rate": float(x["value"]),
                "rate_type": rate_type,
                "frequency": "annual",
                "source_name": "World Bank World Development Indicators",
                "source_url": f"https://data.worldbank.org/indicator/{indicator}",
                "series_code": indicator,
                "series_name": x["indicator"]["value"],
                "units": "percent",
                "source_retrieved_at": NOW,
                "original_frequency": "annual",
                "reference_period": year,
                "rate_definition": (
                    f"World Bank WDI indicator {indicator}: "
                    f"{x['indicator']['value']}; see linked indicator metadata."
                ),
                "methodology_notes": (
                    "Annual source observation; not interpolated or expanded. "
                    "observation_date is the period label start (1 January)."
                ),
            })
    return pd.DataFrame(rows)


def bis_policy():
    # BIS monthly observations are end-of-period values.
    url = "https://stats.bis.org/api/v1/data/WS_CBPOL/M."
    r = S.get(
        url,
        params={"startPeriod": START[:7], "endPeriod": END[:7], "format": "csvfile"},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    raw = pd.read_csv(io.BytesIO(r.content))
    raw.columns = [str(c).strip() for c in raw.columns]

    def find(*names):
        wanted = {n.lower() for n in names}
        return next((c for c in raw.columns if c.lower() in wanted), None)

    tc = find("TIME_PERIOD")
    vc = find("OBS_VALUE")
    cc = find("REF_AREA")
    fc = find("FREQ")
    title_col = find("TITLE")
    if not all([tc, vc, cc, fc]):
        raise RuntimeError("Unexpected BIS CSV schema: " + str(list(raw.columns)))

    rows = []
    for _, x in raw.iterrows():
        period = str(x[tc]).strip()
        period_start = pd.to_datetime(period, format="%Y-%m", errors="coerce")
        value = pd.to_numeric(x[vc], errors="coerce")
        if pd.isna(period_start) or pd.isna(value):
            continue

        period_end = period_start + pd.offsets.MonthEnd(0)
        if period_start < pd.Timestamp(START).replace(day=1) or period_end > pd.Timestamp(END):
            continue

        iso2 = str(x[cc]).strip().upper()
        country_name, iso3 = country_from_iso2(iso2)
        is_country = iso3 is not None
        rows.append({
            "country": country_name,
            "source_country_name": country_name,
            "entity_type": "country" if is_country else "region",
            "country_code": iso2 if is_country else None,
            "iso3": iso3,
            "observation_date": period_start.strftime("%Y-%m-01"),
            "year": int(period_start.year),
            "month": int(period_start.month),
            "interest_rate": float(value),
            "rate_type": "policy",
            "frequency": "monthly",
            "source_name": "Bank for International Settlements",
            "source_url": "https://data.bis.org/topics/CBPOL",
            "series_code": f"WS_CBPOL:M.{iso2}",
            "series_name": str(x[title_col]) if title_col else f"Central bank policy rate - {country_name}",
            "units": "percent per year",
            "source_retrieved_at": NOW,
            "original_frequency": "monthly",
            "reference_period": period_start.strftime("%Y-%m"),
            "rate_definition": "BIS selected policy rate for main policy instrument",
            "methodology_notes": (
                "BIS monthly end-of-period observation. observation_date is the "
                "period label start (1st of month); reference_period identifies "
                "the month. See BIS metadata for country-specific definitions."
            ),
        })

    if not rows:
        raise RuntimeError("BIS returned no monthly policy-rate rows; inspect API response/schema.")
    return pd.DataFrame(rows)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [
        world_bank("FR.INR.LEND", "lending"),
        world_bank("FR.INR.DPST", "deposit"),
        bis_policy(),
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        raise RuntimeError("No official observations collected.")

    df = pd.concat(frames, ignore_index=True)
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df["interest_rate"] = pd.to_numeric(df["interest_rate"], errors="coerce")
    df = df.dropna(subset=["country", "observation_date", "interest_rate", "rate_type"])
    df = df[
        (df.observation_date >= pd.Timestamp(START))
        & (df.observation_date <= pd.Timestamp(END))
    ]

    # Use ISO-3 for countries and the BIS reference-area code for non-country areas.
    df["geography_key"] = df["iso3"].fillna(df["series_code"].str.rsplit(".", n=1).str[-1])
    duplicate_key = ["geography_key", "observation_date", "rate_type", "series_code"]
    duplicate_count = int(df.duplicated(duplicate_key).sum())
    if duplicate_count:
        raise RuntimeError(f"Duplicate logical observations detected: {duplicate_count}")

    # Country names are canonicalized across source systems; source labels remain preserved.
    df = df.sort_values(["country", "rate_type", "observation_date"])
    df["observation_date"] = df["observation_date"].dt.strftime("%Y-%m-%d")
    df["month"] = df["month"].astype("Int64")
    df = df.drop(columns=["geography_key"])
    df.insert(0, "observation_id", range(1, len(df) + 1))
    df.to_csv(OUT, index=False, encoding="utf-8")

    country_count = df.loc[df["entity_type"] == "country", "iso3"].nunique()
    india_rows = int((df["iso3"] == "IND").sum())
    print(f"Rows: {len(df):,}; ISO3 countries: {country_count:,}")
    print(df.groupby(["entity_type", "rate_type", "frequency"], dropna=False).size().to_string())
    print(f"India rows: {india_rows}")

    required = ["country", "entity_type", "observation_date", "year", "interest_rate",
                "rate_type", "frequency", "source_name", "source_url", "series_code",
                "source_retrieved_at"]
    missing_required = [c for c in required if c not in df.columns or df[c].isna().any()]
    if missing_required:
        raise RuntimeError(f"Missing required fields or values: {missing_required}")
    country_rows = df["entity_type"] == "country"
    if df.loc[country_rows, ["country_code", "iso3"]].isna().any().any():
        raise RuntimeError("Country observations must have both ISO-2 and ISO-3 codes.")
    region_rows = df["entity_type"] == "region"
    if df.loc[region_rows, "iso3"].notna().any():
        raise RuntimeError("Regional aggregates must not be assigned country ISO-3 codes.")
    if df.loc[df["frequency"] == "monthly", "month"].isna().any():
        raise RuntimeError("Monthly observations have missing month values.")
    if df.loc[df["frequency"] == "annual", "month"].notna().any():
        raise RuntimeError("Annual observations unexpectedly have month values.")
    if india_rows == 0:
        raise RuntimeError("India is missing from BIS policy-rate output; verify BIS API response.")
    if len(df) < 1000:
        print("NOTICE: Fewer than 1,000 real rows; no synthetic rows added.")
    if country_count < 100:
        print("NOTICE: Fewer than 100 countries; broaden official sources.")


if __name__ == "__main__":
    main()
