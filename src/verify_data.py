"""Re-fetch official BIS and RBI sources and independently verify each CSV rate."""
import json
import math
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
import io

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TODAY = pd.Timestamp.today().normalize()
START = os.getenv("START_DATE", (TODAY - pd.DateOffset(years=5)).date().isoformat())
END = os.getenv("END_DATE", date.today().isoformat())
DATA_PATH = Path("data/processed/global_bank_interest_rates.csv")
AUDIT_PATH = Path("data/processed/source_verification.csv")
SUMMARY_PATH = Path("data/processed/source_verification_summary.json")
BIS_URL = "https://stats.bis.org/api/v1/data/WS_CBPOL/M."
RBI_URL = "https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=23865"

session = requests.Session()
session.headers["User-Agent"] = "Data-Collection-independent-verification/2.0"
retry = Retry(
    total=6, connect=6, read=6, status=6, backoff_factor=2,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]), respect_retry_after_header=True,
)
session.mount("https://", HTTPAdapter(max_retries=retry))
TIMEOUT = (20, 240)


def fetch_bis():
    response = session.get(
        BIS_URL,
        params={"startPeriod": START[:7], "endPeriod": END[:7], "format": "csvfile"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    raw = pd.read_csv(io.BytesIO(response.content))
    required = {"TIME_PERIOD", "OBS_VALUE", "REF_AREA"}
    if not required.issubset(raw.columns):
        raise RuntimeError(f"Unexpected BIS verification schema: {list(raw.columns)}")
    values = {}
    for _, item in raw.iterrows():
        period = str(item["TIME_PERIOD"]).strip()
        start = pd.to_datetime(period, format="%Y-%m", errors="coerce")
        value = pd.to_numeric(item["OBS_VALUE"], errors="coerce")
        if pd.isna(start) or pd.isna(value):
            continue
        if start < pd.Timestamp(START).replace(day=1) or start + pd.offsets.MonthEnd(0) > pd.Timestamp(END):
            continue
        area = str(item["REF_AREA"]).strip().upper()
        values[(f"WS_CBPOL:M.{area}", period)] = float(value)
    return values


def flatten_columns(columns):
    if isinstance(columns, pd.MultiIndex):
        return [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in columns]
    return [str(x).strip() for x in columns]


def parse_rbi_value(value):
    if pd.isna(value):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "-", "—", "–", "NA", "N/A"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def fetch_rbi():
    response = session.get(RBI_URL, timeout=TIMEOUT)
    response.raise_for_status()
    tables = pd.read_html(io.StringIO(response.text), displayed_only=False)
    result = {}
    for table in tables:
        table.columns = flatten_columns(table.columns)
        normalized = {c: re.sub(r"[^a-z]", "", c.lower()) for c in table.columns}
        date_col = next((c for c, k in normalized.items()
                         if "effectivedate" in k or k == "date"), None)
        if not date_col:
            first_col = table.columns[0] if len(table.columns) else None
            if first_col is not None:
                sample = pd.to_datetime(table[first_col].head(12), dayfirst=True, errors="coerce")
                if sample.notna().sum() >= 3:
                    date_col = first_col
        if not date_col:
            continue
        cols = {
            "RBI_POLICY_BANK_RATE": next((c for c, k in normalized.items()
                if "bankrate" in k and "marginal" not in k), None),
            "RBI_POLICY_REPO": next((c for c, k in normalized.items()
                if "repo" in k and "reverse" not in k and "marginal" not in k
                and "standing" not in k), None),
            "RBI_POLICY_REVERSE_REPO": next((c for c, k in normalized.items()
                if "reverserepo" in k or ("reverse" in k and "repo" in k)), None),
            "RBI_POLICY_SDF": next((c for c, k in normalized.items()
                if "standingdepositfacility" in k or k in {"sdf", "sdfrate"}), None),
            "RBI_POLICY_MSF": next((c for c, k in normalized.items()
                if "marginalstandingfacility" in k or k in {"msf", "msfrate"}), None),
        }
        cols = {code: col for code, col in cols.items() if col is not None}
        if not cols and len(table.columns) >= 7:
            positions = {
                "RBI_POLICY_BANK_RATE": 1,
                "RBI_POLICY_REPO": 3,
                "RBI_POLICY_REVERSE_REPO": 4,
                "RBI_POLICY_SDF": 5,
                "RBI_POLICY_MSF": 6,
            }
            cols = {
                code: table.columns[pos]
                for code, pos in positions.items()
                if pos < len(table.columns)
            }
        if not cols:
            continue
        for _, row in table.iterrows():
            effective = pd.to_datetime(row[date_col], dayfirst=True, errors="coerce")
            if pd.isna(effective) or effective < pd.Timestamp(START) or effective > pd.Timestamp(END):
                continue
            period = effective.strftime("%Y-%m-%d")
            for code, col in cols.items():
                value = parse_rbi_value(row[col])
                if value is not None:
                    result[(code, period)] = value
        break
    if not result:
        print(
            "WARNING: RBI Table 40 could not be independently parsed; "
            "verification will cover BIS rows only. RBI values are not assumed."
        )
        return {}
    return result


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(DATA_PATH)
    data = pd.read_csv(DATA_PATH)
    global START
    if "collection_window_start" not in data.columns:
        raise RuntimeError("Dataset is missing collection_window_start; recollect with the current collector.")
    starts = data["collection_window_start"].dropna().astype(str).unique()
    if len(starts) != 1:
        raise RuntimeError(f"Expected one collection window start, found: {starts.tolist()}")
    START = starts[0]
    required = {
        "authority_name", "bank_name", "rate_name", "observation_date",
        "interest_rate", "frequency", "series_code", "reference_period",
        "source_name", "is_estimated",
    }
    missing = sorted(required - set(data.columns))
    if missing:
        raise RuntimeError(f"Dataset missing required columns: {missing}")
    if data["authority_name"].isna().any() or data["bank_name"].isna().any():
        raise RuntimeError("Some records have no financial authority name.")
    if data["is_estimated"].astype(str).str.lower().isin(["true", "1", "yes"]).any():
        raise RuntimeError("Estimated records found in the official-only dataset.")

    expected_all = {}
    expected_all.update(fetch_bis())
    rbi_expected = fetch_rbi()
    expected_all.update(rbi_expected)

    # Verify all rows present in the dataset. BIS also exposes some series
    # outside the collector's mapped authority set; these are not silently
    # treated as collected records.
    included_series = set(data["series_code"].astype(str))
    expected = {
        key: value for key, value in expected_all.items()
        if key[0] in included_series
    }

    dataset = {}
    duplicate_keys = []
    report = []
    for idx, row in data.iterrows():
        if row["frequency"] == "monthly":
            key = (str(row["series_code"]), str(row["reference_period"]))
        elif row["frequency"] == "event":
            key = (str(row["series_code"]), pd.Timestamp(row["observation_date"]).strftime("%Y-%m-%d"))
        else:
            raise RuntimeError(f"Unsupported frequency at row {idx + 2}: {row['frequency']}")
        if key in dataset:
            duplicate_keys.append(key)
        dataset[key] = (idx, float(row["interest_rate"]))

    matched = mismatched = missing_source = extra_dataset = 0
    for key, (idx, value) in dataset.items():
        official = expected.get(key)
        if official is None:
            extra_dataset += 1
            status = "NOT_FOUND_IN_FRESH_SOURCE"
            difference = None
        else:
            difference = value - official
            if math.isclose(value, official, rel_tol=1e-10, abs_tol=1e-8):
                matched += 1
                status = "MATCH"
            else:
                mismatched += 1
                status = "VALUE_MISMATCH"
        report.append({
            "dataset_row": idx + 2, "source_key": str(key),
            "dataset_value": value, "official_source_value": official,
            "difference": difference, "verification_status": status,
        })

    for key, official in expected.items():
        if key not in dataset:
            missing_source += 1
            report.append({
                "dataset_row": None, "source_key": str(key),
                "dataset_value": None, "official_source_value": official,
                "difference": None, "verification_status": "MISSING_FROM_DATASET",
            })

    pd.DataFrame(report).to_csv(AUDIT_PATH, index=False)
    summary = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requested_start": START, "requested_end": END,
        "dataset_rows": int(len(data)),
        "fresh_official_source_observations": int(len(expected)),
        "all_source_observations_available_for_included_series": int(len(expected_all)),
        "rbi_policy_observations_available_for_verification": int(len(rbi_expected)),
        "rbi_policy_rows_in_dataset": int(data["source_name"].astype(str).str.contains("Reserve Bank of India").sum()),
        "matched_values": int(matched), "value_mismatches": int(mismatched),
        "missing_source_observations_in_dataset": int(missing_source),
        "dataset_observations_not_found_in_fresh_source": int(extra_dataset),
        "duplicate_dataset_keys": int(len(duplicate_keys)),
        "authority_names_present": bool(data["authority_name"].notna().all()),
        "verification_passed": bool(
            matched == len(data) and mismatched == 0 and missing_source == 0
            and extra_dataset == 0 and len(duplicate_keys) == 0
        ),
        "sources": {"BIS": "https://data.bis.org/topics/CBPOL", "RBI": RBI_URL},
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["verification_passed"]:
        raise RuntimeError("Official-source verification failed; inspect the audit CSV.")


if __name__ == "__main__":
    main()
