"""Independently re-fetch official BIS and World Bank observations and audit every CSV rate."""
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
import io

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

START = os.getenv("START_DATE", "2023-12-01")
END = os.getenv("END_DATE", date.today().isoformat())
DATA_PATH = Path("data/processed/global_bank_interest_rates.csv")
AUDIT_PATH = Path("data/processed/source_verification.csv")
SUMMARY_PATH = Path("data/processed/source_verification_summary.json")

session = requests.Session()
session.headers["User-Agent"] = "Data-Collection-source-verification/1.0"
retry = Retry(
    total=6, connect=6, read=6, status=6, backoff_factor=2,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    respect_retry_after_header=True,
)
adapter = HTTPAdapter(max_retries=retry)
session.mount("https://", adapter)
session.mount("http://", adapter)
TIMEOUT = (20, 240)


def fetch_world_bank(indicator):
    url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
    observations = []
    # Match the collector's smaller year-scoped requests to avoid large-response timeouts.
    for year in range(int(START[:4]), int(END[:4]) + 1):
        page = 1
        while True:
            response = session.get(
                url,
                params={
                    "date": str(year),
                    "format": "json",
                    "per_page": 1000,
                    "page": page,
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
                break
            metadata, batch = payload
            observations.extend(batch)
            if page >= int(metadata.get("pages", 1)):
                break
            page += 1

    expected = {}
    for item in observations:
        iso3 = str(item.get("countryiso3code", "")).strip().upper()
        value = item.get("value")
        if len(iso3) != 3 or value is None:
            continue
        year = int(item["date"])
        if int(START[:4]) <= year <= int(END[:4]):
            key = (iso3, year, indicator)
            expected[key] = float(value)
    return expected


def fetch_bis():
    url = "https://stats.bis.org/api/v1/data/WS_CBPOL/M."
    response = session.get(
        url,
        params={"startPeriod": START[:7], "endPeriod": END[:7], "format": "csvfile"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    raw = pd.read_csv(io.BytesIO(response.content))
    raw.columns = [str(column).strip() for column in raw.columns]
    required = {"TIME_PERIOD", "OBS_VALUE", "REF_AREA"}
    if not required.issubset(set(raw.columns)):
        raise RuntimeError(f"Unexpected BIS schema; columns={list(raw.columns)}")

    expected = {}
    for _, item in raw.iterrows():
        period = str(item["TIME_PERIOD"]).strip()
        period_start = pd.to_datetime(period, format="%Y-%m", errors="coerce")
        value = pd.to_numeric(item["OBS_VALUE"], errors="coerce")
        if pd.isna(period_start) or pd.isna(value):
            continue
        period_end = period_start + pd.offsets.MonthEnd(0)
        if (
            period_start < pd.Timestamp(START).replace(day=1)
            or period_end > pd.Timestamp(END)
        ):
            continue
        ref_area = str(item["REF_AREA"]).strip().upper()
        key = (f"WS_CBPOL:M.{ref_area}", period)
        expected[key] = float(value)
    return expected


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(DATA_PATH)
    data = pd.read_csv(DATA_PATH)
    required_columns = {
        "iso3", "year", "reference_period", "interest_rate",
        "rate_type", "frequency", "series_code", "entity_type",
    }
    missing_columns = sorted(required_columns - set(data.columns))
    if missing_columns:
        raise RuntimeError(f"Dataset missing required columns: {missing_columns}")

    expected = {}
    expected.update(fetch_world_bank("FR.INR.LEND"))
    expected.update(fetch_world_bank("FR.INR.DPST"))
    expected.update(fetch_bis())

    dataset_rows = {}
    duplicate_keys = []
    for idx, row in data.iterrows():
        if row["frequency"] == "annual":
            key = (str(row["iso3"]).upper(), int(row["year"]), str(row["series_code"]))
        elif row["frequency"] == "monthly":
            key = (str(row["series_code"]), str(row["reference_period"]))
        else:
            raise RuntimeError(f"Unsupported frequency at CSV row {idx + 2}: {row['frequency']}")
        if key in dataset_rows:
            duplicate_keys.append(key)
        dataset_rows[key] = (idx, float(row["interest_rate"]))

    report = []
    matched = mismatched = missing_source = extra_dataset = 0
    for key, (idx, dataset_value) in dataset_rows.items():
        if key not in expected:
            extra_dataset += 1
            report.append({
                "dataset_row": idx + 2, "source_key": str(key),
                "dataset_value": dataset_value, "official_source_value": None,
                "difference": None, "verification_status": "NOT_FOUND_IN_FRESH_SOURCE",
            })
            continue
        source_value = expected[key]
        difference = dataset_value - source_value
        is_match = math.isclose(dataset_value, source_value, rel_tol=1e-10, abs_tol=1e-8)
        if is_match:
            matched += 1
            status = "MATCH"
        else:
            mismatched += 1
            status = "VALUE_MISMATCH"
        report.append({
            "dataset_row": idx + 2, "source_key": str(key),
            "dataset_value": dataset_value, "official_source_value": source_value,
            "difference": difference, "verification_status": status,
        })

    for key, source_value in expected.items():
        if key not in dataset_rows:
            missing_source += 1
            report.append({
                "dataset_row": None, "source_key": str(key),
                "dataset_value": None, "official_source_value": source_value,
                "difference": None, "verification_status": "MISSING_FROM_DATASET",
            })

    audit = pd.DataFrame(report)
    audit.to_csv(AUDIT_PATH, index=False)
    summary = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requested_start": START,
        "requested_end": END,
        "dataset_rows": int(len(data)),
        "fresh_official_source_observations": int(len(expected)),
        "matched_values": int(matched),
        "value_mismatches": int(mismatched),
        "missing_source_observations_in_dataset": int(missing_source),
        "dataset_observations_not_found_in_fresh_source": int(extra_dataset),
        "duplicate_dataset_keys": int(len(duplicate_keys)),
        "verification_passed": bool(
            matched == len(data)
            and mismatched == 0
            and missing_source == 0
            and extra_dataset == 0
            and len(duplicate_keys) == 0
        ),
        "sources": {
            "BIS": "https://stats.bis.org/api/v1/data/WS_CBPOL/M.",
            "World Bank lending": "https://api.worldbank.org/v2/country/all/indicator/FR.INR.LEND",
            "World Bank deposit": "https://api.worldbank.org/v2/country/all/indicator/FR.INR.DPST",
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["verification_passed"]:
        raise RuntimeError(
            "Source verification failed. Inspect source_verification.csv and summary JSON."
        )


if __name__ == "__main__":
    main()
