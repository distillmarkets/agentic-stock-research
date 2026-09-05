"""The company passport: point-in-time fundamentals and the market's price on one timeline.

    python examples/passport.py NVDA

writes ``cache/passport_NVDA.png``: five panels on one shared date axis.

1. price      split-adjusted closes, log scale, with a tick for every filing
              that revised a prior annual fact, sized by facts changed
2. revenue    annual revenue as filed, bars at ``periodEnd``
3. margin     operating margin, on its own axis, never shared with revenue
4. shares     weighted-average diluted shares, split-basis flags ringed and
              annotated with the verdict ``joins.corroborate_flags`` returns
5. insider    open-market Form 4 transactions, value-sized ticks, with the
              window this corpus holds no Form 4 detail for shaded and dated

Everything is read through ``distill_toolkit.client`` (disk-cached, so a re-run
costs nothing) and ``distill_toolkit.stooq``. Chrome and colour come from
``distill_toolkit.charts``.

Three things this picture is built to make visible rather than hide, each of
which is a trap in ``docs/traps.md``:

* a revision is a **filing**, not a fact (trap 10). One annual report can recast
  dozens of facts, so the ticks are deduped on ``changedAccession``.
* a step in the diluted-share series is a **candidate** split, not a split
  (trap 14). Every flag is tested against the never-restated
  ``sharesOutstanding`` and drawn with its verdict, including "contradicted".
* Form 4 detail in this corpus starts recently whatever window is requested,
  and ``fromDate`` echoes the request rather than stating coverage (trap 11).
  The uncovered stretch is shaded, not left looking empty.

The passport can only be drawn for a company that still trades. That is the
point of ``findings/ghost-cohort.md``: about a third of December filer-years
have no series in a current-listings price file at all.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import dates as mdates
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from distill_toolkit import charts as C
from distill_toolkit import client, joins, stooq

HISTORY_YEARS = 20
INSIDER_WINDOW_DAYS = 3650
INSIDER_PAGE = 500

SOURCE = (
    "Distill Markets API: /sec/fundamentals/{t}/history (years=20), /sec/revisions/{t}, "
    "/sec/insider/{t} (windowDays=3650, paged at limit=500), /sec/profile/{t}. "
    "Prices: a US daily end-of-day bundle you hold, split-adjusted, price return only, "
    "current listings only. Fundamentals are as filed, latest filing wins; revision ticks "
    "are the filing that first reported a materially changed value."
)


# ---- geometry and date-axis marks -----------------------------------------
# Date-axis marks come from charts.date_bars and charts.date_ticks. Two pieces
# stay local, for reasons that are about this figure rather than about the
# module:
#
# * _stack is not charts.stack. charts.stack sizes its headline block for a
#   figure of ordinary height; this one is five panels on 13 inches with a long
#   two-line headline and a 150-character subtitle, and it wraps and places both
#   at its own point sizes. Passing that geometry through charts.stack would mean
#   adding parameters to the module for one caller.
# * _date_axis has no counterpart in charts, because choosing a year step from
#   the span is a decision about a specific x range rather than a mark.

def _stack(headline: str, subtitle: str, heights, size=(9.8, 13.0)):
    """A vertical stack of panels on one shared x axis, house-styled."""
    C.theme()
    fig, axes = plt.subplots(len(heights), 1, figsize=size, sharex=True,
                             gridspec_kw={"height_ratios": list(heights)})
    axes = list(np.atleast_1d(axes))
    import textwrap
    h = size[1]
    head = C.escape("\n".join(textwrap.wrap(headline, 96)))
    fig.text(0.012, 1 - 0.28 / h, head, ha="left", va="top", fontsize=12.5,
             fontweight="semibold", color=C.INK, linespacing=1.25)
    used = 0.28 + 0.20 * (head.count("\n") + 1)
    sub = C.escape("\n".join(textwrap.wrap(subtitle, 150)))
    fig.text(0.012, 1 - (used + 0.06) / h, sub, ha="left", va="top",
             fontsize=9.0, color=C.INK2, linespacing=1.3)
    used += 0.06 + 0.16 * (sub.count("\n") + 1)
    fig.subplots_adjust(top=1 - (used + 0.62) / h, bottom=1.15 / h,
                        left=0.095, right=0.975, hspace=0.60)
    for ax in axes:
        ax.grid(axis="y")
        ax.tick_params(length=0)
    return fig, axes


def _nums(dates) -> np.ndarray:
    return mdates.date2num([pd.Timestamp(d).to_pydatetime() for d in dates])


def _date_axis(ax, lo, hi) -> None:
    """Year ticks sized so they do not collide at this span."""
    ax.set_xlim(mdates.date2num(lo), mdates.date2num(hi))
    span_years = (hi - lo).days / 365.25
    step = 1 if span_years <= 9 else (2 if span_years <= 18 else 4)
    ax.xaxis.set_major_locator(mdates.YearLocator(step))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


# ---- data -----------------------------------------------------------------
def fetch(ticker: str) -> dict:
    """Every response the passport needs. Cached, so a second run makes no call."""
    pages = list(client.get_paged(f"/api/v1/sec/insider/{ticker}",
                                  limit=INSIDER_PAGE, windowDays=INSIDER_WINDOW_DAYS))
    transactions = [t for page in pages for t in page.get("transactions", [])]
    summary = {k: v for k, v in pages[-1].items() if k != "transactions"}
    return {
        "profile": client.get(f"/api/v1/sec/profile/{ticker}"),
        "history": client.get(f"/api/v1/sec/fundamentals/{ticker}/history", years=HISTORY_YEARS),
        "revisions": client.get(f"/api/v1/sec/revisions/{ticker}"),
        "insider_tx": transactions,
        "insider_summary": summary,
    }


def fundamentals_frame(history: dict) -> pd.DataFrame:
    """One row per fiscal year, oldest first, keyed on ``periodEnd``."""
    rows = [{
        "fiscal_year": int(y["fiscalYear"]),
        "period_end": pd.Timestamp(y["periodEnd"]),
        "revenue": y.get("revenue"),
        "operating_margin": y.get("operatingMargin"),
        "diluted_shares": y.get("weightedAverageSharesDiluted"),
        "shares_outstanding": y.get("sharesOutstanding"),
    } for y in history["years"]]
    return pd.DataFrame(rows).sort_values("period_end").reset_index(drop=True)


def revising_filings(revisions: dict) -> pd.DataFrame:
    """One row per REVISING FILING, never per fact. See docs/traps.md trap 10.

    ``/sec/revisions`` returns one row per revised fact and a single annual
    report can recast dozens, so counting rows counts filings many times over:
    over 707 tickers, 10,878 facts arrive in 2,552 filings, an inflation of
    4.26x. Dedupe on ``changedAccession``, falling back to ``changedFiled``.
    """
    by_filing: dict[tuple, dict] = defaultdict(lambda: {"facts": 0, "types": set()})
    for r in revisions.get("revisions", []):
        filed = r.get("changedFiled")
        if not filed:
            continue
        entry = by_filing[(r.get("changedAccession") or filed, filed)]
        entry["facts"] += 1
        entry["types"].add(r.get("changeType"))
    rows = [{"accession": k[0], "filed": pd.Timestamp(k[1]), "facts": v["facts"],
             "change_types": "/".join(sorted(t for t in v["types"] if t))}
            for k, v in by_filing.items()]
    cols = ["accession", "filed", "facts", "change_types"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows).sort_values("filed").reset_index(drop=True)


def open_market_frame(transactions: list) -> pd.DataFrame:
    """Non-derivative open-market purchases (code ``P``) and sales (code ``S``).

    ``M`` option-exercise rows appear twice, once derivative and once not, and
    ``A`` grants and ``F`` tax withholdings are not market transactions at all,
    so the code filter is doing real work. A row with no ``value`` is dropped
    rather than plotted at zero.
    """
    rows = []
    for t in transactions:
        if t.get("code") not in ("P", "S") or t.get("isDerivative"):
            continue
        value = t.get("value")
        if not value:
            continue
        rows.append({"date": pd.Timestamp(t["transactionDate"]),
                     "side": "purchase" if t["code"] == "P" else "sale",
                     "value": float(value)})
    cols = ["date", "side", "value"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def share_flags(fund: pd.DataFrame) -> list[tuple[int, float, float]]:
    series = {int(r.fiscal_year): r.diluted_shares for r in fund.itertuples()
              if r.diluted_shares and not pd.isna(r.diluted_shares)}
    return joins.split_basis_flags(series)


def _clean(fund: pd.DataFrame, col: str) -> dict[int, float]:
    """``{fiscal_year: value}`` with nulls dropped, which the sanity check needs."""
    d = fund.dropna(subset=[col])
    return {int(r.fiscal_year): float(getattr(r, col)) for r in d.itertuples()}


def first_insider_date(transactions: list) -> pd.Timestamp | None:
    """The oldest transaction actually returned.

    ``fromDate`` on the response echoes the requested window and says nothing
    about coverage: it comes back as a date years before the oldest row the
    corpus holds. The only way to learn the coverage floor is to read this.
    """
    if not transactions:
        return None
    return min(pd.Timestamp(t["transactionDate"]) for t in transactions)


# ---- headline -------------------------------------------------------------
def facts(ticker: str, data: dict) -> dict:
    """Every number the headline quotes, computed once, stated as filed."""
    fund = fundamentals_frame(data["history"])
    rev = fund.dropna(subset=["revenue"])
    filings = revising_filings(data["revisions"])
    closes = stooq.closes(ticker)
    flags = share_flags(fund)
    summary = data["insider_summary"]

    f = {
        "ticker": ticker,
        "name": data["profile"]["name"],
        "cik": data["profile"]["cikNumber"],
        "fy_first": int(rev.fiscal_year.iloc[0]),
        "fy_last": int(rev.fiscal_year.iloc[-1]),
        "rev_multiple": float(rev.revenue.iloc[-1] / rev.revenue.iloc[0]),
        "fiscal_years": int(len(fund)),
        "revised_facts": int(len(data["revisions"].get("revisions", []))),
        "revising_filings": int(len(filings)),
        "ticker_ambiguous": bool(data["revisions"].get("tickerAmbiguous")),
        "corroboration": joins.corroborate_flags(data["history"]["years"], flags),
        "shares_years_covered": int(fund.diluted_shares.notna().sum()),
        "insider_buys": int(summary.get("openMarketBuys") or 0),
        "insider_sells": int(summary.get("openMarketSells") or 0),
        "insider_first_tx": first_insider_date(data["insider_tx"]),
        "insider_coverage_note": bool(summary.get("coverageNote")),
        "priced": closes is not None,
        "price_multiple": None,
        "price_window_covered": False,
        "price_gap_years": None,
    }
    # The two share series disagreeing by more than a factor of two is either a
    # split basis break (traps 1 and 2: the diluted count is restated two fiscal
    # years back and the outstanding count is never restated) or one count
    # carried in the wrong unit (trap 13). Classify rather than pool:
    # a year inside the restatement window of a corroborated split flag is the
    # first, and a ratio in the hundreds is the second.
    split_years = {y for c in f["corroboration"] if c["corroborated"]
                   for y in range(c["flag_year"], c["flag_year"] + 3)}
    f["share_disagreements"] = [
        dict(row, cause="split basis" if row["fiscal_year"] in split_years else "check units")
        for row in joins.share_series_sanity(_clean(fund, "shares_outstanding"),
                                             _clean(fund, "diluted_shares"))
    ]
    f["share_unit_flags"] = [r for r in f["share_disagreements"] if r["cause"] == "check units"]
    if closes is not None:
        p0d, p1d = rev.period_end.iloc[0], rev.period_end.iloc[-1]
        if closes.index[0] <= p0d:
            f["price_multiple"] = float(closes.loc[:p1d].iloc[-1] / closes.loc[:p0d].iloc[-1])
            f["price_window_covered"] = True
        else:
            f["price_gap_years"] = round((closes.index[0] - p0d).days / 365.25, 1)
    return f


def headline(f: dict) -> str:
    """A factual one-liner: what the filings say, never what it means."""
    parts = [f"revenue {f['rev_multiple']:.1f}x FY{f['fy_first']} to FY{f['fy_last']}"]
    if f["price_window_covered"]:
        parts.append(f"price {f['price_multiple']:.1f}x over the same dates")
    elif f["priced"]:
        parts.append(f"price series starts {f['price_gap_years']:.0f} years into that window")
    else:
        parts.append("no price series in this bundle")
    if f["revising_filings"]:
        parts.append(f"{f['revising_filings']} filings revised {f['revised_facts']} annual facts")
    else:
        parts.append("no annual fact revised by 1% or more")
    return f"{f['name']} ({f['ticker']}): " + "; ".join(parts) + "."


def subtitle(f: dict) -> str:
    bits = [f"CIK {f['cik']}", f"{f['fiscal_years']} fiscal years on file",
            f"diluted-share count on file for {f['shares_years_covered']}"]
    for c in f["corroboration"]:
        bits.append(f"FY{c['flag_year']} diluted-share step x{c['diluted_ratio']:.2f} "
                    f"{c['verdict']} by sharesOutstanding")
    if f["share_unit_flags"]:
        years = ", ".join(f"FY{r['fiscal_year']}" for r in f["share_unit_flags"])
        bits.append(f"share counts disagree beyond a corporate action at {years}")
    bits.append(f"Form 4 detail in this corpus begins {f['insider_first_tx'].date()}"
                if f["insider_first_tx"] is not None else "no Form 4 detail")
    if f["insider_coverage_note"]:
        bits.append("issuer carries a coverageNote, so insider counts are a lower bound")
    if f["ticker_ambiguous"]:
        bits.append("tickerAmbiguous is true for this ticker")
    return " · ".join(bits)


# ---- panels ---------------------------------------------------------------
def _price_panel(ax, closes, filings, lo, hi):
    C.label(ax, "Price, log scale",
            "split-adjusted closes, price return only. Amber ticks: filings that revised a "
            "prior annual fact, height = facts changed")
    if closes is None:
        ax.text(0.5, 0.5, "no series in this price bundle", transform=ax.transAxes,
                ha="center", color=C.MUTED)
        return
    s = closes.loc[lo:hi]
    ax.plot(_nums(s.index), s.values, color=C.BRAND, lw=1.5, zorder=3)
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0, 2.0, 5.0), numticks=14))
    ax.yaxis.set_minor_locator(LogLocator(base=10.0, subs=np.arange(2, 10) * 0.1, numticks=100))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 1 else f"{v:g}"))
    ax.set_ylabel("close", fontsize=9, color=C.INK2)
    lo_y, hi_y = ax.get_ylim()
    ax.set_ylim(lo_y / 1.9, hi_y)
    lo_y, hi_y = ax.get_ylim()
    if not len(filings):
        return
    span = math.log10(hi_y / lo_y)
    biggest = filings.facts.max()
    inside = filings[(filings.filed >= lo) & (filings.filed <= hi)]
    for r in inside.itertuples():
        frac = 0.03 + 0.16 * (r.facts / biggest)
        ax.vlines(_nums([r.filed]), lo_y, lo_y * 10 ** (span * frac),
                  color=C.AMBER, lw=1.6, zorder=4)
    for r in inside.sort_values("facts", ascending=False).head(2).itertuples():
        frac = 0.03 + 0.16 * (r.facts / biggest)
        ax.annotate(f"{r.filed.date()}\n{r.facts} fact" + ("" if r.facts == 1 else "s"),
                    (_nums([r.filed])[0], lo_y * 10 ** (span * frac)),
                    xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                    fontsize=7.5, color=C.AMBER)


def _revenue_panel(ax, fund):
    C.label(ax, "Revenue as filed",
            "annual, bar at fiscal period end; latest filing wins on restatement")
    d = fund.dropna(subset=["revenue"])
    C.date_bars(ax, d.period_end.to_numpy(), (d.revenue / 1e9).to_numpy(),
                width_days=230.0)
    ax.set_ylabel("$bn", fontsize=9, color=C.INK2)
    C.finish(ax)


def _margin_panel(ax, fund):
    C.label(ax, "Operating margin", "own axis, never shared with revenue")
    d = fund.dropna(subset=["operating_margin"])
    if len(d):
        ax.plot(_nums(d.period_end), d.operating_margin * 100, color=C.TEAL,
                lw=1.7, marker="o", ms=3.2, zorder=3)
    C.finish(ax, "%", pct=True)


def _shares_panel(ax, fund, flags, corroboration):
    C.label(ax, "Weighted-average diluted shares",
            "as filed; a step at an integer factor is a candidate split-basis break, "
            "confirmed against the never-restated sharesOutstanding")
    d = fund.dropna(subset=["diluted_shares"])
    if len(d):
        ax.plot(_nums(d.period_end), d.diluted_shares / 1e6, color=C.BRAND_LIGHT,
                lw=1.5, marker="o", ms=2.8, zorder=3)
    corr = {c["flag_year"]: c for c in corroboration}
    for year, ratio, factor in flags:
        c = corr.get(year, {})
        colour = C.DOWN if c.get("corroborated") else C.INK2
        note = (f"FY{year} x{ratio:.2f}\nsplit basis break ({factor:g}:1)"
                if c.get("corroborated") else
                f"FY{year} x{ratio:.2f}\nflagged, {c.get('verdict', 'untestable')}")
        row = d[d.fiscal_year == year]
        if row.empty:
            continue
        x = _nums([row.period_end.iloc[0]])[0]
        y = row.diluted_shares.iloc[0] / 1e6
        ax.scatter([x], [y], s=46, facecolor="none", edgecolor=colour, linewidth=1.4, zorder=5)
        y0, y1 = ax.get_ylim()
        above = (y - y0) / (y1 - y0) < 0.5
        ax.annotate(note, (x, y), xytext=(6, 5 if above else -3), textcoords="offset points",
                    fontsize=7.5, color=colour, va="bottom" if above else "top")
    ax.set_ylabel("millions", fontsize=9, color=C.INK2)
    C.finish(ax)


def _insider_panel(ax, om, lo, hi, first_tx):
    C.label(ax, "Open-market insider transactions",
            "Form 4 codes P and S, non-derivative; tick height = transaction value. "
            "Dates are transaction dates, and the filing follows within two business days")
    if first_tx is not None and first_tx > lo:
        ax.axvspan(mdates.date2num(lo.to_pydatetime()),
                   mdates.date2num(first_tx.to_pydatetime()),
                   color=C.BRAND_WASH, zorder=0, lw=0)
        ax.text(0.012, 0.90, f"no Form 4 detail in this corpus before {first_tx.date()}",
                transform=ax.transAxes, fontsize=8, color=C.INK2, va="top", ha="left", zorder=6)
    up = om[(om.side == "purchase") & om.date.between(lo, hi)]
    down = om[(om.side == "sale") & om.date.between(lo, hi)]
    C.date_ticks(ax, up.date.to_numpy(), (up.value / 1e6).to_numpy(), color=C.UP, lw=1.6)
    C.date_ticks(ax, down.date.to_numpy(), (-down.value / 1e6).to_numpy(), color=C.DOWN, lw=1.0)
    ax.set_ylabel("$m  (purchases up / sales down)", fontsize=9, color=C.INK2)
    if not len(up) and not len(down):
        ax.text(0.5, 0.5, "no open-market transactions in the covered window",
                transform=ax.transAxes, ha="center", color=C.MUTED, fontsize=9)
    ax.text(0.012, 0.06, f"{len(up)} open-market purchases, {len(down)} sales plotted",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=8, color=C.MUTED)
    C.finish(ax)


# ---- entry point ----------------------------------------------------------
def passport(ticker: str, out_path: str | Path) -> dict:
    """Render the passport for ``ticker`` to ``out_path``. Returns the fact dict."""
    data = fetch(ticker)
    f = facts(ticker, data)
    fund = fundamentals_frame(data["history"])
    filings = revising_filings(data["revisions"])
    om = open_market_frame(data["insider_tx"])
    closes = stooq.closes(ticker)
    flags = share_flags(fund)

    # Window: show the seam where the two sources start, and never more than two
    # years of price history before the first filed fiscal year. When the price
    # series starts after the first filed year the gap is left visible, because
    # that gap is the point.
    fund_start = fund.period_end.min()
    lo = fund_start
    if closes is not None and closes.index[0] < fund_start:
        lo = max(closes.index[0], fund_start - pd.Timedelta(730, "D"))
    hi = max([fund.period_end.max()] + ([closes.index[-1]] if closes is not None else []))
    lo, hi = lo - pd.Timedelta(120, "D"), hi + pd.Timedelta(120, "D")

    fig, axes = _stack(headline(f), subtitle(f), heights=(3.2, 1.35, 1.15, 1.15, 1.35))
    _price_panel(axes[0], closes, filings, lo, hi)
    _revenue_panel(axes[1], fund)
    _margin_panel(axes[2], fund)
    _shares_panel(axes[3], fund, flags, f["corroboration"])
    _insider_panel(axes[4], om, lo, hi, f["insider_first_tx"])
    for ax in axes:
        _date_axis(ax, lo, hi)
    C.save(fig, str(out_path), SOURCE)
    return f


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[0])
        print("usage: python examples/passport.py TICKER [OUT.png]")
        return 2
    ticker = argv[1].upper()
    out = Path(argv[2]) if len(argv) > 2 else client.CACHE_DIR / f"passport_{ticker}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    f = passport(ticker, out)
    print(headline(f))
    print(f"  {f['revising_filings']} revising filings carrying {f['revised_facts']} facts "
          f"({f['revised_facts'] / f['revising_filings']:.2f} facts per filing)"
          if f["revising_filings"] else "  no revising filings")
    for c in f["corroboration"]:
        print(f"  FY{c['flag_year']} diluted-share step x{c['diluted_ratio']:.2f} "
              f"({c['factor']:g}:1): {c['verdict']}")
    for r in f["share_disagreements"]:
        note = ("consistent with the split basis break above (docs/traps.md traps 1 and 2)"
                if r["cause"] == "split basis"
                else "check the served units before any per-share arithmetic "
                     "(docs/traps.md trap 13)")
        print(f"  FY{r['fiscal_year']}: sharesOutstanding / diluted = {r['ratio']:,.2f}x, {note}")
    if f["insider_first_tx"] is not None:
        print(f"  oldest Form 4 transaction returned: {f['insider_first_tx'].date()}")
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
