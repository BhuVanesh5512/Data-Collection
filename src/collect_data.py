"""Collect official central-bank and financial-authority interest rates only."""
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
import io

import pandas as pd
import pycountry
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TODAY = pd.Timestamp.today().normalize()
START = os.getenv("START_DATE", (TODAY - pd.DateOffset(years=5)).date().isoformat())
END = os.getenv("END_DATE", date.today().isoformat())
OUT = Path("data/processed/global_bank_interest_rates.csv")
MAX_HISTORY_YEARS = int(os.getenv("MAX_HISTORY_YEARS", "30"))
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

S = requests.Session()
S.headers["User-Agent"] = "Data-Collection-official-rates-research/2.0"
retry = Retry(
    total=6, connect=6, read=6, status=6, backoff_factor=2,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    respect_retry_after_header=True,
)
S.mount("https://", HTTPAdapter(max_retries=retry))
TIMEOUT = (20, 240)

# Authority labels for BIS reference areas. Unknown areas fail closed; they are
# never guessed from country names.
CENTRAL_BANKS = {
    "AR": "Central Bank of Argentina", "AU": "Reserve Bank of Australia",
    "BR": "Central Bank of Brazil", "CA": "Bank of Canada",
    "CH": "Swiss National Bank", "CL": "Central Bank of Chile",
    "HR": "Croatian National Bank",
    "CN": "People's Bank of China", "CO": "Bank of the Republic (Banco de la República)",
    "CZ": "Czech National Bank", "DK": "Danmarks Nationalbank",
    "GB": "Bank of England", "HK": "Hong Kong Monetary Authority",
    "HU": "Magyar Nemzeti Bank", "ID": "Bank Indonesia",
    "IL": "Bank of Israel", "IN": "Reserve Bank of India",
    "IS": "Central Bank of Iceland", "JP": "Bank of Japan",
    "KR": "Bank of Korea", "KW": "Central Bank of Kuwait",
    "MA": "Bank Al-Maghrib", "MK": "National Bank of the Republic of North Macedonia",
    "MX": "Bank of Mexico", "MY": "Bank Negara Malaysia",
    "NO": "Norges Bank", "NZ": "Reserve Bank of New Zealand",
    "PE": "Central Reserve Bank of Peru", "PH": "Bangko Sentral ng Pilipinas",
    "PL": "Narodowy Bank Polski", "RO": "National Bank of Romania",
    "RS": "National Bank of Serbia", "RU": "Bank of Russia",
    "SA": "Saudi Central Bank", "SE": "Sveriges Riksbank",
    "TH": "Bank of Thailand", "TR": "Central Bank of the Republic of Türkiye",
    "US": "Board of Governors of the Federal Reserve System",
    "ZA": "South African Reserve Bank", "XM": "European Central Bank",
    # Additional BIS euro-area reference areas and other possible policy-rate
    # areas. Names follow the BIS member-central-bank directory.
    "AT": "Central Bank of the Republic of Austria",
    "BE": "National Bank of Belgium",
    "DE": "Deutsche Bundesbank",
    "EE": "Bank of Estonia",
    "ES": "Bank of Spain",
    "FI": "Bank of Finland",
    "FR": "Bank of France",
    "GR": "Bank of Greece",
    "IE": "Central Bank of Ireland",
    "IT": "Bank of Italy",
    "LT": "Bank of Lithuania",
    "LU": "Central Bank of Luxembourg",
    "LV": "Bank of Latvia",
    "NL": "De Nederlandsche Bank",
    "PT": "Banco de Portugal",
    "SI": "Bank of Slovenia",
    "SK": "National Bank of Slovakia",
    "BA": "Central Bank of Bosnia and Herzegovina",
    "BG": "Bulgarian National Bank",
    "SG": "Monetary Authority of Singapore",
    "AE": "Central Bank of the United Arab Emirates",
    "VN": "State Bank of Viet Nam",
}
BIS_URL = "https://stats.bis.org/api/v1/data/WS_CBPOL/M."
BIS_INFO_URL = "https://data.bis.org/topics/CBPOL"
RBI_URL = "https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=23865"
RBI_AUTHORITY = "Reserve Bank of India"


def country_from_iso2(code):
    code = str(code).strip().upper()
    if code == "XM":
        return "Euro area", None
    country = pycountry.countries.get(alpha_2=code)
    if not country:
        raise RuntimeError(f"Unknown BIS reference area: {code}")
    return country.name, country.alpha_3


def flatten_columns(columns):
    if isinstance(columns, pd.MultiIndex):
        return [
            " ".join(str(part) for part in col if str(part) != "nan").strip()
            for col in columns
        ]
    return [str(col).strip() for col in columns]


def parse_rbi_value(value):
    if pd.isna(value):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "-", "—", "–", "NA", "N/A"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def rbi_policy_rates():
    """Read RBI's published Table 40 effective-date policy-rate history."""
    response = S.get(RBI_URL, timeout=TIMEOUT)
    response.raise_for_status()
    tables = pd.read_html(io.StringIO(response.text), displayed_only=False)
    selected = None
    date_col = None
    rate_cols = {}
    for table in tables:
        table.columns = flatten_columns(table.columns)
        normalized = {
            col: re.sub(r"[^a-z]", "", col.lower()) for col in table.columns
        }
        dc = next((col for col, key in normalized.items()
                   if "effectivedate" in key or key == "date"), None)
        if not dc:
            # RBI occasionally changes the table header structure. Fall back
            # only to a first column that actually contains parseable dates.
            first_col = table.columns[0] if len(table.columns) else None
            if first_col is not None:
                sample = pd.to_datetime(table[first_col].head(12), dayfirst=True, errors="coerce")
                if sample.notna().sum() >= 3:
                    dc = first_col
        if not dc:
            continue
        found = {
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
        found = {code: col for code, col in found.items() if col is not None}
        if not found and len(table.columns) >= 7:
            # RBI's published Table 40 has a stable official column order:
            # Effective Date, Bank Rate, Fix Range, Repo, Reverse Repo,
            # SDF, MSF, CRR, SLR. Exclude Fix Range and reserve ratios.
            positions = {
                "RBI_POLICY_BANK_RATE": 1,
                "RBI_POLICY_REPO": 3,
                "RBI_POLICY_REVERSE_REPO": 4,
                "RBI_POLICY_SDF": 5,
                "RBI_POLICY_MSF": 6,
            }
            found = {
                code: table.columns[pos]
                for code, pos in positions.items()
                if pos < len(table.columns)
            }
        if not found:
            continue
        selected, date_col, rate_cols = table, dc, found
        break
    if selected is None:
        print(
            "WARNING: RBI Table 40 could not be parsed. Keeping all BIS official "
            "policy-rate observations; no RBI values will be invented."
        )
        return pd.DataFrame()

    labels = {
        "RBI_POLICY_BANK_RATE": "Bank Rate",
        "RBI_POLICY_REPO": "Policy Repo Rate",
        "RBI_POLICY_REVERSE_REPO": "Fixed Reverse Repo Rate",
        "RBI_POLICY_SDF": "Standing Deposit Facility Rate",
        "RBI_POLICY_MSF": "Marginal Standing Facility Rate",
    }
    rows = []
    for _, item in selected.iterrows():
        effective = pd.to_datetime(item[date_col], dayfirst=True, errors="coerce")
        if pd.isna(effective) or effective < pd.Timestamp(START) or effective > pd.Timestamp(END):
            continue
        for code, col in rate_cols.items():
            value = parse_rbi_value(item[col])
            if value is None:
                continue
            period = effective.strftime("%Y-%m-%d")
            rows.append({
                "country": "India", "source_country_name": "India",
                "entity_type": "country", "country_code": "IN", "iso3": "IND",
                "bank_name": RBI_AUTHORITY, "authority_name": RBI_AUTHORITY,
                "bank_name_status": "identified_financial_authority",
                "institution_name": RBI_AUTHORITY, "institution_type": "central_bank",
                "monetary_authority_name": RBI_AUTHORITY,
                "monetary_authority_source_url": "https://www.rbi.org.in/",
                "institution_name_note": "Official monetary-policy rate published by the Reserve Bank of India.",
                "observation_date": period, "year": int(effective.year),
                "month": int(effective.month), "interest_rate": value,
                "is_estimated": False, "observation_status": "official_observation",
                "estimation_method": None, "rate_type": "policy",
                "rate_name": labels[code], "frequency": "event",
                "source_name": "Reserve Bank of India",
                "source_url": RBI_URL, "series_code": code,
                "series_name": labels[code], "units": "percent per year",
                "source_retrieved_at": NOW, "original_frequency": "effective_date",
                "reference_period": period,
                "rate_definition": "Rate shown in RBI Table 40 from its stated effective date.",
                "methodology_notes": (
                    "Official RBI effective-date observation. Only cells explicitly "
                    "published as numeric rates are included; blank/dash cells are not filled."
                ),
            })
    if not rows:
        print(
            "WARNING: RBI Table 40 produced no parseable observations in the "
            "selected window. Keeping BIS observations only for this run."
        )
        return pd.DataFrame()
    return pd.DataFrame(rows)


def bis_policy():
    response = S.get(
        BIS_URL,
        params={"startPeriod": START[:7], "endPeriod": END[:7], "format": "csvfile"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    raw = pd.read_csv(io.BytesIO(response.content))
    raw.columns = [str(c).strip() for c in raw.columns]
    required = {"TIME_PERIOD", "OBS_VALUE", "REF_AREA"}
    if not required.issubset(raw.columns):
        raise RuntimeError(f"Unexpected BIS CSV schema: {list(raw.columns)}")
    rows = []
    for _, item in raw.iterrows():
        period = str(item["TIME_PERIOD"]).strip()
        start = pd.to_datetime(period, format="%Y-%m", errors="coerce")
        value = pd.to_numeric(item["OBS_VALUE"], errors="coerce")
        if pd.isna(start) or pd.isna(value):
            continue
        if start < pd.Timestamp(START).replace(day=1) or start + pd.offsets.MonthEnd(0) > pd.Timestamp(END):
            continue
        area = str(item["REF_AREA"]).strip().upper()
        if area not in CENTRAL_BANKS:
            raise RuntimeError(f"No verified authority-name mapping for BIS area {area}.")
        country, iso3 = country_from_iso2(area)
        authority = CENTRAL_BANKS[area]
        rows.append({
            "country": country, "source_country_name": country,
            "entity_type": "country" if iso3 else "region",
            "country_code": area if iso3 else None, "iso3": iso3,
            "bank_name": authority, "authority_name": authority,
            "bank_name_status": "identified_financial_authority",
            "institution_name": authority,
            "institution_type": "central_bank" if iso3 else "regional_monetary_authority",
            "monetary_authority_name": authority,
            "monetary_authority_source_url": "https://www.bis.org/about/organisation/members.htm",
            "institution_name_note": "Monetary authority associated with the BIS policy-rate reference area.",
            "observation_date": start.strftime("%Y-%m-01"),
            "year": int(start.year), "month": int(start.month),
            "interest_rate": float(value), "is_estimated": False,
            "observation_status": "official_observation", "estimation_method": None,
            "rate_type": "policy", "rate_name": "BIS selected central bank policy rate",
            "frequency": "monthly", "source_name": "Bank for International Settlements",
            "source_url": BIS_INFO_URL, "series_code": f"WS_CBPOL:M.{area}",
            "series_name": f"Selected central bank policy rate - {country}",
            "units": "percent per year", "source_retrieved_at": NOW,
            "original_frequency": "monthly", "reference_period": period,
            "rate_definition": "BIS selected target or traded rate for the main policy instrument.",
            "methodology_notes": (
                "BIS monthly end-of-period observation. Date is labelled as first day "
                "of month; reference_period identifies the month."
            ),
        })
    if not rows:
        raise RuntimeError("BIS returned no in-window monthly policy-rate rows.")
    return pd.DataFrame(rows)


def main():
    global START
    if pd.Timestamp(START) > pd.Timestamp(END):
        raise ValueError(f"START_DATE {START} is after END_DATE {END}")

    # Start with five years. If the genuine official observations are still
    # below the user's 1,000-row target, expand backwards in five-year steps.
    # Never synthesize, interpolate, forward-fill or duplicate observations.
    explicit_start = bool(os.getenv("START_DATE"))
    requested_start = START
    window_start = START
    max_history_years = MAX_HISTORY_YEARS
    while True:
        START = window_start
        frames = [bis_policy(), rbi_policy_rates()]
        candidate = pd.concat(frames, ignore_index=True)
        candidate["observation_date"] = pd.to_datetime(candidate["observation_date"], errors="coerce")
        candidate["interest_rate"] = pd.to_numeric(candidate["interest_rate"], errors="coerce")
        candidate = candidate.dropna(subset=[
            "country", "observation_date", "interest_rate", "rate_type",
            "authority_name", "bank_name", "rate_name", "source_url",
        ])
        monthly_mask = candidate["frequency"].eq("monthly")
        monthly_starts = pd.to_datetime(
            candidate["reference_period"].where(monthly_mask).astype("string") + "-01",
            format="%Y-%m-%d", errors="coerce",
        )
        monthly_ends = monthly_starts + pd.offsets.MonthEnd(0)
        keep_monthly = (
            monthly_mask
            & monthly_ends.ge(pd.Timestamp(START))
            & monthly_starts.le(pd.Timestamp(END))
        )
        keep_event = (
            ~monthly_mask
            & candidate["observation_date"].between(pd.Timestamp(START), pd.Timestamp(END))
        )
        candidate = candidate[keep_monthly | keep_event].copy()
        if len(candidate) >= 1000 or explicit_start:
            data = candidate
            break
        elapsed_years = (pd.Timestamp(END) - pd.Timestamp(window_start)).days / 365.2425
        if elapsed_years >= max_history_years:
            data = candidate
            break
        window_start = (
            pd.Timestamp(window_start) - pd.DateOffset(years=5)
        ).date().isoformat()
        print(
            f"Only {len(candidate):,} official rows in the current window; "
            f"expanding history backwards to {window_start}."
        )

    data["collection_window_start"] = window_start
    duplicate_key = ["iso3", "observation_date", "series_code"]
    duplicates = int(data.duplicated(duplicate_key).sum())
    if duplicates:
        raise RuntimeError(f"Duplicate source observations detected: {duplicates}")
    if data["authority_name"].isna().any() or data["bank_name"].isna().any():
        raise RuntimeError("Every row must have a verified financial authority name.")
    if data["is_estimated"].astype(bool).any():
        raise RuntimeError("Estimated observations are not allowed in the official dataset.")
    data = data.sort_values(["country", "series_code", "observation_date"])
    data["observation_date"] = data["observation_date"].dt.strftime("%Y-%m-%d")
    data["month"] = data["month"].astype("Int64")
    data.insert(0, "observation_id", range(1, len(data) + 1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUT, index=False, encoding="utf-8")

    countries = data.loc[data["entity_type"] == "country", "iso3"].nunique()
    india = data[data["iso3"] == "IND"]
    print(f"Collection window: {window_start} to {END}")
    print(f"Rows: {len(data):,}; countries: {countries:,}")
    print(data.groupby(["source_name", "rate_name", "frequency"], dropna=False).size().to_string())
    print(f"India official policy-rate rows: {len(india):,}")
    print(f"Authorities: {data['authority_name'].nunique():,}")
    if len(data) < 1000:
        print(
            f"NOTICE: Only {len(data):,} genuine observations were available "
            f"after searching back up to {max_history_years} years. "
            "No synthetic rows were added."
        )
    if countries < 40:
        print("NOTICE: Country coverage is limited to economies with supported official sources.")


if __name__ == "__main__":
    main()
