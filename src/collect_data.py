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
    country = pycountry.countries.get(alpha_2=code)
    if country:
        return country.name, country.alpha_3
    return code, None


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
        year = str(x["date"])
        period = f"{year}-01-01"
        if START <= period <= END:
            country_name, iso2 = country_from_iso3(iso3)
            rows.append({
                "country": x["country"]["value"],
                "country_code": iso2,
                "iso3": iso3,
                "observation_date": period,
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
                "rate_definition": "As defined in World Bank indicator metadata",
                "methodology_notes": "Annual source observation; not interpolated or expanded.",
            })
    return pd.DataFrame(rows)


def bis_policy():
    # Monthly frequency across all BIS reference areas. The key dimensions are
    # FREQ.REF_AREA; M. selects monthly observations for every reference area.
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
        dt = pd.to_datetime(period, format="%Y-%m", errors="coerce")
        value = pd.to_numeric(x[vc], errors="coerce")
        if pd.isna(dt) or pd.isna(value):
            continue
        if dt < pd.Timestamp(START).replace(day=1) or dt > pd.Timestamp(END).replace(day=1):
            continue

        iso2 = str(x[cc]).strip().upper()
        country_name, iso3 = country_from_iso2(iso2)
        rows.append({
            "country": country_name,
            "country_code": iso2,
            "iso3": iso3,
            "observation_date": dt.strftime("%Y-%m-01"),
            "year": int(dt.year),
            "month": int(dt.month),
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
            "reference_period": dt.strftime("%Y-%m"),
            "rate_definition": "BIS selected policy rate for main policy instrument",
            "methodology_notes": "BIS monthly observation; month-end value derived by BIS from daily data. See BIS series metadata for country-specific definitions.",
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
    df = df.drop_duplicates(
        ["iso3", "observation_date", "rate_type", "series_code"], keep="last"
    )
    df = df.sort_values(["country", "rate_type", "observation_date"])
    df["observation_date"] = df["observation_date"].dt.strftime("%Y-%m-%d")
    df["month"] = df["month"].astype("Int64")
    df.insert(0, "observation_id", range(1, len(df) + 1))
    df.to_csv(OUT, index=False, encoding="utf-8")

    country_count = df["iso3"].dropna().nunique()
    print(f"Rows: {len(df):,}; ISO3 countries: {country_count:,}")
    print(df.groupby(["rate_type", "frequency"], dropna=False).size().to_string())
    print("India rows:", int((df["iso3"] == "IND").sum()))
    if df["iso3"].eq("IND").sum() == 0:
        raise RuntimeError("India is missing from BIS policy-rate output; verify BIS API response.")
    if len(df) < 1000:
        print("NOTICE: Fewer than 1,000 real rows; no synthetic rows added.")
    if country_count < 100:
        print("NOTICE: Fewer than 100 countries; broaden official sources.")


if __name__ == "__main__":
    main()
