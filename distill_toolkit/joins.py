"""Joining fundamentals to prices without fooling yourself.

Distill serves fundamentals and no prices. A price series you hold is
split-adjusted on its own schedule. The functions here make the join explicit:
check the share basis, decompose a return, and compute forward returns with
staleness guards. Every trap they defend against was hit for real; see
docs/traps.md.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

SPLIT_FACTORS = (2, 3, 4, 5, 6, 7, 8, 10, 20)


def split_basis_flags(
    shares_by_year: Mapping[int, float], tol: float = 0.06
) -> list[tuple[int, float, float]]:
    """Years where the share count steps by something that looks like a split.

    Filers restate the weighted-average diluted count only two fiscal years back
    from the first annual filing after a split. On a window that crosses an
    older split the series still carries one step of the split factor, and a
    price series adjusted across all history disagrees with it by exactly that
    factor. Returns ``(year, ratio, factor)`` where ``ratio`` is
    ``shares[year] / shares[year - 1]`` and ``factor`` is the nearest integer
    split (``n`` for a forward split, ``1/n`` for a reverse).

    A step is evidence, not proof. Anything that multiplies the count by a
    round number lands in the same band: an IPO share-count step, a conversion,
    a stock-funded acquisition. Measured against the never-restated
    ``sharesOutstanding`` over a research pool, 46% of the flags corroborate,
    37% are contradicted and 17% are untestable, so about a third of what this
    returns is a false positive. Pass the flags through ``corroborate_flags``
    and give ``rebase_shares`` only the corroborated ones; rebasing on a flag
    this function raised alone silently multiplies a real issuance into the
    share basis and every per-share figure built on it.
    """
    years = sorted(y for y, v in shares_by_year.items() if v)
    flags = []
    for prev, year in zip(years, years[1:]):
        if year - prev != 1:
            continue
        ratio = shares_by_year[year] / shares_by_year[prev]
        for n in SPLIT_FACTORS:
            if abs(ratio - n) <= n * tol:
                flags.append((year, ratio, float(n)))
                break
            if abs(ratio - 1 / n) <= tol / n:
                flags.append((year, ratio, 1 / n))
                break
    return flags


def rebase_shares(
    shares_by_year: Mapping[int, float], flags: list[tuple[int, float, float]]
) -> dict[int, float]:
    """Put every year on the basis of the latest year by applying flagged splits backward.

    Each flag ``(year, ratio, factor)`` multiplies every year before ``year`` by
    ``factor``. Feed it corroborated flags only: a flag raised by
    ``split_basis_flags`` alone is a step of about the right size, and applying
    one that turns out to be an issuance moves every earlier year by that
    factor with no visible symptom in the output.
    """
    out = dict(shares_by_year)
    for year, _ratio, factor in sorted(flags):
        for y in list(out):
            if y < year and out[y]:
                out[y] = out[y] * factor
    return out


def corroborate_flags(
    history_years: Sequence[Mapping],
    flags: list[tuple[int, float, float]],
    lookahead: int = 3,
    lo: float = 0.7,
    hi: float = 1.4,
) -> list[dict]:
    """Test each diluted-share flag against the never-restated ``sharesOutstanding``.

    The two share series break at different times, and that is what makes the
    test work. A filer restates ``weightedAverageSharesDiluted`` two fiscal
    years back from the first annual filing after a split, so the restated
    series steps at fiscal year ``y`` while the split itself happens around
    ``y + 2``. ``sharesOutstanding`` is never restated, so at ``y`` it still
    holds the pre-split count and it steps by the split factor at the split's
    own year.

    So: take ``sharesOutstanding`` at the flag year as the baseline and look for
    a year in ``y+1 .. y+lookahead`` whose count sits between ``lo`` and ``hi``
    times ``factor`` of it. A count that grows for another reason does not land
    in that band. The reported step year is the FIRST year in the window whose
    ratio enters the band, which is the year the split reached the outstanding
    count; when no year enters it, the year whose ratio came closest is reported
    so a contradicted verdict still shows what the series did.

    ``history_years`` is the ``years`` list of a ``/sec/fundamentals/{t}/history``
    response. Three verdicts, and the third is not the second: ``corroborated``,
    ``contradicted`` (the series exists and never steps by the factor) and
    ``untestable`` (no usable ``sharesOutstanding`` in the window). Only a
    corroborated flag belongs in ``rebase_shares``; an untestable one is
    unknown, not false.
    """
    so: dict[int, float] = {}
    for y in history_years:
        v = y.get("sharesOutstanding")
        # A NaN is truthy, and a frame that has been through pandas hands one
        # over for every absent count; treat it as absent, not as a baseline.
        if v is not None and v == v and float(v) > 0:
            so[int(y["fiscalYear"])] = float(v)
    out = []
    for year, ratio, factor in flags:
        base_year = max((y for y in so if y <= year), default=None)
        best, best_year, verdict = None, None, "untestable"
        if base_year is not None:
            base = so[base_year]
            for y in range(year + 1, year + lookahead + 1):
                if y not in so or not base:
                    continue
                r = so[y] / base
                if lo * factor <= r <= hi * factor:
                    best, best_year = r, y
                    break
                if best is None or abs(math.log(r / factor)) < abs(math.log(best / factor)):
                    best, best_year = r, y
            if best is not None:
                verdict = "corroborated" if lo * factor <= best <= hi * factor else "contradicted"
        out.append({"flag_year": year, "diluted_ratio": ratio, "factor": factor,
                    "baseline_year": base_year,
                    "shares_outstanding_step": best,
                    "shares_outstanding_step_year": best_year,
                    "verdict": verdict,
                    "corroborated": verdict == "corroborated"})
    return out


def share_series_sanity(
    shares_outstanding_by_year: Mapping[int, float],
    wasd_by_year: Mapping[int, float],
    lo: float = 0.5,
    hi: float = 2.0,
) -> list[dict]:
    """Fiscal years where the two share counts for one fiscal year disagree too much.

    A year-end outstanding count and a weighted-average diluted count for the
    same fiscal year sit within a few per cent of each other for a firm that
    issued and bought back the usual amount, and inside ``[lo, hi]`` for one
    that did something larger. Outside it, one of two things is true, and both
    are worth knowing before the numbers are used:

    * the two series are on different split bases, because the diluted series
      is restated across a split and ``sharesOutstanding`` is not. The ratio is
      then close to a split factor, and it is the same fact ``corroborate_flags``
      reads deliberately.
    * a share series can carry one value in the wrong unit (millions instead of
      shares); on one priced pool about 1% of filer-years did, a discrepancy of
      six orders of magnitude, and such years flow into ``rebase_shares`` and
      ``decompose`` as if they were counts.

    A ratio near a small integer is the first; a ratio in the thousands or
    millions is the second, and ``netIncome / epsDiluted`` reconstructs what the
    count should have been. Returns one row per offending year with both counts
    and their ratio; an empty list is the clean case.
    """
    out = []
    for year in sorted(set(shares_outstanding_by_year) & set(wasd_by_year)):
        so, wasd = shares_outstanding_by_year[year], wasd_by_year[year]
        if not so or not wasd or so <= 0 or wasd <= 0:
            continue
        ratio = so / wasd
        if not (lo <= ratio <= hi):
            out.append({"fiscal_year": year, "shares_outstanding": float(so),
                        "weighted_average_diluted": float(wasd), "ratio": float(ratio)})
    return out


def decompose(
    p0: float, p1: float, rev0: float, rev1: float, sh0: float, sh1: float
) -> dict[str, float]:
    """Multiplicative return decomposition on a revenue basis.

        price_return = revenue_per_share_growth * multiple_change

    Works with negative earnings, unlike a P/E decomposition, because it is
    revenue-based. All six inputs must be on one split basis. Returns
    ``ret``, ``rps``, ``mult``, ``ps0`` and ``ps1``.
    """
    ps0, ps1 = p0 * sh0 / rev0, p1 * sh1 / rev1
    return {
        "ret": p1 / p0,
        "rps": (rev1 / rev0) / (sh1 / sh0),
        "mult": ps1 / ps0,
        "ps0": ps0,
        "ps1": ps1,
    }


def forward_return(
    closes: "pd.Series",
    start: "pd.Timestamp",
    days: int,
    max_entry_stale_days: int = 14,
    max_exit_gap_days: int = 45,
) -> float | None:
    """Price return from the last close on or before ``start`` to the last close
    on or before ``start + days``.

    Returns ``None`` when the entry print is older than ``max_entry_stale_days``
    (a stale last price from a delisted name) or the exit print is more than
    ``max_exit_gap_days`` short of the horizon, and when the series ends at
    entry: if the last close on or before the horizon is the entry close itself,
    nothing was observed over the window and the honest answer is "no return",
    not a 0% return. A zero manufactured that way is the flat middle of any
    distribution and it is contributed by exactly the names that stopped
    trading, so it pulls a tail statistic toward safety.
    """
    import pandas as pd

    entry = closes.loc[:start]
    horizon = start + pd.Timedelta(days=days)
    exit_ = closes.loc[:horizon]
    if entry.empty or exit_.empty:
        return None
    if (start - entry.index[-1]).days > max_entry_stale_days:
        return None
    if (horizon - exit_.index[-1]).days > max_exit_gap_days:
        return None
    if exit_.index[-1] == entry.index[-1]:
        return None
    if entry.iloc[-1] <= 0:
        return None
    return float(exit_.iloc[-1] / entry.iloc[-1] - 1)


def market_adjust(df: "pd.DataFrame", col: str, by: str = "year") -> "pd.Series":
    """``col`` minus the same-group median: a return relative to the matched universe."""
    return df[col] - df.groupby(by)[col].transform("median")


# ---- split basis, inferred ------------------------------------------------
#: Ratios a stock split is actually declared at. A factor within ``SNAP_TOL`` of
#: one of these is snapped to it; the estimator carries a few per cent of error
#: because one series is a period-end count and the other a weighted average
#: over a year in which the count also moved.
CANONICAL_SPLITS = (2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 40, 50, 100, 1.5)
SNAP_TOL = 0.10


def snap(factor: float, tol: float = SNAP_TOL) -> tuple[float, bool]:
    """Nearest declared split ratio to ``factor`` when one is within ``tol``, else ``factor``.

    Splits are declared at round numbers. An estimated factor of 3.94 is a
    four-for-one with estimation error in it, and rounding it says so; an
    estimated 2.7 is not any declared ratio and must stay 2.7, because a factor
    that will not snap is the signal that the fingerprint was not a split.
    Distance is measured in log space, so 1/4 and 4 are equally near.
    Returns ``(factor, snapped)``.
    """
    cands = [float(c) for c in CANONICAL_SPLITS] + [1.0 / c for c in CANONICAL_SPLITS]
    best = min(cands, key=lambda c: abs(math.log(factor / c)))
    return (best, True) if abs(math.log(factor / best)) < tol else (factor, False)


def firm_basis(
    shares_outstanding_by_year: Mapping[int, float],
    wasd_by_year: Mapping[int, float],
    implied_by_year: Mapping[int, float] | None = None,
    lo: float = 0.5,
    hi: float = 2.0,
    max_run: int = 2,
    fmin: float = 1 / 60,
    fmax: float = 60.0,
) -> tuple[list[dict], list[int], set[int]]:
    """``(splits, unresolved_years, testable_years)``: one filer's splits, inferred.

    This is the join between ``share_series_sanity`` and ``corroborate_flags``
    that neither of them makes. The two share series break at different times,
    and that is what makes the inference possible. A filer restates
    ``weightedAverageSharesDiluted`` about two fiscal years back from the first
    annual filing after a split and no further, while ``sharesOutstanding`` is
    never restated. So for a split at fiscal year ``s`` with factor ``f``, the
    years ``s-2`` and ``s-1`` carry a restated post-split diluted count against
    an unrestated pre-split outstanding count and their ratio sits near ``1/f``,
    while every other year has both counts on one basis and a ratio near 1.
    ``share_series_sanity`` is that flag; this turns a run of flags into a split
    year and a factor.

    A split is accepted only when three things hold together: the run of flagged
    years is no longer than the two-year restatement window, the implied factor
    is a plausible split ratio, and the outstanding count's own step from
    ``s-1`` to ``s`` is closer to the factor than to 1. The third test is what
    separates a split from the other thing that puts the ratio far from 1, a
    year in which the share count itself grew several-fold: at a split the
    outstanding count steps by the factor, and at an IPO or a conversion it does
    not step back.

    ``implied_by_year`` is ``netIncome / epsDiluted`` and is read only where the
    diluted count is absent. A flagged run that fails any of the three tests is
    returned in ``unresolved_years``: the basis is known to be broken and the
    break is not repairable, which is a third state and must not be treated as
    either clean or fixed. ``testable_years`` are the years that carried both
    counts, so a year outside it was never tested at all.
    """
    implied_by_year = implied_by_year or {}
    ratio = {}
    for y in sorted(shares_outstanding_by_year):
        d = wasd_by_year.get(y) or implied_by_year.get(y)
        if d and d > 0 and shares_outstanding_by_year[y] > 0:
            ratio[y] = shares_outstanding_by_year[y] / d
    flagged = sorted(y for y, r in ratio.items() if not (lo <= r <= hi))
    runs: list[list[int]] = []
    for y in flagged:
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    splits, unresolved = [], []
    for run in runs:
        s = run[-1] + 1
        vals = sorted(ratio[y] for y in run)
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        f_wasd = 1.0 / median
        so = shares_outstanding_by_year
        step = so[s] / so[s - 1] if (s in so and so.get(s - 1)) else None
        ok = (len(run) <= max_run and fmin <= f_wasd <= fmax and step is not None
              and abs(math.log(step / f_wasd)) < abs(math.log(step)))
        if not ok:
            unresolved.extend(run)
            continue
        f, snapped = snap(math.sqrt(f_wasd * step))
        splits.append({"split_year": s, "factor": f, "factor_wasd": f_wasd,
                       "so_step": step, "snapped": snapped, "run_len": len(run)})
    return splits, sorted(set(unresolved)), set(ratio)


def rebase(shares_by_year: Mapping[int, float], splits: Sequence[Mapping]) -> dict[int, float]:
    """Every year on the LATEST year's basis, which is the basis a price file is on.

    A price file is adjusted for every split up to its own right edge, so the
    only share count that multiplies into a market capitalisation is one on that
    same basis. Each split multiplies every year before its ``split_year`` by
    its ``factor``. ``rebase_shares`` is the same operation driven by
    ``split_basis_flags`` output; this one is driven by ``firm_basis``.
    """
    out = dict(shares_by_year)
    for sp in sorted(splits, key=lambda d: d["split_year"]):
        for y in list(out):
            if y < sp["split_year"] and out[y]:
                out[y] = out[y] * sp["factor"]
    return out


def market_cap(shares, close, period_end=None, as_of=None):
    """Share count times close, refused where the fiscal period does not precede the close.

    The arithmetic is trivial and both inputs are traps. ``shares`` must already
    be on the price file's split basis (``firm_basis`` then ``rebase``): a
    never-restated ``sharesOutstanding`` multiplied by a retroactively adjusted
    close mis-states the capitalisation by the product of every split between
    the fiscal year on file and the file's right edge, and the error is silent
    because it looks like a company rather than like a defect.

    The alignment check is the second trap and this function enforces it. A
    fiscal year's share count is not knowable until that year's report is filed,
    so pairing it with a close from inside that same year reads a number the
    market did not have (docs/traps.md, trap 4). With ``period_end`` and
    ``as_of``, any row whose period does not END BEFORE the close date is NaN.
    That still allows a filing lag: the period ended, the report may not have
    been filed yet, and only ``/sec/fundamentals/{t}/as-of/{date}`` closes that
    gap. Without the two dates the check is the caller's, and it is not
    optional.

    Scalars in, scalar out; arrays in, array out.
    """
    cap = np.asarray(shares, dtype=float) * np.asarray(close, dtype=float)
    if period_end is not None and as_of is not None:
        pe = np.asarray(period_end, dtype="datetime64[ns]")
        ao = np.asarray(as_of, dtype="datetime64[ns]")
        cap = np.where(pe < ao, cap, np.nan)
    cap = np.where(cap > 0, cap, np.nan)
    return cap if cap.ndim else float(cap)
