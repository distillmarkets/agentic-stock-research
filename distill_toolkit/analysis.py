"""Shared study helpers: forward price paths, event windows, survival curves, sector benchmarks.

These exist so that every study computes the same thing the same way. All of
them take data you already hold (the panel export and a Stooq bundle) and
return aggregates or per-row frames that stay on your disk.

Conventions used throughout:

* A *firm-year* is one December snapshot of one CIK in the point-in-time panel.
* *Market-adjusted* means minus the same-entry-year median across every priced
  firm, so it is relative to the matched universe, not to an index.
* Returns are price returns from split-adjusted closes and omit dividends.
* Only firms with a Stooq series are priced; ``match_rate`` reports the share
  that are, and every study must print it (see docs/traps.md, trap 3).
* A firm-year repeats by firm. Any interval or placebo over these frames
  resamples or permutes whole CIKs, never rows: ``cluster_bootstrap`` and
  ``clustered_shuffle`` are the two that do it.
"""

from __future__ import annotations

import itertools
import json
import math
import warnings
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from . import client, stooq

SECTOR_ETF = {
    "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF", "Energy": "XLE",
    "Industrials": "XLI", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Utilities": "XLU", "Materials": "XLB", "Real Estate": "XLRE", "Communication Services": "XLC",
}

# Days a close may be stale relative to an event date before the event is dropped.
MAX_GAP_DAYS = 7


def december_snapshots(panel: pd.DataFrame, years: tuple[int, int] = (2010, 2025)) -> pd.DataFrame:
    """Listed, revenue-positive December rows with an unambiguous ticker, plus ``year``."""
    multi = panel.groupby("ticker").cik.nunique()
    collided = set(multi[multi > 1].index)
    dec = panel[(panel.as_of_date.dt.month == 12) & panel.is_listed_equity & (panel.revenue > 0)
                & ~panel.ticker.isin(collided)].copy()
    dec["year"] = dec.as_of_date.dt.year
    return dec[dec.year.between(*years)]


def match_rate(dec: pd.DataFrame) -> float:
    """Share of firm-years that have a Stooq series. Print this in every study."""
    idx = stooq.index()
    return float(dec.ticker.map(lambda t: stooq.stooq_key(t) in idx).mean())


def priced_flags(dec: pd.DataFrame) -> pd.Series:
    """Per-row: the ticker has a series in the bundle at all.

    This is nominal coverage. A symbol present in a current-listings bundle says
    nothing about whether it carries a close near any particular snapshot date,
    which is what a price study needs; ``fresh_close_flags`` is that test. The
    complement of this flag is the cohort no price-based result can see, and it
    is not missing at random: a bundle of current listings drops a delisted
    issuer outright rather than ending its series.
    """
    idx = stooq.index()
    return dec.ticker.map(lambda t: stooq.stooq_key(t) in idx).astype(bool)


def fresh_close_flags(dec: pd.DataFrame, max_stale_days: int = 14) -> pd.Series:
    """Per-row: a close exists within ``max_stale_days`` before the snapshot date.

    This is the entry test ``forward_paths`` applies, so it is the coverage a
    price study actually gets rather than the coverage the symbol list promises.
    Report it next to ``priced_flags``: nominal against usable.
    """
    priced = priced_flags(dec)
    fresh: dict[tuple, bool] = {}
    for t, g in dec[priced].groupby("ticker"):
        c = stooq.closes(t)
        if c is None or len(c) < 30:
            for r in g.itertuples():
                fresh[(r.cik, r.year)] = False
            continue
        for r in g.itertuples():
            before = c.index[c.index <= r.as_of_date]
            fresh[(r.cik, r.year)] = bool(
                len(before) and (r.as_of_date - before.max()).days <= max_stale_days)
    return pd.Series([fresh.get((c, y), False) for c, y in zip(dec.cik, dec.year)],
                     index=dec.index)


def transitions(dec: pd.DataFrame, gap_years: int) -> pd.DataFrame:
    """Firm-years joined to their snapshot ``gap_years`` later, one row per pair.

    The join is on CIK, and a pair only counts when the later snapshot cites a
    fiscal year at least ``gap_years`` newer than the earlier one. Without that
    guard a snapshot that has not yet been refreshed by a new filing joins to
    itself and produces a transition in which nothing happened. Later columns
    carry the ``_next`` suffix; ``base_year`` is the earlier snapshot's year.
    """
    years = sorted(dec.year.unique())
    out = []
    for y in years:
        if y + gap_years not in years:
            continue
        cur = dec[dec.year == y].set_index("cik")
        nxt = dec[dec.year == y + gap_years].set_index("cik")
        j = cur.join(nxt, rsuffix="_next", how="inner")
        j = j[j.fiscal_year_next >= j.fiscal_year + gap_years]
        j["base_year"] = y
        out.append(j)
    if not out:
        return pd.DataFrame(columns=list(dec.columns) + ["base_year"])
    return pd.concat(out).reset_index()


#: Outcome columns ``add_outcomes`` derives, as ``(new column, base column, kind)``.
OUTCOMES = (
    ("d_opm", "operating_margin", "diff"),
    ("d_netm", "net_margin", "diff"),
    ("d_health", "health_score", "diff"),
    ("rev_growth", "revenue", "growth"),
)


def add_outcomes(pairs: pd.DataFrame, drop_absurd_margins: bool = True) -> pd.DataFrame:
    """Add the forward changes a transition study asks for, for whichever pairs exist.

    ``d_*`` are differences (next minus base) and ``rev_growth`` is a ratio minus
    one. A column is only added when both it and its ``_next`` partner are
    present, so the same call works on an export that carries no health score.

    ``drop_absurd_margins`` removes rows whose operating margin is outside
    +/-100%. A margin that large is a units or a tiny-denominator artefact
    rather than a firm, and one such row moves a cohort median. The filter
    applies to ``operating_margin_next`` as well: the outcome of a transition is
    the next-year value, so filtering only the base leaves the artefact in the
    column the study actually reads.
    """
    out = pairs
    if drop_absurd_margins:
        for col in ("operating_margin", "operating_margin_next"):
            if col in out.columns:
                out = out[out[col].abs() < 1]
    out = out.copy()
    for name, base, kind in OUTCOMES:
        nxt = f"{base}_next"
        if base not in out.columns or nxt not in out.columns:
            continue
        out[name] = (out[nxt] - out[base]) if kind == "diff" else (out[nxt] / out[base] - 1)
    return out


def forward_paths(dec: pd.DataFrame, horizons: int = 24, keep: Sequence[str] = ()) -> pd.DataFrame:
    """One row per priced firm-year with ``r_1..r_H``: cumulative price return at monthly horizons.

    Entry is the last close on or before the snapshot date, rejected if older
    than 14 days (a stale print from a name about to delist). Horizons past the
    end of the series plus 45 days are NaN. ``delisted_in_window`` marks series
    that ended before the last horizon. Adds ``x_1..x_H`` market-adjusted columns.

    ``delisted_in_window`` is a statement about the file, not about the company:
    a current-listings bundle deletes a delisted symbol instead of ending its
    series, so on such a bundle the flag fires on exactly the entry years whose
    last horizon sits past the file's right edge. A ``listed_until`` column on
    ``dec`` (the export carries one per firm) is the statement about the
    company: no return is read past it, and the flag is set from it, because a
    symbol is reused and a series that runs on past a firm's listing end is
    quoting whoever holds the symbol now.

    A close is found by ``numpy.searchsorted`` on the ticker's own date array,
    once per horizon for the whole ticker, rather than by reindexing the series
    onto a per-row grid. A reindex is linear in the length of the price series
    and a search is logarithmic in it, and the universe carries thousands of
    rows per long series.
    """
    idx = stooq.index()
    dec = dec[dec.ticker.map(lambda t: stooq.stooq_key(t) in idx)]
    rows = []
    for t, g in dec.groupby("ticker"):
        c = stooq.closes(t)
        if c is None or len(c) < 30:
            continue
        ci, cv = c.index.to_numpy(), c.to_numpy(dtype=float)
        last = c.index[-1]
        end = (pd.to_datetime(g.listed_until).to_numpy() if "listed_until" in g.columns
               else np.full(len(g), np.datetime64("NaT", "ns")))
        anchors = pd.DatetimeIndex(g.as_of_date)
        av = anchors.to_numpy()
        j0 = np.searchsorted(ci, av, side="right") - 1
        fresh = j0 >= 0
        stale = np.full(len(g), np.iinfo(np.int64).max, dtype=np.int64)
        stale[fresh] = (av[fresh] - ci[j0[fresh]]) // np.timedelta64(1, "D")
        ok = fresh & (stale <= 14)
        p0 = np.where(ok, cv[np.clip(j0, 0, len(cv) - 1)], np.nan)
        ok &= p0 > 0
        if not ok.any():
            continue
        g, anchors, p0, end = g[ok], anchors[ok], p0[ok], end[ok]
        edge = np.datetime64(last) + np.timedelta64(45, "D")
        path = np.empty((len(g), horizons + 1), dtype=float)
        grid = av[ok]
        for k in range(horizons + 1):
            grid = (anchors + pd.DateOffset(months=k)).to_numpy()
            jk = np.searchsorted(ci, grid, side="right") - 1
            px = np.where(jk >= 0, cv[np.clip(jk, 0, len(cv) - 1)], np.nan)
            col = px / p0 - 1
            col[(grid > edge) | (grid > end)] = np.nan
            path[:, k] = col
        ended = (grid > np.datetime64(last)) | (grid > end)
        for i, r in enumerate(g.itertuples()):
            row = {"cik": r.cik, "ticker": t, "year": r.year, "as_of_date": r.as_of_date,
                   "delisted_in_window": bool(ended[i])}
            row.update({k: getattr(r, k) for k in keep})
            row.update({f"r_{k}": path[i, k] for k in range(1, horizons + 1)})
            rows.append(row)
    out = pd.DataFrame(rows)
    adjusted = market_adjust_by(out, [f"r_{k}" for k in range(1, horizons + 1)], by="year")
    for k in range(1, horizons + 1):
        out[f"x_{k}"] = adjusted[f"r_{k}"]
    return out


def event_window(closes: pd.Series, day, offsets: Sequence[int] = (1, 5, 20),
                 max_gap_days: int = MAX_GAP_DAYS) -> dict | None:
    """Price return from the last close before ``day`` to ``offsets`` trading days after it.

    ``None`` when there is no fresh close before the event or too few after it.
    Subtract the same window on SPY (or a sector ETF) for an abnormal return.
    """
    t = pd.Timestamp(day)
    pre = closes.loc[:t - pd.Timedelta(days=1)]
    if pre.empty or (t - pre.index[-1]).days > max_gap_days:
        return None
    post = closes.loc[t:]
    if len(post) <= max(offsets):
        return None
    p0 = pre.iloc[-1]
    return {f"ar_{o}": float(post.iloc[o] / p0 - 1) for o in offsets}


def abnormal_window(ticker: str, day, benchmark: str = "SPY", offsets: Sequence[int] = (1, 5, 20)) -> dict | None:
    """``event_window`` for a ticker minus the same window on a benchmark series."""
    c, b = stooq.closes(ticker), stooq.closes(benchmark)
    if c is None or b is None:
        return None
    w, wb = event_window(c, day, offsets), event_window(b, day, offsets)
    if not w or not wb:
        return None
    return {k: w[k] - wb[k] for k in w}


# ---- event-time paths -----------------------------------------------------
def _event_path(closes: pd.Series, day: pd.Timestamp, lo: int, hi: int,
                max_gap_days: int = MAX_GAP_DAYS) -> np.ndarray | None:
    """Cumulative return over trading days ``lo``..``hi`` around ``day``, or ``None``.

    The base price is the last close strictly before ``day`` and offset 0 is the
    first close on or after it, which is ``event_window``'s convention at every
    positive offset. Negative offsets walk back through the closes before the
    base, so day -1 is the base close itself. Offsets with no close are NaN.
    """
    pre = closes.loc[: day - pd.Timedelta(days=1)]
    if pre.empty or (day - pre.index[-1]).days > max_gap_days:
        return None
    p0 = float(pre.iloc[-1])
    if not p0 or p0 <= 0:
        return None
    post = closes.loc[day:]
    out = np.full(hi - lo + 1, np.nan)
    pre_v, post_v = pre.to_numpy(), post.to_numpy()
    for k in range(lo, hi + 1):
        if k < 0:
            i = len(pre_v) + k
            if i >= 0:
                out[k - lo] = pre_v[i] / p0 - 1
        elif k < len(post_v):
            out[k - lo] = post_v[k] / p0 - 1
    return out


def abnormal_path(ticker: str, day, lo: int, hi: int, benchmark: str = "SPY",
                  max_gap_days: int = MAX_GAP_DAYS) -> np.ndarray | None:
    """Market-adjusted cumulative return over event time, from day ``lo`` to day ``hi``.

    ``lo`` may be negative: the run-up into an event is often the whole finding,
    and ``event_window``/``abnormal_window`` can only look forward. Returns one
    value per trading day offset, the ticker's cumulative return minus the
    benchmark's over the same offsets, or ``None`` when either leg has no fresh
    close before the event.

    The benchmark is put on the ticker's own trading days before event time is
    walked, as ``path_between`` does. Two symbols do not share a trading-day
    grid: a halt, a late listing or a missing bar shifts one leg against the
    other, and offset ``k`` then subtracts a different calendar date on each
    side. Aligning by date first makes the difference an abnormal return rather
    than a return over two slightly different windows.
    """
    c, b = stooq.closes(ticker), stooq.closes(benchmark)
    if c is None or b is None:
        return None
    day = pd.Timestamp(day)
    bb = b.reindex(b.index.union(c.index)).ffill().reindex(c.index).dropna()
    if bb.empty:
        return None
    pc = _event_path(c, day, lo, hi, max_gap_days)
    pb = _event_path(bb, day, lo, hi, max_gap_days)
    if pc is None or pb is None:
        return None
    return pc - pb


def path_between(ticker: str, d0, d1, benchmark: str = "SPY", points: int = 10,
                 post_days: int = 20, min_trading_days: int = 20,
                 max_gap_days: int = MAX_GAP_DAYS) -> dict | None:
    """Abnormal log path from ``d0`` to ``d1``, then ``post_days`` past ``d1``.

    Two events per firm sit an arbitrary and firm-specific number of trading
    days apart, so a fixed offset grid cannot compare them. This samples the
    between-window at ``points`` equal fractions of the trading days it contains,
    which puts every firm on one axis whatever its own spacing, and continues on
    a fixed daily grid after ``d1`` where the spacing is the same for everyone.

    Log returns, minus the benchmark's over the same span, so the two legs
    ``pre`` and ``post`` add to ``total``. Returns ``ntd`` (trading days between
    the anchors), ``p_1..p_points``, ``q_1..q_post_days``, ``pre20`` (the 20
    trading days ending at ``d1``), ``pre``, ``post`` and ``total``; ``None``
    when either anchor lacks a close within ``max_gap_days`` or the anchors are
    closer than ``min_trading_days`` apart.
    """
    c, b = stooq.closes(ticker), stooq.closes(benchmark)
    if c is None or b is None or len(c) < 60:
        return None
    d0, d1 = pd.Timestamp(d0), pd.Timestamp(d1)
    pre0 = c.index[c.index <= d0]
    if len(pre0) == 0 or (d0 - pre0[-1]).days > max_gap_days:
        return None
    pre1 = c.index[c.index < d1]
    if len(pre1) == 0 or (d1 - pre1[-1]).days > max_gap_days:
        return None
    i0, i1 = c.index.get_loc(pre0[-1]), c.index.get_loc(pre1[-1])
    if i1 - i0 < min_trading_days:
        return None
    bb = b.reindex(b.index.union(c.index)).ffill().reindex(c.index)
    if np.isnan(bb.iloc[i0]) or np.isnan(bb.iloc[i1]):
        return None
    lc, lb = np.log(c.to_numpy()), np.log(bb.to_numpy())
    out: dict[str, float] = {"ntd": float(i1 - i0)}
    for k in range(1, points + 1):
        j = i0 + int(round(k / points * (i1 - i0)))
        out[f"p_{k}"] = (lc[j] - lc[i0]) - (lb[j] - lb[i0])
    for k in range(1, post_days + 1):
        j = i1 + k
        out[f"q_{k}"] = ((lc[j] - lc[i1]) - (lb[j] - lb[i1])
                         if j < len(lc) and not np.isnan(lb[j]) else np.nan)
    j = i1 - 20
    out["pre20"] = ((lc[i1] - lc[j]) - (lb[i1] - lb[j])) if j >= 0 and not np.isnan(lb[j]) else np.nan
    out["pre"] = out[f"p_{points}"]
    out["post"] = out[f"q_{post_days}"]
    out["total"] = out["pre"] + out["post"]
    return out


# ---- survival -------------------------------------------------------------
def failure_times(mat: np.ndarray, thresh: float = -0.5) -> tuple[np.ndarray, np.ndarray]:
    """``(failure month, last observed month)`` per row of a path matrix.

    The failure month is the first column at or below ``thresh``, one-based, and
    NaN when the row never reaches it. The last observed month is the last
    non-NaN column, 0 for a row with no data at all. A row's observed window is
    assumed to be a prefix: values up to some month, NaN after.
    """
    mat = np.asarray(mat, dtype=float)
    hit = np.nan_to_num(mat, nan=np.inf) <= thresh
    fail = np.where(hit.any(1), hit.argmax(1) + 1, np.nan).astype(float)
    obs = ~np.isnan(mat)
    last = np.where(obs.any(1), mat.shape[1] - obs[:, ::-1].argmax(1), 0).astype(float)
    return fail, last


def kaplan_meier(fail: np.ndarray, last: np.ndarray, horizons: int = 24) -> pd.DataFrame:
    """Kaplan-Meier survival and cumulative incidence over months 1..``horizons``.

    Failure is absorbing: a row that fails stays failed, and it leaves the risk
    set at its failure month rather than being deleted from the base rate when
    its path later runs out. A row that neither failed nor was observed to the
    end is censored at its last observed month, which contributes to the risk
    set up to that month and to nothing after it. Censoring is only ignorable if
    the reason a path ends is unrelated to the event, which holds for the right
    edge of a price file and does not hold for a delisting.

    Returns ``at_risk``, ``failures``, ``survival`` and ``incidence`` per month.
    """
    fail = np.asarray(fail, dtype=float)
    last = np.asarray(last, dtype=float)
    stop = np.where(np.isnan(fail), last, fail)
    s, out = 1.0, []
    for k in range(1, horizons + 1):
        at_risk = int((stop >= k).sum())
        d = int((fail == k).sum())
        if at_risk > 0:
            s *= 1.0 - d / at_risk
        out.append({"month": k, "at_risk": at_risk, "failures": d,
                    "survival": s, "incidence": 1.0 - s})
    return pd.DataFrame(out).set_index("month")


def survival_curve(paths: pd.DataFrame, event: str = "halved", horizons: int = 24,
                   prefix: str = "r", thresh: float = -0.5) -> pd.DataFrame:
    """Kaplan-Meier time to ``event`` over a ``forward_paths`` frame.

    ``event`` is ``"halved"``: the first month at which the cumulative return is
    at or below ``thresh``. ``prefix`` picks the basis, ``"r"`` for raw price
    return and ``"x"`` for market-adjusted, so the same question can be asked
    about a price that halved and about a firm that fell 50 points behind its
    entry-year cohort.

    ``event="ended"`` raises. A delisting hazard is not estimable from a
    current-listings price file: such a bundle deletes a delisted symbol rather
    than ending its series, so the only paths that end are the ones whose
    horizon runs past the file's right edge, and the resulting curve is a step
    at that edge, identical for every cohort.

    Returns the frame from ``kaplan_meier``; ``incidence`` is the share that
    have hit the event by each month, and ``crossing`` reads a level off it.
    """
    if event == "ended":
        raise ValueError(
            "the 'ended' event is not estimable from a current-listings price bundle: "
            "delisted symbols are deleted rather than ended, so every path that ends "
            "does so at the file's right edge and the curve carries no information "
            "about any cohort. Measure delisting from a source that dates it."
        )
    if event != "halved":
        raise ValueError(f"unknown event {event!r}; 'halved' is the only estimable one here")
    cols = [f"{prefix}_{k}" for k in range(1, horizons + 1)]
    missing = [c for c in cols if c not in paths.columns]
    if missing:
        raise KeyError(f"paths frame has no {missing[0]}; pass prefix='r' or 'x' to match it")
    fail, last = failure_times(paths[cols].to_numpy(dtype=float), thresh)
    return kaplan_meier(fail, last, horizons)


def crossing(incidence: pd.Series, level: float) -> int | None:
    """First month at which cumulative incidence reaches ``level``, else ``None``."""
    hit = incidence[incidence >= level]
    return int(hit.index[0]) if len(hit) else None


# ---- cluster-aware resampling ---------------------------------------------
def _cluster_blocks(groups: np.ndarray) -> list[np.ndarray]:
    """Row positions of each group, as index arrays.

    Positions rather than frames: a bootstrap concatenates index arrays hundreds
    of times, and concatenating frames instead is the difference between seconds
    and minutes.
    """
    order = np.argsort(groups, kind="stable")
    g = groups[order]
    starts = np.flatnonzero(np.r_[True, g[1:] != g[:-1]])
    return np.split(order, starts[1:])


def _cluster_replicates(values: np.ndarray, groups: np.ndarray, stat: Callable, draws: int,
                        seed: int, mask_a: np.ndarray | None = None,
                        mask_b: np.ndarray | None = None, min_side: int = 1) -> np.ndarray:
    """Bootstrap replicates of ``stat``, or of a difference of two ``stat``s, over whole groups.

    The one resampler behind every interval in this module. With no masks it
    replicates ``stat`` over all rows; with two it replicates
    ``stat(a) - stat(b)`` inside each draw, so a group that appears on both
    sides moves both together and the difference keeps its pairing. A draw that
    leaves either side thinner than ``min_side`` rows is discarded rather than
    contributing a statistic of almost nothing.
    """
    blocks = _cluster_blocks(groups)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(draws):
        pick = rng.integers(0, len(blocks), len(blocks))
        rows = np.concatenate([blocks[i] for i in pick])
        if mask_a is None:
            out.append(stat(values[rows]))
            continue
        a, b = mask_a[rows], mask_b[rows]
        if a.sum() < min_side or b.sum() < min_side:
            continue
        out.append(stat(values[rows][a]) - stat(values[rows][b]))
    return np.asarray(out, dtype=float)


def _percentiles(reps: np.ndarray, alpha: float) -> tuple[float, float]:
    if reps.size == 0:
        return float("nan"), float("nan")
    return (float(np.percentile(reps, 100 * alpha / 2)),
            float(np.percentile(reps, 100 * (1 - alpha / 2))))


def cluster_bootstrap(values, groups, stat: Callable = np.median, draws: int = 1000,
                      seed: int = 0, alpha: float = 0.05) -> tuple[float, float, float]:
    """``(observed, lower, upper)`` for ``stat``, resampling whole groups with replacement.

    Rows repeat by firm: several firm-years, several events, several quarters of
    one CIK. An interval that resamples rows treats those as independent
    observations and comes out too narrow. This draws whole groups, so a firm
    either contributes all of its rows to a replicate or none of them.

    ``cluster_boot_diff`` is the same estimator for a difference of two cohorts.
    NaN values are dropped first; the result is NaNs when nothing survives that.
    """
    values = np.asarray(values, dtype=float)
    groups = np.asarray(groups)
    ok = ~np.isnan(values)
    values, groups = values[ok], groups[ok]
    if values.size == 0:
        return float("nan"), float("nan"), float("nan")
    reps = _cluster_replicates(values, groups, stat, draws, seed)
    lo, hi = _percentiles(reps, alpha)
    return float(stat(values)), lo, hi


def cluster_boot_diff(a: pd.DataFrame, b: pd.DataFrame, col: str, by: str = "cik",
                      stat: Callable = np.median, draws: int = 1000, seed: int = 0,
                      alpha: float = 0.05) -> tuple[float, float, float, float]:
    """``(observed, lower, upper, share of draws at or below zero)`` for ``stat(a) - stat(b)``.

    Two cohorts drawn from the same firms are not two independent samples: a
    firm that sits in both moves both statistics at once. Each replicate
    resamples the union of the two frames' groups and rebuilds both sides from
    the same draw, which is what keeps that dependence in the interval.

    The fourth number is a one-sided read of the replicate distribution, not a
    p-value from a null model: it says how often a difference this way round
    failed to appear, and it only means anything for a difference.
    """
    a = a[np.isfinite(a[col].to_numpy(dtype=float))]
    b = b[np.isfinite(b[col].to_numpy(dtype=float))]
    if not len(a) or not len(b):
        return float("nan"), float("nan"), float("nan"), float("nan")
    values = np.concatenate([a[col].to_numpy(dtype=float), b[col].to_numpy(dtype=float)])
    groups = np.concatenate([a[by].to_numpy(), b[by].to_numpy()])
    mask_a = np.r_[np.ones(len(a), bool), np.zeros(len(b), bool)]
    reps = _cluster_replicates(values, groups, stat, draws, seed, mask_a, ~mask_a)
    lo, hi = _percentiles(reps, alpha)
    obs = float(stat(a[col].to_numpy(dtype=float)) - stat(b[col].to_numpy(dtype=float)))
    if obs == 0.0 and lo == 0.0 and hi == 0.0:
        # Both cohorts share the same statistic and so does every replicate.
        # On a sparse or coarse outcome (an integer score, a column that is
        # mostly zero) that is what the median does, and the zero-width
        # interval describes the grid, not the difference. The means can differ
        # by a lot while this prints 0.000 [0.000, 0.000].
        warnings.warn(
            "cluster_boot_diff: tied statistic in every replicate; [0, 0] describes a "
            "coarse or sparse outcome, not a precise null. Use stat=np.mean or a rate.",
            RuntimeWarning, stacklevel=2)
    p_le_0 = float((reps <= 0).mean()) if reps.size else float("nan")
    return obs, lo, hi, p_le_0


def clustered_shuffle(labels, groups, within=None, seed: int = 0) -> pd.Series:
    """Permute a label between groups, carrying each group's whole label series with it.

    The null a study needs is "this label, on the wrong firm", not "this label,
    on a random row". Shuffling rows destroys the within-firm persistence of the
    label and understates the null, sometimes by a factor of three. One global
    group-to-group map keeps each firm's label path intact.

    ``within`` is an optional alignment key such as the period or the entry
    year. Given one, a row takes the partner's labels for the same key, walking
    every row of that cell in order (a quarterly frame hands over four quarters,
    not one quarter four times). A row whose partner has no cell at that key
    takes the partner's label at its nearest key instead, so the partner's
    whole path still moves as one and no row is lost from the null. Drawing
    those rows from a pool of other firms would break the label's persistence
    on exactly the rows an unbalanced panel has most of, and a null with less
    persistence than the data is a null that flatters the result. The share of
    nearest-key rows is raised as a ``RuntimeWarning`` because each period's
    label distribution is then approximate rather than exact. Without
    ``within``, a row takes the partner's labels in order, cycling if the
    partner has fewer.

    This is the between-group null: calendar timing survives, firm identity does
    not. ``within_firm_shuffle`` is the other one.

    **The z this produces is a property of the construction, not of the data.**
    On an unbalanced panel a large share of rows have no partner row at their
    key, and what is done with those rows sets the width of the null. Three
    no-drop constructions of this same null gave z of 5.1, 8.8 and 12.0 on one
    frame, and an earlier construction that handed such a row a random label
    from the key's pool of other firms lost the within-firm persistence the
    helper exists to preserve and reported 17.8. Quote the construction beside
    the z, and read the ratio of the null's mean to the observed statistic
    rather than the z alone (CORRECTIONS.md entry 18).
    """
    index = labels.index if isinstance(labels, pd.Series) else pd.RangeIndex(len(labels))
    lab = np.asarray(labels)
    grp = np.asarray(groups)
    if len(lab) != len(grp):
        raise ValueError("labels and groups must be the same length")
    rng = np.random.default_rng(seed)
    uniq = pd.unique(grp)
    partner = dict(zip(uniq, rng.permutation(uniq)))
    if within is None:
        pools = {g: lab[grp == g] for g in uniq}
        counters = {g: 0 for g in uniq}
        out = []
        for g in grp:
            src = partner[g]
            out.append(pools[src][counters[src] % len(pools[src])])
            counters[src] += 1
        return pd.Series(out, index=index)
    w = np.asarray(within)
    if len(w) != len(lab):
        raise ValueError("within must be the same length as labels")
    cells: dict[tuple, list[int]] = {}
    for pos, key in enumerate(zip(grp.tolist(), w.tolist())):
        cells.setdefault(key, []).append(pos)
    group_keys: dict = {}
    for (g, k) in cells:
        group_keys.setdefault(g, []).append(k)
    # Nearest is measured in positions along the sorted key list, so a key can
    # be a year, a quarter-end date or a "2024-03" string alike.
    rank = {k: i for i, k in enumerate(sorted(set(w.tolist())))}
    group_keys = {g: sorted(ks, key=rank.__getitem__) for g, ks in group_keys.items()}
    group_ranks = {g: [rank[k] for k in ks] for g, ks in group_keys.items()}
    counters = {key: 0 for key in cells}
    out = np.empty(len(lab), dtype=object)
    fallback = 0
    for pos, (g, k) in enumerate(zip(grp.tolist(), w.tolist())):
        p = partner[g]
        src = (p, k)
        rows = cells.get(src)
        if rows is None:
            # The partner's path carries on from its nearest key: persistence
            # is preserved, timing is off by the gap.
            ks, rs = group_keys[p], group_ranks[p]
            r = rank[k]
            i = int(np.searchsorted(rs, r))
            if i >= len(rs) or (i > 0 and r - rs[i - 1] <= rs[i] - r):
                i -= 1
            src = (p, ks[i])
            rows = cells[src]
            fallback += 1
        out[pos] = lab[rows[counters[src] % len(rows)]]
        counters[src] += 1
    if fallback:
        warnings.warn(
            f"clustered_shuffle: {fallback / len(lab):.1%} of rows had no partner row for "
            "their key and took the partner's label at its nearest key; the per-key label "
            "distribution is approximate on an unbalanced panel",
            RuntimeWarning, stacklevel=2)
    return pd.Series(out.tolist(), index=index)


def within_firm_shuffle(df: pd.DataFrame, col: str, by: str = "cik", seed: int = 0) -> pd.Series:
    """Permute ``col`` inside each group, across that group's own rows.

    The within-group null: every group keeps its entire distribution, its mean,
    its spread, and whether it is a noisy group at all, and only the pairing
    between a value and the row it belongs to is destroyed. It answers "does
    this label point at the right period for this firm", where
    ``clustered_shuffle`` answers "does this label point at the right firm".
    The two nulls can disagree, and a result that survives one and not the other
    is a result about the thing the surviving null preserved.

    A group with one row is unchanged by construction and contributes nothing to
    the null.
    """
    rng = np.random.default_rng(seed)
    return df.groupby(by)[col].transform(lambda x: rng.permutation(x.to_numpy()))


def shift_trading_days(ticker: str, day, k: int) -> pd.Timestamp | None:
    """``day`` moved ``k`` trading days on the ticker's own calendar, or ``None``.

    A transaction date is not a publication date. Form 4 discloses a trade up to
    two business days after it happens, so an event study anchored on the
    transaction date measures a window the market could not yet have read, and
    the fix is a shift on the calendar the prices are actually on rather than on
    the civil calendar. ``k`` may be negative to move back.

    ``None`` when the ticker has no series or the shift runs off the end of it.
    """
    day = pd.Timestamp(day)
    if k == 0:
        return day
    c = stooq.closes(ticker)
    if c is None:
        return None
    if k > 0:
        idx = c.index[c.index >= day]
        return idx[k] if len(idx) > k else None
    idx = c.index[c.index <= day]
    return idx[k - 1] if len(idx) >= -k + 1 else None


def extremes_vs_middle(df: pd.DataFrame, quintile_col: str, outcome: str,
                       stat: Callable = np.mean, extremes: Sequence = (1, 5), middle=3,
                       groups: str | None = None, draws: int = 400,
                       seed: int = 0, alpha: float = 0.05) -> dict:
    """``stat`` over the extreme quintiles minus ``stat`` over the middle one.

    Q5 minus Q1 is the wrong summary for a variable whose two tails do the same
    thing. A quantity that sorts by the SIZE of a change rather than its
    direction shows up as a U across the quintiles, and a top-minus-bottom
    contrast reads that U as a null. This contrast asks the question the shape
    poses: do both ends differ from the middle.

    Values are in the outcome's own units. With ``groups`` naming a cluster
    column, ``lo``/``hi`` are a ``cluster_bootstrap`` interval on the gap;
    without one they are NaN. Returns ``n_extremes``, ``n_middle``, ``gap``,
    ``lo``, ``hi``.
    """
    d = df.dropna(subset=[quintile_col, outcome])
    if groups:
        d = d.dropna(subset=[groups])
    d = d.reset_index(drop=True)
    a = d[quintile_col].isin(list(extremes)).to_numpy()
    b = d[quintile_col].isin(list(np.atleast_1d(middle))).to_numpy()
    v = d[outcome].to_numpy(dtype=float)
    gap = float(stat(v[a]) - stat(v[b])) if a.any() and b.any() else float("nan")
    lo = hi = float("nan")
    if groups and a.any() and b.any():
        reps = _cluster_replicates(v, d[groups].to_numpy(), stat, draws, seed, a, b, min_side=2)
        lo, hi = _percentiles(reps, alpha)
    return {"n_extremes": int(a.sum()), "n_middle": int(b.sum()), "gap": gap, "lo": lo, "hi": hi}


def benchmark_return(symbol: str, start, months: int) -> float | None:
    """Price return of an ETF or index from the last close on or before ``start`` over ``months``."""
    c = stooq.closes(symbol)
    if c is None:
        return None
    t0 = pd.Timestamp(start)
    t1 = t0 + pd.DateOffset(months=months)
    e0, e1 = c.loc[:t0], c.loc[:t1]
    if e0.empty or e1.empty or (t1 - e1.index[-1]).days > 45:
        return None
    return float(e1.iloc[-1] / e0.iloc[-1] - 1)


# ---- point-in-time record anchors -----------------------------------------
def record_refresh_events(panel: pd.DataFrame, events_only: bool = True) -> pd.DataFrame:
    """The first quarter-end at which each ``(cik, fiscal_year)`` appears in the panel.

    The panel is point-in-time, so a fiscal year's first appearance is knowable
    on the day it happens: it is the first quarter end taken after that year's
    annual report reached the record. That date is the anchor at which a change
    in the filed record is new. A December row is not. A fiscal year enters the
    panel at 74% of March quarter-ends and 8% of December ones, so a December
    row's annual block is a median of 275 days old, and a December-anchored sort
    measures a change the record has already carried for three quarters
    (docs/traps.md, trap 16).

    ``first_panel_row`` marks the rows at which nothing refreshed: the firm
    arrived. 8.50% of priced refresh anchors, 2,611 of 30,733, are a CIK's own
    first panel row, where the flag records an arrival and not a new filing, so
    a study that reads the anchor as "the record changed" drops them or says
    why not.

    Adds ``fy_first_seen``, ``is_refresh``, ``fy_age_days`` and
    ``first_panel_row``. With ``events_only`` the frame is cut to the refresh
    rows, which is the event set; without it every row is returned carrying the
    flags, which is what a staleness measurement wants. No universe filter is
    applied: pass the rows you intend to study, already cut to listed,
    revenue-positive, uncollided tickers if that is the universe you want.
    """
    first = (panel.groupby(["cik", "fiscal_year"]).as_of_date.min()
             .rename("fy_first_seen").reset_index())
    out = panel.merge(first, on=["cik", "fiscal_year"], how="left")
    out["is_refresh"] = out.as_of_date == out.fy_first_seen
    out["fy_age_days"] = (out.as_of_date - out.fy_first_seen).dt.days
    out["first_panel_row"] = out.as_of_date == out.groupby("cik").as_of_date.transform("min")
    if events_only:
        return out[out.is_refresh].reset_index(drop=True)
    return out


def _quarter_index(dates: pd.Series) -> pd.Series:
    """``year * 4 + quarter - 1``, so a difference of quarters is a subtraction."""
    d = pd.DatetimeIndex(dates)
    return pd.Series(d.year * 4 + (d.month - 1) // 3, index=getattr(dates, "index", None))


def exit_frame(panel: pd.DataFrame, runway_quarters: int = 8, vintage=None,
               anchor: str = "last_row", rows: pd.DataFrame | None = None) -> pd.DataFrame:
    """When each CIK's record stops, and whether that is far enough back to call an exit.

    Per CIK: ``first_row``, ``last_row``, ``last_refresh`` (the first quarter end
    carrying the CIK's final fiscal year, so the last date at which a new annual
    filing refreshed the record), ``stale_tail_quarters`` between the two,
    ``exit_date`` under the chosen ``anchor`` and ``exit``. This is the
    price-free definition, so it sees the firms a current-listings price bundle
    deletes outright.

    **The last panel row is a staleness drop, not a filing date.** On a 130-CIK
    probe carrying a served ``delistedAt``, the panel's last row FOLLOWS that
    date for 93.1% of them by a median of +2.92 quarters, while the last record
    refresh PRECEDES it for 93.8% by a median of 1.83 quarters. The true exit
    sits between the two anchors, and neither is it.

    **The anchor is the measurement.** On the same 137,787 firm-quarters, an
    eight-quarter exit base rate for the Altman Z < 1.8 cell runs 26.60% on the
    last-refresh anchor with the repeated stale rows kept, 18.49% and 18.81% on
    the two middle definitions, and 9.83% on the last-row anchor with those rows
    dropped: a factor of 2.7 across four defensible choices. Report the anchor
    and the stale-row treatment beside any such rate (CORRECTIONS.md entry for
    ``research/review-pre-exit``).

    ``anchor`` is ``"last_row"`` or ``"last_refresh"``. ``vintage`` defaults to
    the panel's own last as-of date, which is the right edge of what is
    observable.

    With ``rows``, the per-CIK answer is attached to an anchor frame carrying
    ``cik`` and ``as_of_date`` instead: ``exit`` is then per row and is NaN
    where the row's own ``runway_quarters`` horizon runs past the vintage, since
    a firm-year whose window has not closed is not a survivor and must not be
    counted as one. ``after_last_refresh`` marks the rows that repeat one annual
    filing past the CIK's last refresh; every one of them belongs to an exiting
    CIK and is positive by construction, and they were 51.9% of the positive
    outcomes in the cell above.
    """
    if anchor not in ("last_row", "last_refresh"):
        raise ValueError(f"anchor must be 'last_row' or 'last_refresh', not {anchor!r}")
    vintage = pd.Timestamp(panel.as_of_date.max() if vintage is None else vintage)
    p = panel.sort_values(["cik", "as_of_date"])
    final_fy = p.groupby("cik").fiscal_year.transform("last")
    firms = pd.DataFrame({
        "first_row": p.groupby("cik").as_of_date.min(),
        "last_row": p.groupby("cik").as_of_date.max(),
        "last_refresh": p[p.fiscal_year == final_fy].groupby("cik").as_of_date.min(),
    })
    firms["stale_tail_quarters"] = (_quarter_index(firms.last_row).to_numpy()
                                    - _quarter_index(firms.last_refresh).to_numpy())
    firms["exit_date"] = firms[anchor]
    firms["exit"] = (firms.exit_date + pd.DateOffset(months=3 * runway_quarters)) <= vintage
    firms.index.name = "cik"
    if rows is None:
        return firms
    out = rows.copy()
    out["exit_date"] = out.cik.map(firms.exit_date)
    out["last_refresh"] = out.cik.map(firms.last_refresh)
    horizon = out.as_of_date + pd.DateOffset(months=3 * runway_quarters)
    out["exit_horizon"] = horizon
    out["exit_observable"] = horizon <= vintage
    out["exit"] = np.where(out.exit_observable,
                           (out.exit_date <= horizon).astype(float), np.nan)
    out["after_last_refresh"] = out.as_of_date > out.last_refresh
    return out


# ---- within-cohort ranking -------------------------------------------------
def _group_key(df: pd.DataFrame, by) -> pd.Series:
    """A grouping key from a column name or an array-like, aligned to ``df``."""
    if isinstance(by, str):
        return df[by]
    return pd.Series(np.asarray(by), index=df.index)


def qcut_within(df: pd.DataFrame, col: str, by, q: int = 5,
                min_per_bin: int = 5) -> pd.Series:
    """Quantile 1..``q`` of ``col`` inside each ``by`` cohort, NaN where undefined.

    Ranks before cutting, so a column with an atom at exactly zero still splits
    into ``q`` bins instead of collapsing into two. A Piotroski step, a margin
    that did not move and a buyback intensity that is zero for most of the
    universe all have that shape, and ``pandas.qcut`` on the raw values puts
    every tied row in one bin and leaves the rest empty.

    A cohort with fewer than ``min_per_bin * q`` non-null rows is left NaN
    rather than cut into bins of one or two, which is how a thin early year
    contributes a spread made of single rows.

    ``by`` is a column name or an array aligned to ``df``. The cut is
    vectorised, because a placebo loop recuts inside every draw.
    """
    v = df[col].astype(float)
    g = _group_key(df, by)
    r = v.groupby(g).rank(method="first", pct=True)
    n = v.groupby(g).transform("count")
    out = np.ceil(r * q)
    return out.where((n >= min_per_bin * q) & v.notna()).clip(1, q)


def tercile(df: pd.DataFrame, col: str, by, min_per_bin: int = 5) -> pd.Series:
    """``qcut_within`` at ``q=3``: the cut a thin cohort can still carry."""
    return qcut_within(df, col, by, q=3, min_per_bin=min_per_bin)


# ---- firm type against firm timing ----------------------------------------
def decomposition_ladder(df: pd.DataFrame, col: str, outcome: str, by: str = "cik",
                         within: str = "year", q: int = 5, stat: Callable = np.mean,
                         draws: int = 400, seed: int = 0,
                         min_history: int = 5) -> pd.DataFrame:
    """The same sort under four readings of one column, each with a cluster interval.

    A top-minus-bottom spread on a firm-year column answers two questions at
    once: which firms sit at the top, and which of a firm's own years sit at its
    top. These four sorts separate them, and the gap that survives says which
    question the finding was about.

    * **this row's value**, the sort as published;
    * **the firm's mean over its PRIOR rows only**, which is knowable at entry
      and carries no information from after the row (its whole-history twin
      reads the future and is not offered here);
    * **the within-firm rank of this row**, which holds firm identity fixed and
      keeps only timing;
    * **the within-firm demeaned value**, the same contrast in the column's own
      units.

    Rows are read in ``(by, within)`` order for the backward mean, so ``within``
    has to be the time key. Each variant is cut by ``qcut_within`` inside
    ``within`` and the top bin is contrasted with the bottom by
    ``cluster_boot_diff`` over ``by``. Gaps are in the outcome's own units, not
    percentage points. Returns ``n``, ``firms``, ``gap``, ``lo``, ``hi`` per
    variant, indexed by the sort's name. The four sorts can move a tail gap far
    enough to change what a study is about, so all four are reported together.
    """
    d = df.dropna(subset=[col]).sort_values([by, within], kind="stable").copy()
    grp = d.groupby(by)[col]
    fmean = grp.transform("mean")
    count = grp.transform("size")
    prior_mean = (grp.cumsum() - d[col]) / grp.cumcount()
    variants = [
        ("this row's value", d[col], None),
        ("the firm's mean over prior rows only", prior_mean, grp.cumcount() >= 2),
        ("the within-firm rank of this row", grp.rank(pct=True), count >= min_history),
        ("the within-firm demeaned value", d[col] - fmean, count >= min_history),
    ]
    out = []
    for name, values, mask in variants:
        v = values if mask is None else values.where(mask)
        f = d.assign(_v=v).dropna(subset=["_v"])
        f = f.assign(_q=qcut_within(f, "_v", within, q=q))
        obs, lo, hi, _ = cluster_boot_diff(f[f._q == q], f[f._q == 1], outcome, by=by,
                                           stat=stat, draws=draws, seed=seed)
        out.append({"sorted on": name, "n": int(len(f)), "firms": int(f[by].nunique()),
                    "gap": obs, "lo": lo, "hi": hi})
    return pd.DataFrame(out).set_index("sorted on")


def presample_label(df: pd.DataFrame, col: str, by: str = "cik",
                    label_years: tuple[int, int] = (2010, 2013),
                    eval_years: tuple[int, int] = (2015, 2023),
                    year_col: str = "year", stat: str = "mean",
                    min_rows: int = 2) -> pd.DataFrame:
    """Fix a firm's label on an early window, then evaluate it on a later disjoint one.

    A firm-level sort computed on the same rows it is evaluated on cannot say
    whether the label was knowable in advance, because the label and the outcome
    share their rows. This fixes the label from ``label_years`` and returns only
    the ``eval_years`` rows, so the two windows share nothing. The windows must
    not touch: a one-year gap between them is the convention here, and an
    overlap raises.

    The label is ``stat`` of ``col`` over the label window, computed on whatever
    frame is passed, so a label taken from the FULL panel and evaluated on a
    priced subset is one call with two frames. Firms with fewer than
    ``min_rows`` label-window rows are dropped: a mean of one row is that row.

    The survivorship this creates is the caveat that travels with the result. A
    firm needs rows in both windows to appear at all, which is a minority of any
    pool and skews large, so the evaluated cohort is not the pool's cohort.

    Returns the eval rows carrying ``presample_{col}``.
    """
    l0, l1 = label_years
    e0, e1 = eval_years
    if e0 <= l1:
        raise ValueError(
            f"label window {label_years} and eval window {eval_years} overlap or touch; "
            "the point of the label is that it shares no row with the evaluation")
    lab = df[(df[year_col] >= l0) & (df[year_col] <= l1)].dropna(subset=[col])
    agg = lab.groupby(by)[col].agg([stat, "size"])
    agg = agg[agg["size"] >= min_rows]
    out = df[(df[year_col] >= e0) & (df[year_col] <= e1)].copy()
    out[f"presample_{col}"] = out[by].map(agg[stat])
    return out.dropna(subset=[f"presample_{col}"])


def year_stratum_shuffle(df: pd.DataFrame, col: str, strata, within: str = "year",
                         seed: int = 0) -> pd.Series:
    """Permute ``col`` inside each ``(within, stratum)`` cell.

    The third null beside ``clustered_shuffle`` and ``within_firm_shuffle``, and
    the one that says how much of a firm-level null is carried by a single
    coarse property. It keeps the period and one binned firm attribute, usually
    the firm's own mean of ``col``, and destroys everything else about firm
    identity, where ``within_firm_shuffle`` keeps all of it. If this null lands
    where the within-firm null lands, the within-firm null was carrying the firm
    mean and nothing more.

    ``strata`` is a column name or an array aligned to ``df``. Returns a Series
    on ``df``'s index.
    """
    rng = np.random.default_rng(seed)
    d = df.assign(_stratum=_group_key(df, strata))
    return d.groupby([within, "_stratum"], observed=True)[col].transform(
        lambda x: rng.permutation(x.to_numpy()))


# ---- cluster resampling, exposed ------------------------------------------
def cluster_resample_index(groups, draws: int, seed: int = 0):
    """Yield one array of row positions per cluster-bootstrap draw.

    Whole groups are drawn with replacement, so a firm contributes all of its
    rows to a replicate or none of them, and a group drawn twice appears twice.
    This is the same resampler ``cluster_bootstrap`` and ``cluster_boot_diff``
    run on, exposed because a statistic that is not a function of one value
    column cannot be passed to either: a ratio of two medians, an R-squared, a
    rate over a matrix. Four studies reached into the private ``_cluster_blocks``
    for exactly that.

    Row positions rather than frames: a bootstrap concatenates index arrays
    hundreds of times, and concatenating frames instead is the difference
    between seconds and minutes. Index the values with ``values[rows]`` and
    ``frame.iloc[rows]``, never ``frame.loc``.
    """
    blocks = _cluster_blocks(np.asarray(groups))
    rng = np.random.default_rng(seed)
    for _ in range(draws):
        pick = rng.integers(0, len(blocks), len(blocks))
        yield np.concatenate([blocks[i] for i in pick])


def boot_ratio(num, den, groups, stat: Callable = np.nanmedian, draws: int = 400,
               seed: int = 0, alpha: float = 0.05) -> tuple[float, float, float]:
    """``(observed, lower, upper)`` for ``stat(num) / stat(den)``, resampling whole groups.

    A ratio of two statistics over the same rows is not a difference and cannot
    go through ``cluster_boot_diff``: both legs move together inside a draw, and
    that dependence is the whole point of the interval. ``num`` and ``den`` share
    a first axis, one entry per row of ``groups``, and may be wider than one
    column, so "this day's absolute abnormal return over the median of every
    quiet day" is one call with a matrix on each side.

    The statistic is applied to all elements of the resampled block, so a wider
    ``den`` weights the denominator by how many columns it carries, which is
    what a quiet-window baseline wants. NaNs are the caller's to handle;
    ``numpy.nanmedian`` is the default because an event matrix has holes.
    """
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    if len(num) != len(den):
        raise ValueError("num and den must have the same number of rows")
    obs = float(stat(num) / stat(den))
    reps = np.asarray([stat(num[rows]) / stat(den[rows])
                       for rows in cluster_resample_index(groups, draws, seed)], dtype=float)
    lo, hi = _percentiles(reps, alpha)
    return obs, lo, hi


# ---- daily event time -----------------------------------------------------
def _first_close_at_or_after(idx: "pd.DatetimeIndex", day) -> int | None:
    """Position of the first close on or after ``day``: ``abnormal_path``'s event-time zero."""
    i = int(np.searchsorted(idx.to_numpy(), np.datetime64(pd.Timestamp(day)), side="left"))
    return i if i < len(idx) else None


def daily_abnormal(ticker: str, day, lo: int, hi: int,
                   benchmark: str = "SPY") -> np.ndarray | None:
    """Bar-to-bar abnormal return over trading-day offsets ``lo``..``hi``, not cumulative.

    Offset 0 is the first close on or after ``day``, which is
    ``abnormal_path``'s convention, and the value at offset k is the ticker's
    simple return from the close at k-1 to the close at k minus the benchmark's
    over the same two closes.

    Differencing a cumulative path is not this. Every value of
    ``abnormal_path`` is measured from one base close, so the difference of two
    of them divides a day's move by the base rather than by the previous close,
    which scales each day by how far the path has already travelled and
    coincides with the daily return only at offset 0 (docs/traps.md, trap 17).

    The benchmark is put on the ticker's own trading days first, so offset k
    subtracts the same calendar date on both sides. ``None`` when either series
    is missing or the window runs off an end of the ticker's series, and the
    result is all-or-nothing: a hole anywhere in the window returns ``None``
    rather than a path with a gap in it.
    """
    c, b = stooq.closes(ticker), stooq.closes(benchmark)
    if c is None or b is None:
        return None
    bb = b.reindex(b.index.union(c.index)).ffill().reindex(c.index)
    j = _first_close_at_or_after(c.index, day)
    if j is None or j + lo - 1 < 0 or j + hi >= len(c):
        return None
    cv, bv = c.to_numpy(dtype=float), bb.to_numpy(dtype=float)
    seg_c, seg_b = cv[j + lo - 1: j + hi + 1], bv[j + lo - 1: j + hi + 1]
    if np.isnan(seg_c).any() or np.isnan(seg_b).any() or (seg_c[:-1] <= 0).any():
        return None
    return (seg_c[1:] / seg_c[:-1] - 1) - (seg_b[1:] / seg_b[:-1] - 1)


def med_abs_ratio(mat: np.ndarray, offsets, day: int = 0, quiet_min: int = 6) -> float:
    """Median absolute value at offset ``day`` over its median on the quiet offsets.

    A scale-free read of how much bigger one day is than a firm's own ordinary
    day, which is what a cross-section of firms with wildly different volatility
    can be pooled on. Absolute values, so it measures size and not direction,
    and medians, so one firm's 300% day does not become the answer. ``quiet``
    is every offset at least ``quiet_min`` trading days from the event on either
    side, which keeps the run-up and the drift out of the baseline.

    ``mat`` is one row per event and one column per offset, and ``offsets`` names
    the columns. ``boot_ratio`` puts an interval on it.
    """
    offsets = np.asarray(offsets)
    d = np.asarray(mat, dtype=float)[:, offsets == day]
    quiet = np.asarray(mat, dtype=float)[:, np.abs(offsets) >= quiet_min]
    return float(np.nanmedian(np.abs(d)) / np.nanmedian(np.abs(quiet)))


# ---- calendar-day segments ------------------------------------------------
def _named_segments(segments) -> list[tuple[str, int, int]]:
    if isinstance(segments, Mapping):
        return [(str(k), int(a), int(b)) for k, (a, b) in segments.items()]
    return [(f"s_{int(a)}_{int(b)}", int(a), int(b)) for a, b in segments]


def segment_returns(events: pd.DataFrame, segments, anchor: str = "as_of_date",
                    anchor_shift: int = 0, benchmark: str = "SPY",
                    max_stale_days: int = 14, edge_slack_days: int = 0,
                    ticker_col: str = "ticker") -> pd.DataFrame:
    """Market-adjusted returns over arbitrary calendar-day segments around an anchor.

    Each segment is compounded off its OWN start rather than differenced out of
    a cumulative path, which is the only way ``(a, b)`` means the return from day
    ``a`` to day ``b`` (docs/traps.md, trap 17). ``segments`` is a mapping of
    name to ``(lo_days, hi_days)`` or a sequence of such pairs, named ``s_lo_hi``.

    Endpoint rule, and it is not symmetric on purpose: offset 0 is the last
    close STRICTLY BEFORE the shifted anchor, the base print, so the anchor
    day's own move sits inside a segment that starts at 0; every other offset
    ``d`` is the last close on or before ``anchor + d`` calendar days. Offsets
    may be negative, which is how a run-up is measured.

    ``anchor_shift`` moves the anchor by whole calendar days, positive later.
    An event dated by a transaction rather than a publication needs that shift
    before it is a window the market could read.

    **The right edge is hard.** An endpoint later than the ticker's last close
    plus ``edge_slack_days`` is NaN, and so is every segment touching it.
    Slack prices a horizon with the file's final close and labels it with the
    nominal date, which on a current-listings bundle turns the file's right edge
    into a return; raise ``edge_slack_days`` only to reproduce a study that did.

    Per segment the frame carries ``name`` (the ticker's return minus the
    benchmark's between the identical dates), ``name_raw``, ``name_bench`` and
    ``name_end`` (the date that priced the end), plus ``anchor_used``. Events
    whose base print is missing or more than ``max_stale_days`` old are dropped,
    which is the same entry test ``forward_paths`` applies.
    """
    segs = _named_segments(segments)
    bench = stooq.closes(benchmark)
    if bench is None:
        raise ValueError(f"no series for benchmark {benchmark!r}")
    bi, bv = bench.index.to_numpy(), bench.to_numpy(dtype=float)

    def bench_at(dates: np.ndarray) -> np.ndarray:
        out = np.full(len(dates), np.nan)
        ok = ~pd.isna(dates)
        if ok.any():
            j = np.searchsorted(bi, dates[ok].astype("datetime64[ns]"), side="right") - 1
            out[ok] = np.where(j >= 0, bv[np.clip(j, 0, len(bv) - 1)], np.nan)
        return out

    frames = []
    for t, g in events.groupby(ticker_col, sort=False):
        c = stooq.closes(t)
        if c is None or len(c) < 30:
            continue
        ci, cv = c.index.to_numpy(), c.to_numpy(dtype=float)
        edge = ci[-1] + np.timedelta64(int(edge_slack_days), "D")
        a = pd.DatetimeIndex(g[anchor]).to_numpy() + np.timedelta64(int(anchor_shift), "D")
        jb = np.searchsorted(ci, a, side="left") - 1        # last close strictly before
        ok = jb >= 0
        stale = np.full(len(g), np.iinfo(np.int64).max, dtype=np.int64)
        stale[ok] = (a[ok] - ci[jb[ok]]) // np.timedelta64(1, "D")
        ok &= stale <= max_stale_days
        if not ok.any():
            continue
        gg, aa, jb = g[ok].copy(), a[ok], jb[ok]
        px: dict[int, np.ndarray] = {}
        dt: dict[int, np.ndarray] = {}
        for _name, lo_d, hi_d in segs:
            for d in (lo_d, hi_d):
                if d in px:
                    continue
                if d == 0:
                    px[d], dt[d] = cv[jb], ci[jb]
                    continue
                grid = aa + np.timedelta64(int(d), "D")
                je = np.searchsorted(ci, grid, side="right") - 1
                bad = (je < 0) | (grid > edge)
                px[d] = np.where(bad, np.nan, cv[np.clip(je, 0, len(cv) - 1)])
                dt[d] = np.where(bad, np.datetime64("NaT", "ns"),
                                 ci[np.clip(je, 0, len(ci) - 1)])
        bpx = {d: bench_at(dt[d]) for d in px}
        gg["anchor_used"] = aa
        for name, lo_d, hi_d in segs:
            raw = px[hi_d] / px[lo_d] - 1
            ben = bpx[hi_d] / bpx[lo_d] - 1
            gg[name] = raw - ben
            gg[f"{name}_raw"] = raw
            gg[f"{name}_bench"] = ben
            gg[f"{name}_end"] = dt[hi_d]
        frames.append(gg)
    if not frames:
        return events.iloc[:0].copy()
    return pd.concat(frames, ignore_index=True)


def market_adjust_by(frame: pd.DataFrame, cols: Sequence[str], by) -> pd.DataFrame:
    """Each named column minus the median of its own ``by`` cohort.

    Market-adjusted means relative to the firms that entered alongside this one,
    so the cohort key has to be the thing that fixes the window. The calendar
    year is that key only when every anchor is 31 December: on a quarterly grid
    four snapshots a year open four different twelve-month windows, and one
    annual median subtracted from all four leaves a quarter-of-entry effect
    inside the adjusted column. On an event grid it is the event date.

    Returns a frame of the adjusted columns under their original names, on the
    original index, so the caller decides what to call them.
    ``forward_paths`` uses it with ``by="year"``; ``joins.market_adjust`` is the
    one-column form.
    """
    out = pd.DataFrame(index=frame.index)
    for c in cols:
        out[c] = frame[c] - frame.groupby(by)[c].transform("median")
    return out


# ---- variance attribution over blocks -------------------------------------
def _ols_r2(y: np.ndarray, X: np.ndarray) -> float:
    """R-squared of ``y`` on ``X`` with an intercept, by least squares."""
    X = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    return float(1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum())


def r2_lattice(y, blocks: Mapping[str, np.ndarray], max_blocks: int = 12) -> dict:
    """R-squared of every subset of ``blocks``, keyed by ``frozenset``.

    A block's contribution has no single value: it depends on which blocks are
    already in the model, and a ladder run in one order reports one of many
    answers. The lattice is the whole answer, and ``shapley`` reads the spread
    off it.

    ``blocks`` maps a name to a 2-D design block, all with the same number of
    rows as ``y``. The empty set is present at 0.0. Cost is ``2^k`` regressions,
    so ``max_blocks`` refuses a lattice that would not finish.
    """
    names = list(blocks)
    if len(names) > max_blocks:
        raise ValueError(f"{len(names)} blocks is 2**{len(names)} regressions; "
                         f"raise max_blocks deliberately if that is what you want")
    y = np.asarray(y, dtype=float)
    out: dict = {frozenset(): 0.0}
    for k in range(1, len(names) + 1):
        for combo in itertools.combinations(names, k):
            out[frozenset(combo)] = _ols_r2(y, np.column_stack([blocks[c] for c in combo]))
    return out


def shapley(r2: Mapping[frozenset, float], order: Sequence[str] | None = None) -> pd.DataFrame:
    """Per block: its increment alone, at its worst, at its best, and averaged over orderings.

    The Shapley value averages a block's increment over every ordering of the
    blocks, weighted so each "already in" subset size counts equally, and the
    values sum exactly to the full model's R-squared. That is the number a
    ladder is usually reaching for, and ``min_incr`` against ``max_incr`` is the
    honest width of what any single ordering could have reported.

    ``r2`` is a ``r2_lattice`` result. With ``order``, an ``order_incr`` column
    gives the increment that ladder order would have printed, for comparison
    with the study that ran one. Values are in R-squared units, not percent.
    """
    names = sorted(max(r2, key=len))
    nb = len(names)
    rows = []
    for b in names:
        others = [o for o in names if o != b]
        vals, shap = [], 0.0
        for k in range(nb):
            for subset in itertools.combinations(others, k):
                d = r2[frozenset(subset) | {b}] - r2[frozenset(subset)]
                vals.append(d)
                shap += d * math.factorial(k) * math.factorial(nb - k - 1) / math.factorial(nb)
        row = {"block": b, "alone": r2[frozenset([b])], "min_incr": min(vals),
               "max_incr": max(vals), "shapley": shap}
        if order is not None:
            i = list(order).index(b)
            row["order_incr"] = (r2[frozenset(order[:i + 1])] - r2[frozenset(order[:i])])
        rows.append(row)
    return pd.DataFrame(rows).set_index("block")


# ---- fiscal dating --------------------------------------------------------
def fiscal_periods(history_cache=None) -> pd.DataFrame:
    """``(cik, fiscal_year) -> period_end`` from cached ``/history`` responses.

    A fiscal year label is not a date. A December panel row carries the fiscal
    year on file at that date, which for three quarters of filers is the year
    that ended the previous December, so sorting on a trailing return and
    reading the "next" filed year compares the market with the same months it
    just ran through: 72% of such rows overlap the price window completely and
    1.5% are clean (docs/traps.md, trap 15). Dating the period from
    ``periodEnd`` and requiring it to end after the window is the fix, and
    ``overlap_years`` measures what is left.

    ``history_cache`` is a directory of cached responses (default: the client's
    cache) or an iterable of already-parsed response dicts. Later vintages win
    on a duplicate ``(cik, fiscal_year)``. Returns ``cik``, ``fiscal_year``,
    ``period_end``, ``year_offset`` (fiscal year minus the calendar year the
    period ends in) and ``month_day``, which is what a filer's own fiscal
    calendar looks like.
    """
    if history_cache is None or isinstance(history_cache, (str, Path)):
        root = Path(history_cache) if history_cache is not None else client.CACHE_DIR
        docs = []
        for f in sorted(root.glob("*sec_fundamentals_*_history*.json")):
            try:
                docs.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    else:
        docs = list(history_cache)
    rows = []
    for d in docs:
        if not isinstance(d, dict) or "__distill_error__" in d:
            continue
        cik = d.get("cikNumber")
        if cik is None:
            continue
        for y in d.get("years") or []:
            if y.get("periodEnd") and y.get("fiscalYear"):
                rows.append((int(cik), int(y["fiscalYear"]), y["periodEnd"]))
    h = pd.DataFrame(rows, columns=["cik", "fiscal_year", "period_end"])
    if h.empty:
        return h.assign(year_offset=pd.Series(dtype=int), month_day=pd.Series(dtype=object))
    h["period_end"] = pd.to_datetime(h.period_end)
    h = (h.sort_values("period_end")
         .drop_duplicates(["cik", "fiscal_year"], keep="last")
         .reset_index(drop=True))
    h["year_offset"] = h.fiscal_year - h.period_end.dt.year
    h["month_day"] = h.period_end.dt.strftime("%m-%d")
    return h


def overlap_years(period_end, start, end):
    """Share of the fiscal year ending at ``period_end`` that lies inside ``[start, end]``.

    Zero is the number a forward-looking study wants: a fiscal year that begins
    after the price window closed says nothing the window could have contained.
    One means the filed year and the price window are the same months, and any
    relation between them is the two describing one period rather than one
    leading the other.

    The year is taken as the 365 days ending at ``period_end``, which is a
    calendar approximation of a filer's own 52- or 53-week year and is accurate
    to a few days. Vectorised over arrays.
    """
    pe = np.asarray(period_end, dtype="datetime64[ns]")
    ps = pe - np.timedelta64(364, "D")
    a = np.maximum(ps, np.asarray(start, dtype="datetime64[ns]"))
    b = np.minimum(pe, np.asarray(end, dtype="datetime64[ns]"))
    days = (b - a) / np.timedelta64(1, "D")
    return np.clip(days / 365.0, 0, 1)


# ---- revisions ------------------------------------------------------------
def revision_filings(revisions, threshold: float = 0.10) -> pd.DataFrame:
    """One row per revising FILING, from ``/sec/revisions`` rows that are one per fact.

    One annual report recasts dozens of facts, so counting revision rows counts
    facts and inflates events by 4.26x against the filings that caused them
    (docs/traps.md, trap 10). Dedupe on ``changedAccession``, falling back to
    ``changedFiled`` where the accession is absent, and keep the largest
    ``|relDelta|`` fact as the filing's representative.

    ``revisions`` is the ``revisions`` list of one response, an iterable of such
    rows, or a frame of them; a ``ticker`` or ``cik`` key on the rows is carried
    into the dedupe so two filers' accessions never merge.

    Returns the representative fact's fields plus ``n_facts``, ``max_abs_rel``,
    and ``any_down`` / ``any_up``, true when any fact in the filing moved by at
    least ``threshold`` in that direction. There is no form type on
    ``changedAccession``, so a report filed to correct is indistinguishable from
    one that re-presents a prior year in its comparatives, and neither this nor
    anything else in the response separates them.
    """
    f = pd.DataFrame(list(revisions)) if not isinstance(revisions, pd.DataFrame) else revisions.copy()
    if f.empty:
        return f
    f = f[f.changedFiled.notna() & f.relDelta.notna()].copy()
    accession = (f.changedAccession if "changedAccession" in f.columns
                 else pd.Series(None, index=f.index, dtype=object))
    f["filing_key"] = accession.where(accession.notna(), f.changedFiled)
    keys = [k for k in ("ticker", "cik") if k in f.columns] + ["filing_key"]
    f["abs_rel"] = f.relDelta.abs()
    g = f.sort_values("abs_rel").groupby(keys, sort=False)
    out = g.tail(1).set_index(keys)
    out["n_facts"] = g.size()
    out["max_abs_rel"] = g.abs_rel.max()
    out["any_down"] = g.relDelta.min() <= -threshold
    out["any_up"] = g.relDelta.max() >= threshold
    return out.reset_index()


# ---- multiplicity ---------------------------------------------------------
def _beyond(value: float, nulls: np.ndarray) -> float:
    """One-sided share of ``nulls`` at least as extreme as ``value``, in its own direction."""
    return float((nulls >= value).mean() if value >= 0 else (nulls <= value).mean())


def family_chance(cells: Mapping[str, tuple], draws: int | None = None,
                  alpha: float = 0.05) -> dict:
    """How many cells of a reported family clear the study's own null by chance.

    A study that reports a grid of spreads, several sorts against several
    windows, gets a cell clearing at ``alpha`` for free at a rate the grid
    itself sets. This builds a synthetic family out of the study's own shuffle
    draws, applies the study's own clearing rule to it, and reports the
    distribution of the count. ``expected`` against ``observed_clear`` is the
    comparison; ``p_at_least_observed`` is how often chance alone produced a
    family as good as the reported one.

    ``cells`` maps a cell name to ``(observed, nulls)``. ``nulls`` is a sequence
    of shuffled statistics for that cell, or a mapping of null name to such a
    sequence when a cell has to clear more than one shuffle, in which case the
    first null supplies the stand-in value and every null must be cleared.
    ``draws`` defaults to the shortest null available.
    """
    prepared = {}
    for name, (obs, nulls) in cells.items():
        if isinstance(nulls, Mapping):
            pools = {k: np.asarray(v, dtype=float) for k, v in nulls.items()}
        else:
            pools = {"null": np.asarray(nulls, dtype=float)}
        prepared[name] = (float(obs), pools)

    def clears(value: float, pools: Mapping[str, np.ndarray]) -> bool:
        return all(_beyond(value, p) <= alpha for p in pools.values())

    observed_clear = sum(clears(obs, pools) for obs, pools in prepared.values())
    n_draws = min(min(len(p) for p in pools.values()) for _obs, pools in prepared.values())
    n_draws = n_draws if draws is None else min(draws, n_draws)
    counts = np.array([
        sum(clears(float(next(iter(pools.values()))[i]), pools)
            for _obs, pools in prepared.values())
        for i in range(n_draws)], dtype=float)
    return {"n_cells": len(prepared), "observed_clear": int(observed_clear),
            "draws": int(n_draws), "expected": float(counts.mean()),
            "sd": float(counts.std()), "p95": float(np.percentile(counts, 95)),
            "p_any": float((counts >= 1).mean()),
            "p_at_least_observed": float((counts >= observed_clear).mean())}
