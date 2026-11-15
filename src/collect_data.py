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
OUT = Path("data/processed/global_bank_interest_rates.csv")
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
S = requests.Session()
S.headers["User-Agent"] = "Data-Collection-research/1.0"
# Retry temporary API failures and slow responses instead of aborting the workflow.
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

def world_bank(indicator, rate_type):
    url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
    observations, page = [], 1
    while True:
        r = S.get(url, params={"date": f"{START[:4]}:{END[:4]}", "format":"json",
                              "per_page":2000, "page":page}, timeout=REQUEST_TIMEOUT)
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
        if x.get("value") is None or len(x.get("countryiso3code","")) != 3:
            continue
        year = str(x["date"])
        period = f"{year}-01-01"
        if START <= period <= END:
            rows.append({
                "country":x["country"]["value"], "iso3":x["countryiso3code"],
                "observation_date":period, "year":int(year), "month":None,
                "interest_rate":float(x["value"]), "rate_type":rate_type,
                "frequency":"annual", "central_bank":None,
                "source_name":"World Bank World Development Indicators",
                "source_url":f"https://data.worldbank.org/indicator/{indicator}",
                "series_code":indicator, "series_name":x["indicator"]["value"],
                "units":"percent", "source_retrieved_at":NOW,
                "original_frequency":"annual", "reference_period":year,
                "rate_definition":"As defined in World Bank indicator metadata",
                "methodology_notes":"Annual source observation; not interpolated or expanded."
            })
    return pd.DataFrame(rows)

def bis_policy():
    # BIS SDMX v1 data endpoint for the CBPOL policy-rate dataflow.
    url = "https://stats.bis.org/api/v1/data/WS_CBPOL/all"
    r = S.get(url, params={"startPeriod":START,"endPeriod":END,"format":"csv"}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content))
    df.columns = [str(c).strip() for c in df.columns]
    def find(*names):
        return next((c for c in df.columns if c.lower() in [n.lower() for n in names]), None)
    tc, vc = find("TIME_PERIOD"), find("OBS_VALUE")
    cc, sc, fc = find("REF_AREA"), find("SERIES","INDICATOR"), find("FREQ")
    if not tc or not vc:
        raise RuntimeError("Unexpected BIS CSV schema: "+str(list(df.columns)))
    rows=[]
    for _, x in df.iterrows():
        dt=pd.to_datetime(x[tc], errors="coerce")
        val=pd.to_numeric(x[vc], errors="coerce")
        if pd.isna(dt) or pd.isna(val) or dt < pd.Timestamp(START) or dt > pd.Timestamp(END):
            continue
        code=str(x[cc]) if cc else None
        rows.append({
            "country":code, "iso3":code if code and len(code)==3 else None,
            "observation_date":dt.strftime("%Y-%m-%d"), "year":dt.year, "month":dt.month,
            "interest_rate":float(val), "rate_type":"policy",
            "frequency":str(x[fc]) if fc else "as published",
            "central_bank":None, "source_name":"Bank for International Settlements",
            "source_url":"https://data.bis.org/topics/CBPOL",
            "series_code":str(x[sc]) if sc else "WS_CBPOL",
            "series_name":"Central bank policy rate", "units":"percent per year",
            "source_retrieved_at":NOW, "original_frequency":str(x[fc]) if fc else "as published",
            "reference_period":dt.strftime("%Y-%m"),
            "rate_definition":"BIS selected policy rate for main policy instrument",
            "methodology_notes":"See BIS series metadata for country-specific policy-rate definitions."
        })
    if not rows:
        raise RuntimeError("BIS returned no policy-rate rows; inspect API response/schema.")
    return pd.DataFrame(rows)

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames=[world_bank("FR.INR.LEND","lending"),
            world_bank("FR.INR.DPST","deposit"), bis_policy()]
    frames=[x for x in frames if not x.empty]
    if not frames:
        raise RuntimeError("No official observations collected.")
    df=pd.concat(frames,ignore_index=True)
    df["observation_date"]=pd.to_datetime(df["observation_date"],errors="coerce")
    df["interest_rate"]=pd.to_numeric(df["interest_rate"],errors="coerce")
    df=df.dropna(subset=["country","observation_date","interest_rate","rate_type"])
    df=df[(df.observation_date>=pd.Timestamp(START))&(df.observation_date<=pd.Timestamp(END))]
    df=df.drop_duplicates(["iso3","observation_date","rate_type","series_code"],keep="last")
    df=df.sort_values(["country","rate_type","observation_date"])
    df["observation_date"]=df.observation_date.dt.strftime("%Y-%m-%d")
    df.insert(0,"observation_id",range(1,len(df)+1))
    df.to_csv(OUT,index=False,encoding="utf-8")
    print(f"Rows: {len(df):,}; ISO3 countries: {df.iso3.dropna().nunique():,}")
    print(df.groupby(["rate_type","frequency"],dropna=False).size().to_string())
    if len(df)<1000: print("NOTICE: Fewer than 1,000 real rows; no synthetic rows added.")
    if df.iso3.dropna().nunique()<100: print("NOTICE: Fewer than 100 countries; broaden official sources.")

if __name__=="__main__":
    main()
