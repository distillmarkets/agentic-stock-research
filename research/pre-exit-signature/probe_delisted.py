"""Bounded API probe: does the panel's last row precede the served delisting date?

Spends at most 150 uncached calls on
``/api/v1/sec/fundamentals/{ticker}/as-of/2026-09-03?period=annual`` for a
stratified sample of CIKs that left the panel, and keeps three things from each
response: ``delistedAt``, ``cikNumber`` (so a recycled ticker is visible rather
than silent) and the latest ``filedAt`` across the returned annual values, which
is the last annual filing the corpus holds for that issuer.

The sample is pinned to ``cache/research/pre-exit-signature/probe_sample.csv``
on the first run and read from it afterwards, so the study's denominator cannot
move underneath it. ``study.py`` reads only the cached responses and never runs
this file.

    ./.venv/bin/python research/pre-exit-signature/probe_delisted.py
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pandas as pd

from distill_toolkit import client

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from panel_base import CACHE, build_universe  # noqa: E402

AS_OF = "2026-09-03"
BUDGET = 150
SAMPLE_FILE = CACHE / "probe_sample.csv"
OUT_FILE = CACHE / "probe_delisted.csv"


def sample(n: int = BUDGET, seed: int = 11) -> pd.DataFrame:
    """One exited CIK per row, stratified by panel-drop year, pinned to disk."""
    if SAMPLE_FILE.exists():
        return pd.read_csv(SAMPLE_FILE, dtype={"cik": str})
    u, firm = build_universe()
    ex = firm[firm["exit"]].copy()
    ex["drop_year"] = ex.last_qi // 4
    last_rows = u.sort_values(["cik", "qi"]).groupby("cik").tail(1).set_index("cik")
    ex["ticker"] = last_rows.ticker.reindex(ex.index)
    ex = ex.dropna(subset=["ticker"]).reset_index().rename(columns={"index": "cik"})
    per = max(1, n // ex.drop_year.nunique())
    picked = (ex.groupby("drop_year", group_keys=False)
                .apply(lambda g: g.sample(min(per, len(g)), random_state=seed), include_groups=False)
                .reset_index(drop=True))
    if len(picked) < n:
        rest = ex[~ex.cik.isin(picked.cik)].sample(n - len(picked), random_state=seed)
        picked = pd.concat([picked, rest], ignore_index=True)
    picked = picked.head(n)[["cik", "ticker", "drop_year", "last_qi", "fresh_qi"]]
    SAMPLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    picked.to_csv(SAMPLE_FILE, index=False)
    return picked


def main() -> None:
    s = sample()
    uncached = sum(not client.is_cached(f"/api/v1/sec/fundamentals/{t}/as-of/{AS_OF}",
                                        period="annual") for t in s.ticker)
    print(f"{len(s)} tickers, {uncached} uncached calls to spend (budget {BUDGET})")
    rows = []
    for r in s.itertuples():
        path = f"/api/v1/sec/fundamentals/{r.ticker}/as-of/{AS_OF}"
        rec = {"cik": r.cik, "ticker": r.ticker, "status": "ok"}
        try:
            d = client.get(path, period="annual")
        except httpx.HTTPStatusError as e:
            rec["status"] = f"http_{e.response.status_code}"
            rows.append(rec)
            continue
        vals = d.get("values") or []
        filed = [v.get("filedAt") for v in vals if v.get("filedAt")]
        rec.update({"served_cik": d.get("cikNumber"), "delisted_at": d.get("delistedAt"),
                    "period_end": d.get("periodEnd"), "company": d.get("companyName"),
                    "last_filed_at": max(filed) if filed else None, "n_values": len(vals)})
        rows.append(rec)
    out = pd.DataFrame(rows)
    out.to_csv(OUT_FILE, index=False)
    print(json.dumps(out.status.value_counts().to_dict(), indent=1))
    print(f"wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
