"""Study: how different is history in first-print vs latest-wins vintages?

For each sampled firm, compare per fiscal year:
  - PIT side: the earliest December panel snapshot citing that fiscal year
    (what a researcher knew at the time)
  - Latest side: GET /sec/fundamentals/{ticker}/history, which the API documents
    as "latest filing wins on restatement" (what a researcher fetching today sees)

Outputs cache/pit_vs_latest.parquet with one row per (cik, fiscal_year):
revenue and net-margin under both vintages.
"""


import httpx
import pandas as pd

from distill_toolkit import client

OUT = client.CACHE_DIR / "pit_vs_latest.parquet"
SAMPLE = 300
SEED = 42
FY_MIN, FY_MAX = 2014, 2023


def first_print_panel() -> pd.DataFrame:
    df = pd.read_csv(client.CACHE_DIR / "panel.csv", parse_dates=["as_of_date"])
    dec = df[
        (df.as_of_date.dt.month == 12) & df.is_listed_equity & (df.revenue > 0)
    ].copy()
    dec = dec[(dec.fiscal_year >= FY_MIN) & (dec.fiscal_year <= FY_MAX)]
    dec.sort_values("as_of_date", inplace=True)
    # earliest December snapshot citing each (cik, fiscal_year) = first print
    fp = dec.drop_duplicates(subset=["cik", "fiscal_year"], keep="first")
    return fp[["cik", "ticker", "fiscal_year", "revenue", "net_margin"]].rename(
        columns={"revenue": "rev_pit", "net_margin": "netm_pit"}
    )


def main():
    fp = first_print_panel()
    counts = fp.groupby("cik").fiscal_year.nunique()
    eligible = counts[counts >= 6].index
    fp = fp[fp.cik.isin(eligible)]
    tickers = (
        fp.drop_duplicates("cik")
        .sample(SAMPLE, random_state=SEED)[["cik", "ticker"]]
        .values.tolist()
    )
    print(f"eligible firms: {len(eligible)}, sampled: {len(tickers)}")

    rows = []
    for i, (cik, ticker) in enumerate(tickers):
        try:
            hist = client.get(f"/api/v1/sec/fundamentals/{ticker}/history")
        except httpx.HTTPStatusError as e:
            print(f"{ticker}: HTTP {e.response.status_code}", flush=True)
            continue
        for y in hist.get("years", []):
            fy = y.get("fiscalYear")
            rev, ni = y.get("revenue"), y.get("netIncome")
            if fy is None or not rev:
                continue
            rows.append(
                {
                    "cik": cik,
                    "ticker": ticker,
                    "fiscal_year": fy,
                    "rev_latest": rev,
                    "netm_latest": (ni / rev) if ni is not None else None,
                }
            )
        if (i + 1) % 25 == 0:
            print(f"{i+1}/{len(tickers)}", flush=True)

    latest = pd.DataFrame(rows)
    merged = fp.merge(latest, on=["cik", "fiscal_year"], how="inner", suffixes=("", "_x"))
    merged.to_parquet(OUT)
    print(f"matched firm-years: {len(merged)} -> {OUT}")


if __name__ == "__main__":
    main()
