"""Adversarial review of ``research/naming-the-dead/``.

Four checks, in the order ``agents/review.md`` sets out. There is no null to
rebuild and no price window to move: the reviewed study is a census, so the
damage a review can do here is to the denominator, to the key the cohorts are
cut on, and to the scope of the claim.

    R1  the denominator: is "still listed" what the study says it is
    R2  the same three cohorts asked by the key a caller actually holds, the
        ticker, with the outcome split three ways rather than two
    R3  the scope: does SEC's own free per-CIK submissions file name the dead
    R4  the sector cut, re-keyed on the CIK instead of the ticker

Every number in README.md comes out of this script. R3 needs SEC's per-CIK
submissions records reduced to ``submissions.csv`` under this study's cache
folder; this repository ships no downloader for them and
``docs/data-sources.md`` has the fetch. R3 is skipped with a printed note when
that file is absent, and the other three checks still run. From the repository
root:

    SEC_TICKERS=cache/sec/company_tickers.json \\
    DISTILL_OFFLINE=1 ./.venv/bin/python research/review-naming-the-dead/study.py

Uncached API calls: 0. The client's request functions are replaced by a raiser
before anything else is imported. R3 reads the probe's CSV and never fetches.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DISTILL_OFFLINE", "1")

import distill_toolkit.client as _client  # noqa: E402


def _no_call(*_a, **_k):
    raise RuntimeError("the review makes no API call; every input is on disk")


_client.get = _client.post = _client.request = _client.download = _no_call

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from distill_toolkit import charts, client, sec_tickers  # noqa: E402

HERE = Path(__file__).parent
OUT = client.CACHE_DIR / "research" / "review-naming-the-dead"
CHARTS = HERE / "charts"
HEALTHCARE_FLOOR = 10_000_000

COHORTS = ["still filing", "stopped filing, no exit form", "listing ended, dated"]
OUTCOMES = ["the company you asked for", "a different company", "nothing"]


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def firm_table() -> tuple[pd.DataFrame, pd.Timestamp, str]:
    """One row per CIK, with the cohort the review cuts on.

    The reviewed study splits on ``listed_until`` alone: set means the listing
    ended, absent means still listed. Absent also covers a firm that simply
    stopped appearing with no Form 25 and no Form 15 on file, which is not the
    same thing, so it gets its own cohort here.
    """
    path = client.panel_path()
    df = pd.read_csv(path, low_memory=False)
    if "listed_until" not in df.columns:
        raise SystemExit(f"{path.name} carries no listed_until column; see the study's README")
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    final = df["as_of_date"].max()
    firm = (df.sort_values("as_of_date").groupby("cik")
            .agg(first_row=("as_of_date", "min"), last_row=("as_of_date", "max"),
                 ticker=("ticker", "last"), listed_until=("listed_until", "last"),
                 listing_end_source=("listing_end_source", "last")))
    firm["ended"] = firm["listed_until"].notna()
    firm["cohort"] = [
        COHORTS[2] if ended else (COHORTS[0] if last == final else COHORTS[1])
        for ended, last in zip(firm["ended"], firm["last_row"])
    ]
    firm["cohort"] = pd.Categorical(firm["cohort"], COHORTS, ordered=True)
    return firm, final, path.name


# ---------------------------------------------------------------------------
# R1 the denominator
# ---------------------------------------------------------------------------
def r1_denominator(firm: pd.DataFrame, free: set[int]) -> pd.DataFrame:
    """Nameable by CIK, on the three cohorts instead of two.

    The study reports 88.7% for "still listed". That pool holds every firm with
    no ``listed_until``, including ones whose last panel row is years old.
    """
    firm = firm.copy()
    firm["nameable"] = firm.index.astype(int).isin(free)
    tab = (firm.groupby("cohort", observed=True)
           .agg(n=("nameable", "size"), nameable=("nameable", "sum")))
    tab["share"] = (100 * tab["nameable"] / tab["n"]).round(1)
    return tab.reset_index()


def r1_misses(firm: pd.DataFrame, free: set[int]) -> dict:
    """How much of the study's 11.3% "still listed" miss is an undated departure."""
    firm = firm.copy()
    firm["nameable"] = firm.index.astype(int).isin(free)
    live = firm[~firm["ended"]]
    miss = live[~live["nameable"]]
    stale = (miss["cohort"] == COHORTS[1]).sum()
    return {"as_published_still_listed": int(len(live)),
            "as_published_share": round(100 * live["nameable"].mean(), 1),
            "misses": int(len(miss)),
            "misses_that_stopped_filing": int(stale),
            "misses_that_stopped_filing_share": round(100 * stale / len(miss), 1)}


def r1_by_last_year(firm: pd.DataFrame, free: set[int]) -> pd.DataFrame:
    """The same pool, by the year of the firm's last panel row."""
    live = firm[~firm["ended"]].copy()
    live["nameable"] = live.index.astype(int).isin(free)
    live["last_year"] = live["last_row"].dt.year
    tab = live.groupby("last_year").agg(n=("nameable", "size"), nameable=("nameable", "sum"))
    tab["share"] = (100 * tab["nameable"] / tab["n"]).round(1)
    return tab.reset_index()


# ---------------------------------------------------------------------------
# R2 the key a caller actually holds
# ---------------------------------------------------------------------------
def r2_lookup(firm: pd.DataFrame, tix: dict) -> pd.DataFrame:
    """What a ticker lookup against the free file returns, three ways.

    The study's table 3 splits a ticker lookup two ways, present or not. A
    caller cannot tell those apart from the outside; what they can tell apart
    is the company they asked for, a different company, and nothing.
    """
    def outcome(ticker, cik) -> str:
        recs = tix.get(str(ticker).upper(), [])
        if not recs:
            return OUTCOMES[2]
        return OUTCOMES[0] if any(int(r["cik"]) == int(cik) for r in recs) else OUTCOMES[1]

    firm = firm.copy()
    firm["outcome"] = [outcome(r.ticker, cik) for cik, r in firm.iterrows()]
    tab = (pd.crosstab(firm["cohort"], firm["outcome"])
           .reindex(index=COHORTS, columns=OUTCOMES).fillna(0).astype(int))
    tab["n"] = tab.sum(axis=1)
    return tab


def r2_chart(tab: pd.DataFrame, vintage: str) -> Path:
    labels = ["still filing today",
              "stopped filing, no exit\nform on the record",
              "listing ended, dated by\na Form 25 or a Form 15"]
    colours = [charts.BRAND, charts.DOWN, "#dde2e8"]
    charts.theme()
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    for y, (cohort, label) in zip([2, 1, 0], zip(COHORTS, labels)):
        row, left = tab.loc[cohort], 0.0
        for name, colour in zip(OUTCOMES, colours):
            share = 100 * row[name] / row["n"]
            ax.barh(y, share, left=left, height=0.5, color=colour, edgecolor="none", zorder=2)
            if share >= 7:
                ax.text(left + share / 2, y, f"{share:.0f}%", ha="center", va="center",
                        fontsize=11, fontweight="semibold", zorder=3,
                        color=charts.INK2 if name == OUTCOMES[2] else "#ffffff")
            left += share
    ax.set_yticks([2, 1, 0])
    ax.set_yticklabels([f"{lab}\n{tab.loc[c, 'n']:,} companies"
                        for lab, c in zip(labels, COHORTS)], fontsize=9.5, color=charts.INK)
    ax.tick_params(axis="y", length=0, pad=10)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 2.5)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(charts.BASELINE)
    ax.grid(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colours]
    ax.legend(handles, OUTCOMES, loc="upper left", bbox_to_anchor=(-0.005, -0.13), ncol=3,
              frameon=False, fontsize=9.5, handlelength=1.2, handleheight=1.0,
              columnspacing=2.0, borderpad=0, handletextpad=0.6)
    charts._headline(
        fig,
        "Once a company's listing ends, the free SEC list drops it, and its old "
        "symbol points at someone else",
        "Every company is looked up by the stock symbol on its last set of accounts. The free "
        "list holds only the companies registered today, so a symbol a delisted company once "
        "used now points at whoever took it over, or at nothing at all.",
        bottom=0.235, left=0.275, right=0.985)
    CHARTS.mkdir(parents=True, exist_ok=True)
    path = CHARTS / "lookup-outcome.png"
    charts.save(fig, path,
                "Every US company filing 10-K or 10-Q accounts with the SEC since 2009, from the "
                f"Distill Markets point-in-time record of 2026-09-07; SEC company_tickers.json as "
                f"published {vintage}.")
    return path


# ---------------------------------------------------------------------------
# R3 the scope of the claim
# ---------------------------------------------------------------------------
def r3_submissions(firm: pd.DataFrame) -> tuple[pd.DataFrame, dict] | tuple[None, None]:
    path = OUT / "submissions.csv"
    if not path.exists():
        print(f"\nR3 skipped: {path} is not on disk. docs/data-sources.md has the fetch.")
        return None, None
    sub = pd.read_csv(path, low_memory=False)
    sub["named"] = sub["name"].fillna("").astype(str).str.len() > 0
    tab = (sub.groupby("listing_end_source")
           .agg(n=("named", "size"), named=("named", "sum")))
    tab["share"] = (100 * tab["named"] / tab["n"]).round(1)
    summary = {
        "asked": int(len(sub)),
        "named": int(sub["named"].sum()),
        "share_named": round(100 * sub["named"].mean(), 1),
        "errors": int((sub["error"].fillna("").astype(str).str.len() > 0).sum()),
        "carries_former_names": int((sub["n_former_names"] > 0).sum()),
        "still_lists_a_ticker": int((sub["sec_tickers"].fillna("").astype(str).str.len() > 0).sum()),
        "still_names_an_exchange": int((sub["sec_exchanges"].fillna("").astype(str).str.len() > 0).sum()),
    }
    return tab.reset_index(), summary


# ---------------------------------------------------------------------------
# R4 the sector cut, re-keyed
# ---------------------------------------------------------------------------
def r4_sector_key(df_path: Path, free: set[int]) -> pd.DataFrame:
    df = pd.read_csv(df_path, low_memory=False)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    hc = df[df["sector"].eq("Healthcare")]
    rows = []
    for key in ("ticker", "cik"):
        pool = hc.sort_values([key, "as_of_date"]).groupby(key).tail(1)
        pool = pool[pool["revenue"] >= HEALTHCARE_FLOOR].copy()
        pool["ended"] = pool["listed_until"].notna()
        pool["nameable"] = pool["cik"].isin(free)
        rows.append({"keyed_on": key, "firms": len(pool),
                     "still_listed": int((~pool["ended"]).sum()),
                     "ended": int(pool["ended"].sum()),
                     "nameable": int(pool["nameable"].sum()),
                     "still_listed_share": round(100 * pool.loc[~pool["ended"], "nameable"].mean(), 1),
                     "ended_share": round(100 * pool.loc[pool["ended"], "nameable"].mean(), 1)})
    return pd.DataFrame(rows)


def r4_terciles(df_path: Path, free: set[int]) -> pd.DataFrame:
    """The published tercile table, rebuilt on the CIK-keyed pool."""
    df = pd.read_csv(df_path, low_memory=False)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    hc = df[df["sector"].eq("Healthcare")].sort_values(["cik", "as_of_date"])
    pool = hc.groupby("cik").tail(1)
    pool = pool[pool["revenue"] >= HEALTHCARE_FLOOR].copy()
    pool["ended"] = pool["listed_until"].notna()
    pool["nameable"] = pool["cik"].isin(free)
    rows = []
    for ended, g in pool.groupby("ended"):
        cut = "with a listing end" if ended else "still listed"
        g = g.copy()
        g["tercile"] = pd.qcut(g["revenue"].rank(method="first"), 3,
                               labels=["small", "mid", "large"])
        rows.append({"cut": cut, "tercile": "all", "n": len(g),
                     "nameable": int(g["nameable"].sum())})
        for terc, cell in g.groupby("tercile", observed=True):
            rows.append({"cut": cut, "tercile": str(terc), "n": len(cell),
                         "nameable": int(cell["nameable"].sum())})
    tab = pd.DataFrame(rows)
    tab["share"] = (100 * tab["nameable"] / tab["n"]).round(1)
    return tab


# ---------------------------------------------------------------------------
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    firm, final, panel_name = firm_table()
    free = {int(k) for k in sec_tickers.index()}
    tix = sec_tickers.ticker_index()
    vintage = sec_tickers.vintage().isoformat()

    print(f"panel: {panel_name}, final snapshot {final.date()}, {len(firm):,} firms")
    print(f"free SEC file: {vintage}, {len(free):,} CIKs\n")

    print("R1 nameable by CIK, on three cohorts instead of two")
    t = r1_denominator(firm, free)
    print(t.to_string(index=False))
    t.to_csv(OUT / "r1_cohorts.csv", index=False)
    misses = r1_misses(firm, free)
    print(json.dumps(misses, indent=1))
    (OUT / "r1_misses.json").write_text(json.dumps(misses, indent=1))

    print("\nR1b the same pool, by the year of the firm's last panel row")
    t = r1_by_last_year(firm, free)
    print(t.to_string(index=False))
    t.to_csv(OUT / "r1_by_last_year.csv", index=False)

    print("\nR2 what a ticker lookup against the free file returns")
    tab = r2_lookup(firm, tix)
    print(tab.to_string())
    print((100 * tab[OUTCOMES].div(tab["n"], axis=0)).round(1).to_string())
    tab.to_csv(OUT / "r2_lookup.csv")
    print(f"chart: {r2_chart(tab, vintage)}")

    print("\nR3 does SEC's own free per-CIK submissions file name the dead")
    t, summary = r3_submissions(firm)
    if t is not None:
        print(t.to_string(index=False))
        print(json.dumps(summary, indent=1))
        t.to_csv(OUT / "r3_submissions_by_source.csv", index=False)
        (OUT / "r3_submissions.json").write_text(json.dumps(summary, indent=1))

    print("\nR4 the Healthcare pool, keyed on the ticker as published and on the CIK")
    t = r4_sector_key(client.panel_path(), free)
    print(t.to_string(index=False))
    t.to_csv(OUT / "r4_sector_key.csv", index=False)

    print("\nR4b the same pool keyed on the CIK, by revenue tercile")
    t = r4_terciles(client.panel_path(), free)
    print(t.to_string(index=False))
    t.to_csv(OUT / "r4_terciles.csv", index=False)


if __name__ == "__main__":
    main()
