"""Where did a cohort's price return come from: revenue per share, or the multiple?

For each ticker, take the fiscal year ending nearest a baseline date and the
latest fiscal year on file, price both period-ends from your Stooq bundle, put
the diluted share count on one split basis, and decompose:

    price_return = revenue_per_share_growth x multiple_change

Two anchors are reported per name. "Fiscal" prices each period-end against
that year's own revenue, which was not filed until weeks later (docs/traps.md,
trap 4). "No-lookahead" prices the same dates against the most recent annual
actually on file at that date, fetched from the as-of endpoint (Pro scope).

A share-count step that looks like a split is only put on one basis when the
never-restated sharesOutstanding series agrees that a split happened. Flags it
contradicts, or cannot test, are printed and left unapplied.

Before that, every fiscal year whose two served share counts disagree by more
than 2x is printed. About 1% of filer-years on a research pool arrive with the
diluted count in millions while the rest of the response is in raw shares, and
that year would otherwise be decomposed as if it were a count.

Usage: python examples/valuation_decomposition.py BASELINE_ISO TICKER [TICKER ...]

The cohort and the baseline date are yours to choose; the script ships neither.
       defaults: 2022-11-30 and the cohort below
"""

from __future__ import annotations

import re
import sys
from datetime import date

import httpx
import pandas as pd

from distill_toolkit import client, joins, stooq


def nearest_fiscal_year(years: list[dict], target: date) -> dict | None:
    dated = [y for y in years if y.get("periodEnd")]
    if not dated:
        return None
    return min(dated, key=lambda y: abs((date.fromisoformat(y["periodEnd"]) - target).days))


def asof_revenue(ticker: str, iso: str) -> float | None:
    """Most recent annual revenue actually on file at ``iso``. None if not covered."""
    try:
        r = client.get(f"/api/v1/sec/fundamentals/{ticker}/as-of/{iso}", period="annual")
    except httpx.HTTPStatusError:
        return None
    if not isinstance(r, dict) or not isinstance(r.get("values"), list):
        keys = sorted(r)[:10] if isinstance(r, dict) else type(r).__name__
        raise RuntimeError(f"as-of response shape not understood for {ticker}: {keys}")
    rev = [v for v in r["values"] if v.get("conceptGroup") == "Revenue"]
    return float(rev[0]["value"]) if rev and rev[0].get("value") is not None else None


def one(ticker: str, baseline: date) -> dict | None:
    try:
        hist = client.get(f"/api/v1/sec/fundamentals/{ticker}/history")
    except httpx.HTTPStatusError as e:
        print(f"{ticker}: HTTP {e.response.status_code}")
        return None
    years = [
        y for y in hist.get("years", [])
        if y.get("revenue") and y.get("weightedAverageSharesDiluted") and y.get("periodEnd")
    ]
    if len(years) < 2:
        print(f"{ticker}: fewer than two usable years")
        return None
    y0 = nearest_fiscal_year(years, baseline)
    y1 = max(years, key=lambda y: y["fiscalYear"])
    if y0 is None or y0["fiscalYear"] >= y1["fiscalYear"]:
        print(f"{ticker}: no window")
        return None

    shares = {y["fiscalYear"]: float(y["weightedAverageSharesDiluted"]) for y in years}
    # Before anything is rebased or decomposed: do the two served share counts for
    # the same fiscal year even describe the same population? A ratio near a small
    # integer is a split-basis difference, which is what the flags below are about;
    # a ratio in the thousands is a unit switch inside one response, and it flows
    # into decompose() as if it were a count.
    outstanding = {int(y["fiscalYear"]): float(y["sharesOutstanding"])
                   for y in years if y.get("sharesOutstanding")}
    for bad in joins.share_series_sanity(outstanding, shares):
        print(f"{ticker}: FY{bad['fiscal_year']} share counts disagree by "
              f"{bad['ratio']:.2f}x: sharesOutstanding {bad['shares_outstanding']:,.0f} "
              f"against weighted-average diluted {bad['weighted_average_diluted']:,.0f}")
    flags = [f for f in joins.split_basis_flags(shares) if y0["fiscalYear"] < f[0] <= y1["fiscalYear"]]
    # A step in the diluted series is not proof of a split, and about a third of
    # these flags are an issuance or a conversion. Only a flag the never-restated
    # sharesOutstanding agrees with is applied; the rest are printed and left
    # alone, because rebasing on a false flag moves every earlier year silently.
    verdicts = joins.corroborate_flags(years, flags)
    applied = [f for f, v in zip(flags, verdicts) if v["corroborated"]]
    rejected = [(f, v["verdict"]) for f, v in zip(flags, verdicts) if not v["corroborated"]]
    for (year, ratio, factor), verdict in rejected:
        print(f"{ticker}: split flag FY{year} (x{factor:g}, diluted ratio {ratio:.2f}) "
              f"{verdict} against sharesOutstanding, not applied")
    if applied:
        shares = joins.rebase_shares(shares, applied)

    p0, p1 = stooq.px(ticker, y0["periodEnd"]), stooq.px(ticker, y1["periodEnd"])
    if p0 is None or p1 is None:
        print(f"{ticker}: no price on disk for one of the dates")
        return None

    fiscal = joins.decompose(p0, p1, y0["revenue"], y1["revenue"],
                             shares[y0["fiscalYear"]], shares[y1["fiscalYear"]])
    row = {
        "ticker": ticker,
        "fy0": y0["fiscalYear"], "fy1": y1["fiscalYear"],
        "p0": p0, "p1": p1,
        "split_flags": ";".join(f"{y}:{f:g}" for y, _r, f in applied),
        "split_flags_rejected": ";".join(f"{y}:{f:g}:{v}" for (y, _r, f), v in rejected),
        "ret": fiscal["ret"], "rps": fiscal["rps"], "mult_fiscal": fiscal["mult"],
        "ps0_fiscal": fiscal["ps0"], "ps1_fiscal": fiscal["ps1"],
        "mcap0": p0 * shares[y0["fiscalYear"]], "mcap1": p1 * shares[y1["fiscalYear"]],
        "rev0": float(y0["revenue"]), "rev1": float(y1["revenue"]),
    }
    rev0_nl, rev1_nl = asof_revenue(ticker, y0["periodEnd"]), asof_revenue(ticker, y1["periodEnd"])
    if rev0_nl and rev1_nl:
        nl = joins.decompose(p0, p1, rev0_nl, rev1_nl,
                             shares[y0["fiscalYear"]], shares[y1["fiscalYear"]])
        row["mult_nolookahead"] = nl["mult"]
        row["ps1_nolookahead"] = nl["ps1"]
    return row


def main():
    args = sys.argv[1:]
    if len(args) < 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args[0]):
        sys.exit("usage: valuation_decomposition.py BASELINE_ISO TICKER [TICKER ...]")
    baseline = date.fromisoformat(args.pop(0))
    cohort = args
    if not stooq.index():
        sys.exit("no Stooq files found; set STOOQ_DIR to your unpacked bundle")

    rows = [r for t in cohort if (r := one(t, baseline))]
    if not rows:
        sys.exit("no names produced a row; see the messages above")
    df = pd.DataFrame(rows).set_index("ticker")
    pd.set_option("display.width", 200)
    cols = ["fy0", "fy1", "ret", "rps", "mult_fiscal", "mult_nolookahead", "ps1_fiscal",
            "split_flags", "split_flags_rejected"]
    print(df[[c for c in cols if c in df]].round(2).to_string())

    mcap0, mcap1 = df.mcap0.sum(), df.mcap1.sum()
    rev0, rev1 = df.rev0.sum(), df.rev1.sum()
    ps0, ps1 = mcap0 / rev0, mcap1 / rev1
    added = mcap1 - mcap0
    # Cap added by revenue growth at the OLD multiple; the rest is re-rating.
    from_revenue = (rev1 - rev0) * ps0
    print(f"\ncohort market cap {mcap0/1e12:.2f}T -> {mcap1/1e12:.2f}T ({mcap1/mcap0:.2f}x); "
          f"revenue {rev0/1e12:.3f}T -> {rev1/1e12:.3f}T ({rev1/rev0:.2f}x); "
          f"aggregate P/S {ps0:.2f} -> {ps1:.2f} ({ps1/ps0:.2f}x)")
    if added:
        print(f"of {added/1e12:.2f}T added, {from_revenue/1e12:.2f}T at the old multiple; "
              f"{(added-from_revenue)/added*100:.0f}% is multiple change")
    print("market cap here is price x weighted-average diluted shares (a proxy; see docs/traps.md)")
    out = client.CACHE_DIR / "valuation_decomposition.parquet"
    df.to_parquet(out)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
