"""Do the fundamentals findings show up in forward price returns?

Joins the Distill point-in-time panel (December snapshots) to Stooq daily
closes you downloaded yourself. This repository ships no price data; the
per-firm returns only exist on your machine after you run this. Tests, on
market-adjusted forward price returns:

  H1 capital cycle: boom cell (top-quintile capex x asset growth) vs quiet cell
  H2 accruals:      Q1 (cash-rich) minus Q5 (paper earnings) spread
  H3 health:        score buckets, incl. the sub-30 distress tail

Method notes:
- Tickers that map to more than one CIK in the panel are excluded. Ticker is
  the join key here, so they cannot be used safely.
- Stooq closes are split-adjusted but not dividend-adjusted: these are price
  returns, which understate total-return spreads for dividend payers.
- Stooq's bundle under-covers delisted firms (survivorship bias). For H1/H3
  that bias mostly works against finding an effect, because the casualties
  are missing. Match rates are printed so the reader can judge.
- "Market-adjusted" = minus the same-year median return of all matched firms.

Usage: python examples/return_tests.py [path/to/d_us_txt.zip]
       (the zip is unpacked into STOOQ_DIR on first run)
"""

import sys
from pathlib import Path

import pandas as pd

from distill_toolkit import client, joins, stooq

OUT = client.CACHE_DIR / "returns_joined.parquet"

HEALTH_BINS = [0, 30, 50, 70, 85, 100]
HEALTH_LABELS = ["0-30", "30-50", "50-70", "70-85", "85-100"]


def main():
    zip_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    if zip_path and not stooq.index():
        print(f"unpacking {zip_path} -> {stooq.default_root()}")
        stooq.extract_bundle(zip_path)
    idx = stooq.index()
    print(f"stooq tickers on disk: {len(idx)}")
    if not idx:
        sys.exit("no Stooq files found; pass the bundle path or set STOOQ_DIR")

    df = pd.read_csv(client.panel_path(), parse_dates=["as_of_date"])
    multi = df.groupby("ticker").cik.nunique()
    collided = set(multi[multi > 1].index)
    dec = df[
        (df.as_of_date.dt.month == 12)
        & df.is_listed_equity
        & (df.revenue > 0)
        & ~df.ticker.isin(collided)
    ].copy()
    dec["year"] = dec.as_of_date.dt.year
    dec = dec[(dec.year >= 2012) & (dec.year <= 2024)]

    dec["has_px"] = dec.ticker.map(lambda t: stooq.stooq_key(t) in idx)
    print(f"panel firm-years: {len(dec)}, with stooq file: {dec.has_px.mean()*100:.1f}%")

    rets = []
    matched = dec[dec.has_px]
    for i, r in enumerate(matched.itertuples()):
        c = stooq.closes(r.ticker)
        if c is None:
            continue
        r1 = joins.forward_return(c, r.as_of_date, 365)
        r2 = joins.forward_return(c, r.as_of_date, 730)
        if r1 is None and r2 is None:
            continue
        rets.append({"cik": r.cik, "ticker": r.ticker, "year": r.year, "ret1y": r1, "ret2y": r2})
        if (i + 1) % 5000 == 0:
            print(f"{i+1}/{len(matched)}")
    rx = pd.DataFrame(rets)
    print(f"firm-years with usable returns: {len(rx)}")

    m = dec.merge(rx, on=["cik", "ticker", "year"])
    for col in ("ret1y", "ret2y"):
        m[f"x{col}"] = joins.market_adjust(m, col)
    m.to_parquet(OUT)

    # H1 capital cycle
    s = m.dropna(subset=["capex_intensity", "asset_growth"]).copy()
    s = s[s.operating_margin.abs() < 1]
    s["cap_q"] = s.groupby("year").capex_intensity.transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
    s["ag_q"] = s.groupby("year").asset_growth.transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
    boom = s[(s.cap_q == 4) & (s.ag_q == 4)]
    quiet = s[(s.cap_q == 0) & (s.ag_q == 0)]
    print("\nH1 capital cycle (market-adjusted price returns):")
    for name, g in (("boom", boom), ("quiet", quiet)):
        print(f"  {name:6} n={len(g):5}  1y med={g.xret1y.median()*100:6.2f}%  "
              f"2y med={g.xret2y.median()*100:6.2f}%  2y mean={g.xret2y.mean()*100:6.2f}%")

    # H2 accruals
    a = m.dropna(subset=["accruals_ratio"]).copy()
    a["acc_q"] = a.groupby("year").accruals_ratio.transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
    print("\nH2 accruals quintiles (0=cash-rich): 1y market-adjusted median return")
    print((a.groupby("acc_q").xret1y.median() * 100).round(2).to_string())

    # H3 health buckets (only when the export carries the score)
    if "health_score" not in m.columns:
        print("\nH3 skipped: this export has no health_score column (see /sec/financial-health)")
        return
    h = m.dropna(subset=["health_score"]).copy()
    h["bucket"] = pd.cut(h.health_score, HEALTH_BINS, labels=HEALTH_LABELS, include_lowest=True)
    print("\nH3 health buckets: 1y market-adjusted median return / n")
    out = h.groupby("bucket", observed=True).agg(
        med=("xret1y", lambda x: 100 * x.median()), n=("xret1y", "size")).round(2)
    print(out.to_string())


if __name__ == "__main__":
    main()
