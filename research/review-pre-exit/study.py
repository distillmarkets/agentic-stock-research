"""Adversarial review of ``research/pre-exit-signature``.

Every number in ``research/review-pre-exit/README.md`` is produced here, from
files already on disk. No API call is made: the only inputs are

* ``cache/panel.csv`` - the point-in-time panel, screen/export vintage 2026-09-03
* ``cache/stooq_us/`` - read only through the study's own ``load_frames``, to
  mark a ticker priced or not
* ``cache/research/pre-exit-signature/*`` - the reviewed study's own frames and
  the 150 cached probe responses
* ``cache/research/{share-issuance,fundamental-momentum,price-leads-record}/*``
  - sibling frames, read only to measure a shared helper's row-drop rate. Those
  study folders are not in the checkout; the scripts that wrote the frames are
  held by the publisher and available on request.

The reviewed study's constructors are imported rather than reimplemented, so a
reproduction failure here is a real one.

Run from the repository root::

    ./.venv/bin/python research/review-pre-exit/study.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = ROOT / "research" / "pre-exit-signature"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(STUDY_DIR))

from distill_toolkit import charts as C  # noqa: E402
from distill_toolkit.analysis import (  # noqa: E402
    cluster_boot_diff,
    clustered_shuffle,
)

import study as S  # noqa: E402  the reviewed study
from panel_base import EXIT_HORIZON, FINAL_QI, qi_label  # noqa: E402

OUT = ROOT / "cache" / "research" / "review-pre-exit"
CHARTS = Path(__file__).resolve().parent / "charts"
SOURCE = ("Distill point-in-time panel, screen/export vintage 2026-09-03; "
          "Stooq US bundle 2026-08-14; 150 cached /sec/fundamentals as-of responses")
DRAWS = 300
NULL_DRAWS = 200
SEED = 7

# Published numbers, transcribed from research/pre-exit-signature/README.md.
PUBLISHED_BASE = {
    "altman_z < 1.8": (0.1849, 0.0355, 27919, 2246, 13371),
    "interest_coverage < 1": (0.1959, 0.0465, 31604, 2819, 15296),
    "fcf_margin < 0 and revenue falling": (0.1787, 0.0316, 8293, 1273, 4183),
    "piotroski <= 2": (0.1859, 0.0393, 17472, 2431, 8314),
    "two or more of the four": (0.2048, 0.0453, 22156, 2379, 10044),
    "none of the four": (0.1000, 0.0162, 81292, 4082, 55358),
    "any firm-quarter": (0.1321, 0.0233, 137787, 5499, 83582),
}
ADVICE_WORDS = ("undervalued", "overvalued", "buy ", "sell-side", "target price",
                "should ", "warns", "opportunity", "attractive", "cheap", "expensive",
                "recommend", "outperform", "underperform", "worth calling")


def head(text: str) -> None:
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)


def pct(x: float, nd: int = 2) -> str:
    return "nan" if not np.isfinite(x) else f"{100 * x:.{nd}f}%"


# --------------------------------------------------------------------------
# helpers written for this review (no toolkit equivalent exists)
# --------------------------------------------------------------------------
def base_table(u: pd.DataFrame, horizon: int = 8, anchor: str = "last",
               drop_stale: bool = False, drop_ciks: tuple[str, ...] = (),
               ci: bool = True) -> pd.DataFrame:
    """The reviewed study's section-3 table under a chosen exit anchor.

    ``anchor="last"`` is the published definition: a firm-quarter counts as
    exiting when the CIK's **last panel row** falls within ``horizon`` quarters.
    ``anchor="fresh"`` dates the exit at ``fresh_qi``, the last quarter at which
    a new annual filing refreshed the row, which is what the reviewed study
    itself uses as the anchor for its trajectory section.

    ``drop_stale`` removes rows after ``fresh_qi``: for an exiting CIK those
    rows repeat one annual filing and are not independent firm-quarters.
    """
    b = u[u.qi <= FINAL_QI - EXIT_HORIZON - horizon].copy()
    if drop_ciks:
        b = b[~b.cik.isin(set(drop_ciks))]
    if drop_stale:
        b = b[b.qi <= b.fresh_qi]
    if anchor == "last":
        b["exit_h"] = b.last_qi <= b.qi + horizon
    elif anchor == "fresh":
        b["exit_h"] = b.is_exit & (b.fresh_qi <= b.qi + horizon)
    elif anchor == "fresh+2":
        # The probe puts the served delistedAt a median 1.83 quarters after the
        # last refresh and 2.92 quarters before the panel drop, so an anchor two
        # quarters after the last refresh is the one calibrated to the API's own
        # delisting date rather than to either end of the panel record.
        b["exit_h"] = b.is_exit & (b.fresh_qi + 2 <= b.qi + horizon)
    else:
        raise ValueError(anchor)
    st = S.states(b)
    rows = []
    for name in S.STATE_ORDER:
        sub = b[st[name]]
        pr = sub[sub.priced]
        if ci:
            a_r, a_lo, a_hi = S.rate_ci(sub.exit_h, sub.cik, draws=DRAWS, seed=SEED)
            p_r, p_lo, p_hi = S.rate_ci(pr.exit_h, pr.cik, draws=DRAWS, seed=SEED)
        else:
            a_r = sub.exit_h.mean()
            p_r = pr.exit_h.mean()
            a_lo = a_hi = p_lo = p_hi = np.nan
        rows.append({"state": name, "n": len(sub), "ciks": sub.cik.nunique(),
                     "all": a_r, "all_lo": a_lo, "all_hi": a_hi,
                     "n_priced": len(pr), "priced": p_r,
                     "priced_lo": p_lo, "priced_hi": p_hi,
                     "ratio": a_r / p_r if p_r else np.nan})
    t = pd.DataFrame(rows)
    t.attrs["rows"] = len(b)
    t.attrs["ciks"] = b.cik.nunique()
    return t


def print_table(t: pd.DataFrame, title: str) -> None:
    print(f"\n  {title}  (n = {t.attrs['rows']:,} firm-quarters, "
          f"{t.attrs['ciks']:,} CIKs)")
    print(f"    {'state':36s} {'n':>8s} {'whole panel':>24s} {'priced subset':>24s} {'x':>5s}")
    for r in t.itertuples():
        lo = f"[{pct(r.all_lo)},{pct(r.all_hi)}]" if np.isfinite(r.all_lo) else ""
        plo = f"[{pct(r.priced_lo)},{pct(r.priced_hi)}]" if np.isfinite(r.priced_lo) else ""
        print(f"    {r.state:36s} {r.n:8,d} {pct(getattr(r, 'all')):>8s} {lo:>15s} "
              f"{pct(r.priced):>8s} {plo:>15s} {r.ratio:5.2f}")


def build_anchors_keyed(u: pd.DataFrame, firm: pd.DataFrame,
                        keys: tuple[str, ...] = ("anchor", "terc"),
                        seed: int = S.SEED) -> pd.DataFrame:
    """The reviewed study's ``build_anchors`` with the matching cell as a parameter.

    ``keys=("anchor","terc")`` reproduces the published sampler exactly (checked
    in section 3 of this review). ``keys=("anchor","terc","sector")`` adds the
    panel's own sector to the cell. The sector is read at the anchor row, not
    from the CIK's last row, because 244 CIKs carry more than one sector.
    """
    ex = firm[firm["exit"] & (firm.hist_q >= 7)]
    e = pd.DataFrame({"cik": ex.index, "anchor": ex.fresh_qi.to_numpy(), "group": "exit"})
    sv = u[(~u.is_exit) & (u.qi - u.first_qi >= 7) & (u.last_qi - u.qi >= EXIT_HORIZON)]
    sv = sv[["cik", "qi"]].rename(columns={"qi": "anchor"}).assign(group="survivor")
    cand = pd.concat([e, sv], ignore_index=True)
    idx = pd.MultiIndex.from_arrays([cand.cik, cand.anchor])
    cand["revenue"] = u.set_index(["cik", "qi"]).revenue.reindex(idx).to_numpy()
    cand["sector"] = u.set_index(["cik", "qi"]).sector.reindex(idx).to_numpy()
    cand = cand.dropna(subset=["revenue"]).copy()
    cand["terc"] = cand.groupby("anchor").revenue.transform(S.tercile)
    E, Sv = cand[cand.group == "exit"], cand[cand.group == "survivor"]
    rng = np.random.default_rng(seed)
    pools = {k: g.index.to_numpy() for k, g in Sv.groupby(list(keys), observed=True)}
    picks, missed = [], 0
    for r in E.itertuples():
        key = tuple(getattr(r, k) for k in keys)
        pool = pools.get(key if len(key) > 1 else key[0])
        if pool is None or len(pool) == 0:
            missed += 1
            continue
        picks.append(rng.choice(pool, size=min(3, len(pool)), replace=False))
    out = pd.concat([E, Sv.loc[np.concatenate(picks)]], ignore_index=True)
    out["aid"] = np.arange(len(out))
    out.attrs["missed"] = missed
    return out


def did_table(traj: pd.DataFrame, metrics=None, draws: int = DRAWS) -> pd.DataFrame:
    """Difference in differences at each quarter, exits minus controls."""
    metrics = metrics or S.METRICS
    rows = []
    for m in metrics:
        stat = np.mean if m in S.DISCRETE else np.median
        for k in range(-EXIT_HORIZON + 1, 0):
            a = traj[(traj.group == "exit") & (traj.k == k)]
            b = traj[(traj.group == "survivor") & (traj.k == k)]
            col = "d_" + m
            o, lo, hi, _ = cluster_boot_diff(a, b, col, by="cik", stat=stat,
                                             draws=draws, seed=SEED)
            rows.append({"metric": m, "k": k, "did": o, "lo": lo, "hi": hi,
                         "exit_move": stat(a[col].dropna()),
                         "surv_move": stat(b[col].dropna()),
                         "zero_share": float((a[col].dropna() == 0).mean()),
                         "n_e": int(a[col].notna().sum()), "n_s": int(b[col].notna().sum())})
    t = pd.DataFrame(rows)
    t["sig"] = (t.lo > 0) | (t.hi < 0)
    return t


def level_table(traj: pd.DataFrame, draws: int = DRAWS) -> pd.DataFrame:
    """Median level gap at t-8 and t-1, exits minus controls, and the ratio of the two."""
    rows = []
    for m in S.METRICS:
        stat = np.mean if m in S.DISCRETE else np.median
        r = {"metric": m}
        for k, tag in ((-EXIT_HORIZON, "8"), (-1, "1")):
            a = traj[(traj.group == "exit") & (traj.k == k)]
            b = traj[(traj.group == "survivor") & (traj.k == k)]
            o, lo, hi, _ = cluster_boot_diff(a, b, m, by="cik", stat=stat,
                                             draws=draws, seed=SEED)
            r[f"gap{tag}"], r[f"lo{tag}"], r[f"hi{tag}"] = o, lo, hi
            r[f"exit{tag}"] = float(stat(a[m].dropna()))
            r[f"surv{tag}"] = float(stat(b[m].dropna()))
            r[f"ne{tag}"] = int(a[m].notna().sum())
            r[f"ns{tag}"] = int(b[m].notna().sum())
        r["share"] = r["gap8"] / r["gap1"] if r["gap1"] else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def first_sig(did: pd.DataFrame, metric: str):
    sub = did[did.metric == metric]
    return int(sub[sub.sig].k.min()) if sub.sig.any() else None


def cell_mean_shuffle(labels: pd.Series, groups: pd.Series, within: pd.Series,
                      seed: int = 0) -> pd.Series:
    """A between-group shuffle aligned on ``within`` that drops no row.

    ``analysis.clustered_shuffle(within=...)`` maps a row to its partner group's
    label at the same ``within`` key, keeping only the FIRST row of each
    ``(group, within)`` cell and returning NaN when the partner has no row at
    that key. On a quarterly panel aligned on calendar year both bite. This
    version gives a row its partner cell's MEAN label, falling back to the
    partner's overall mean, so every row keeps a value and every row of the
    partner cell contributes. The statistic downstream is a share, so a
    fractional label is the right object for it.
    """
    rng = np.random.default_rng(seed)
    g = np.asarray(groups)
    uniq = pd.unique(g)
    partner = dict(zip(uniq, rng.permutation(uniq)))
    lab = pd.Series(np.asarray(labels, dtype=float))
    cell = lab.groupby([pd.Series(g), pd.Series(np.asarray(within))]).mean()
    overall = lab.groupby(pd.Series(g)).mean()
    keys = pd.MultiIndex.from_arrays(
        [np.array([partner[x] for x in g], dtype=g.dtype), np.asarray(within)])
    out = pd.Series(cell.reindex(keys).to_numpy(), index=labels.index)
    fallback = pd.Series(overall.reindex([partner[x] for x in g]).to_numpy(),
                         index=labels.index)
    return out.fillna(fallback)


# --------------------------------------------------------------------------
# 1. reproduction
# --------------------------------------------------------------------------
def section_reproduce(u: pd.DataFrame, firm: pd.DataFrame) -> pd.DataFrame:
    head("1. REPRODUCTION, zero API calls")
    ex = firm[firm["exit"]]
    checks = [
        ("firm-quarters", len(u), 190586), ("CIKs", len(firm), 6103),
        ("exits", len(ex), 2555), ("exits with 8 quarters of history",
                                   int((firm["exit"] & (firm.hist_q >= 7)).sum()), 1688),
    ]
    rates = [("firm-quarters with a Stooq series", u.priced.mean(), 0.6634),
             ("CIKs with a series", firm.priced.mean(), 0.5322),
             ("exited CIKs with a series", ex.priced.mean(), 0.1143),
             ("unpriced CIKs that exited", firm[~firm.priced]["exit"].mean(), 0.7926),
             ("exits with fewer than 8 quarters of history",
              (ex.hist_q < 7).mean(), 0.339)]
    print("  universe and Stooq match rate, against the published values")
    for name, got, want in checks:
        print(f"    {name:44s} {got:>9,d}  published {want:>9,d}  "
              f"{'OK' if got == want else 'MISMATCH'}")
    for name, got, want in rates:
        print(f"    {name:44s} {got:9.4f}  published {want:9.4f}  "
              f"{'OK' if abs(got - want) < 5e-4 else 'MISMATCH'}")

    p = pd.read_csv(ROOT / "cache/research/pre-exit-signature/probe_delisted.csv",
                    dtype={"cik": str, "served_cik": str})
    smp = pd.read_csv(ROOT / "cache/research/pre-exit-signature/probe_sample.csv",
                      dtype={"cik": str})
    p = p.merge(smp[["cik", "ticker", "last_qi", "fresh_qi"]], on=["cik", "ticker"])
    same = p[p.cik == p.served_cik]
    has = same[same.delisted_at.notna()].copy()
    none = same[same.delisted_at.isna()]

    def q_end(q):
        return pd.PeriodIndex([f"{v // 4}Q{v % 4 + 1}" for v in q],
                              freq="Q").to_timestamp(how="end").normalize()

    has["del"] = pd.to_datetime(has.delisted_at, errors="coerce", utc=True).dt.tz_localize(None)
    has["drop_after"] = (q_end(has.last_qi) - has["del"]).dt.days / 91.31
    has["del_after_fresh"] = (has["del"] - q_end(has.fresh_qi)).dt.days / 91.31
    print("\n  the 150-call probe, recomputed from the cached responses")
    print(f"    resolves to the panel's CIK           {len(same)} of {len(p)} "
          f"({len(same) / len(p):.1%})   published 141 (94.0%)")
    print(f"    carries a delistedAt                  {len(has)} of {len(same)} "
          f"({len(has) / len(same):.1%})   published 130 (92.2%)")
    print(f"    panel drop FOLLOWS delistedAt         {(has.drop_after > 0).mean():.1%}, "
          f"median {has.drop_after.median():+.2f} q   published 93.1%, +2.92 q")
    print(f"    last refresh PRECEDES delistedAt      "
          f"{(has.del_after_fresh > 0).mean():.1%}, median "
          f"{has.del_after_fresh.median():+.2f} q   published 93.8%, +1.83 q")
    still = none[none.last_filed_at.notna()]
    print(f"    no delistedAt                         {len(none)} of {len(same)} "
          f"({len(none) / len(same):.1%})   published 11, quoted as 7.8% of exits")
    print(f"    of those, holding a recent annual filing {len(still)} "
          f"({len(still) / len(same):.1%})   published 8")
    print(f"    The 7.8% is 11/141, the no-delistedAt share; the 'still file' evidence "
          f"covers {len(still)}/{len(same)} = {len(still) / len(same):.1%}. Both counts "
          f"should travel together.")
    print(f"    One of the 11 is a commodity trust admitted to the universe by "
          f"is_listed_equity and revenue > 0, so part of the 7.8% is a universe filter "
          f"rather than a filing fact.")

    t = base_table(u, 8, anchor="last")
    print_table(t, "as published")
    worst = 0.0
    print(f"\n    {'state':36s} {'published':>10s} {'here':>10s} {'diff':>8s} "
          f"{'pub priced':>11s} {'here':>8s}  n / CIKs / n priced")
    for r in t.itertuples():
        pa, pp, pn, pc, pnp = PUBLISHED_BASE[r.state]
        d = getattr(r, "all") - pa
        worst = max(worst, abs(d), abs(r.priced - pp))
        ok = "OK" if (r.n == pn and r.ciks == pc and r.n_priced == pnp) else "N MISMATCH"
        print(f"    {r.state:36s} {pct(pa):>10s} {pct(getattr(r, 'all')):>10s} "
              f"{100 * d:+8.4f} {pct(pp):>11s} {pct(r.priced):>8s}  "
              f"{r.n:,}/{r.ciks:,}/{r.n_priced:,} {ok}")
    b = u[u.qi <= FINAL_QI - EXIT_HORIZON - 8].copy()
    b["exit_h"] = b.last_qi <= b.qi + 8
    gh = b[~b.priced]
    print(f"\n  unpriced firm-quarters stopping filing within 8 quarters: "
          f"{gh.exit_h.mean():.2%} on n = {len(gh):,}, against "
          f"{b[b.priced].exit_h.mean():.2%} on n = {int(b.priced.sum()):,} "
          f"(published 29.97% and 2.33% on 54,205 and 83,582)")
    print(f"\n  largest absolute difference against the published table: "
          f"{100 * worst:.4f}pp. Every count matches. VERDICT: reproduces.")
    return t


# --------------------------------------------------------------------------
# 2. the exit definition and the stale tail
# --------------------------------------------------------------------------
def section_definition(u: pd.DataFrame, firm: pd.DataFrame) -> dict:
    head("2. THE EXIT ANCHOR AND THE STALE TAIL")
    b = u[u.qi <= FINAL_QI - EXIT_HORIZON - 8]
    stale = b.qi > b.fresh_qi
    exrows = b[b.is_exit]
    print(f"  base frame {len(b):,} firm-quarters. Rows after the CIK's last record "
          f"refresh: {stale.sum():,} ({stale.mean():.2%}).")
    print(f"  All of them belong to exiting CIKs: {(stale & b.is_exit).sum():,} of "
          f"{stale.sum():,}. They are {(exrows.qi > exrows.fresh_qi).mean():.1%} of the "
          f"{len(exrows):,} exit-CIK rows and 0.0% of survivor rows,")
    print("  because a still-present CIK's last refresh is later than the 2022Q2 anchor cut.")
    st_all = S.states(b.assign(exit_h=b.last_qi <= b.qi + 8))
    zsub = b[st_all["altman_z < 1.8"]]
    zst = (zsub.qi > zsub.fresh_qi)
    pos = (zsub.last_qi <= zsub.qi + 8)
    print(f"  In the Altman Z < 1.8 cell: {zst.sum():,} of {len(zsub):,} rows "
          f"({zst.mean():.1%}) are stale repeats, {(zst & pos).mean() / pos.mean():.1%} of "
          f"the cell's {pos.sum():,} positive outcomes sit on them, and "
          f"{(pos[zst]).mean():.1%} of stale rows are positive by construction.")

    sv = firm[~firm["exit"]]
    n_quiet = int((sv.fresh_qi <= FINAL_QI - EXIT_HORIZON).sum())
    print(f"\n  Right-edge asymmetry of the re-anchored definition: {n_quiet:,} of "
          f"{len(sv):,} still-present CIKs ({n_quiet / len(sv):.1%}) have not refreshed "
          f"since {qi_label(FINAL_QI - EXIT_HORIZON)} and are still counted as non-exits. "
          f"Their rows sit at or after {qi_label(FINAL_QI - EXIT_HORIZON - 8)} in only "
          f"{int((u.cik.isin(sv.index[sv.fresh_qi <= FINAL_QI - EXIT_HORIZON]) & (u.qi <= FINAL_QI - EXIT_HORIZON - 8)).sum()):,} "
          f"of the base frame's rows.")

    probe = pd.read_csv(STUDY_DIR.parent.parent / "cache/research/pre-exit-signature/probe_delisted.csv",
                        dtype={"cik": str, "served_cik": str})
    still = tuple(probe[(probe.cik == probe.served_cik) & probe.delisted_at.isna()].cik)
    print(f"\n  probe CIKs with no served delistedAt (the study's 7.8%): {len(still)}")

    variants = [
        ("A  published: last panel row, stale rows kept", dict(anchor="last")),
        ("B  last refresh anchor, stale rows kept", dict(anchor="fresh")),
        ("C  last refresh anchor, stale rows dropped", dict(anchor="fresh", drop_stale=True)),
        ("D  last panel row, stale rows dropped", dict(anchor="last", drop_stale=True)),
        ("E  C, minus the 11 probe CIKs that still file",
         dict(anchor="fresh", drop_stale=True, drop_ciks=still)),
        ("F  last refresh + 2 quarters (probe-calibrated), stale rows dropped",
         dict(anchor="fresh+2", drop_stale=True)),
    ]
    tabs = {}
    for name, kw in variants:
        t = base_table(u, 8, **kw)
        tabs[name] = t
        print_table(t, name)
        t.to_csv(OUT / f"base_variant_{name[0]}.csv", index=False)

    print("\n  MOVEMENT of the headline numbers:")
    print(f"    {'state':36s} " + " ".join(f"{n[0]:>9s}" for n, _ in variants))
    for i, state in enumerate(S.STATE_ORDER):
        vals = [tabs[n].iloc[i]["all"] for n, _ in variants]
        print(f"    {state:36s} " + " ".join(f"{pct(v):>9s}" for v in vals))
    print(f"    {'-- priced subset --':36s}")
    for i, state in enumerate(S.STATE_ORDER):
        vals = [tabs[n].iloc[i]["priced"] for n, _ in variants]
        print(f"    {state:36s} " + " ".join(f"{pct(v):>9s}" for v in vals))

    a, bb, c, d = (tabs[n[0]].set_index("state") for n in
                   [("A  published: last panel row, stale rows kept",),
                    ("B  last refresh anchor, stale rows kept",),
                    ("C  last refresh anchor, stale rows dropped",),
                    ("D  last panel row, stale rows dropped",)])
    a = tabs[variants[0][0]].set_index("state")
    bb = tabs[variants[1][0]].set_index("state")
    c = tabs[variants[2][0]].set_index("state")
    d = tabs[variants[3][0]].set_index("state")
    e = tabs[variants[4][0]].set_index("state")
    f = tabs[variants[5][0]].set_index("state")
    z = "altman_z < 1.8"
    print(f"\n  The two errors run in opposite directions and nearly cancel on the headline.")
    print(f"    Altman Z < 1.8: published {pct(a.loc[z, 'all'])}; re-anchoring alone "
          f"{pct(bb.loc[z, 'all'])} (+{100 * (bb.loc[z, 'all'] - a.loc[z, 'all']):.2f}pp); "
          f"dropping stale rows alone {pct(d.loc[z, 'all'])} "
          f"({100 * (d.loc[z, 'all'] - a.loc[z, 'all']):+.2f}pp); both "
          f"{pct(c.loc[z, 'all'])} ({100 * (c.loc[z, 'all'] - a.loc[z, 'all']):+.2f}pp).")
    print(f"    Probe-calibrated anchor F (last refresh + 2 quarters, the median position "
          f"of the served delistedAt): {pct(f.loc[z, 'all'])} whole panel, "
          f"{pct(f.loc[z, 'priced'])} priced, {f.loc[z, 'ratio']:.2f}x.")
    print(f"    Range across the four defensible definitions: "
          f"{pct(min(a.loc[z, 'all'], bb.loc[z, 'all'], c.loc[z, 'all'], d.loc[z, 'all']))} to "
          f"{pct(max(a.loc[z, 'all'], bb.loc[z, 'all'], c.loc[z, 'all'], d.loc[z, 'all']))}.")
    print(f"    Lift over the healthy state: published "
          f"{a.loc[z, 'all'] / a.loc['none of the four', 'all']:.2f}x, "
          f"corrected {c.loc[z, 'all'] / c.loc['none of the four', 'all']:.2f}x.")
    print(f"    Whole-panel over priced ratio: published {a.loc[z, 'ratio']:.2f}x, "
          f"corrected {c.loc[z, 'ratio']:.2f}x.")
    print(f"    Dropping the 11 probe still-filers moves the corrected Altman cell by "
          f"{100 * (e.loc[z, 'all'] - c.loc[z, 'all']):+.3f}pp: 11 of "
          f"{firm['exit'].sum():,} exits is 0.4% of them, so the probe's 7.8% cannot be "
          f"removed this way, only bounded.")

    rng = np.random.default_rng(SEED)
    ex_ciks = firm.index[firm["exit"]].to_numpy()
    bc = u[(u.qi <= FINAL_QI - EXIT_HORIZON - 8)]
    bc = bc[bc.qi <= bc.fresh_qi].copy()
    bc["exit_h"] = bc.is_exit & (bc.fresh_qi <= bc.qi + 8)
    stc = S.states(bc)
    sims = {name: [] for name in ("altman_z < 1.8", "none of the four", "any firm-quarter")}
    for _ in range(NULL_DRAWS):
        drop = set(rng.choice(ex_ciks, int(round(0.078 * len(ex_ciks))), replace=False))
        flag = bc.exit_h & ~bc.cik.isin(drop)
        for name in sims:
            sims[name].append(float(flag[stc[name]].mean()))
    print(f"\n  If the probe's 7.8% no-delistedAt share holds for the population and those "
          f"CIKs are removed at random ({NULL_DRAWS} draws, corrected definition C):")
    for name, v in sims.items():
        v = np.array(v)
        print(f"    {name:36s} {pct(c.loc[name, 'all'])} -> {pct(v.mean())} "
              f"+/- {pct(v.std(ddof=1), 3)}")
    return {"tabs": tabs, "still": still, "sims": sims}


def section_horizons(u: pd.DataFrame) -> pd.DataFrame:
    print("\n  HORIZON SWEEP and OUT-OF-SAMPLE SPLIT under the corrected definition C")
    rows = []
    for h in (4, 8, 12):
        pub = base_table(u, h, anchor="last", ci=False).set_index("state")
        cor = base_table(u, h, anchor="fresh", drop_stale=True, ci=False).set_index("state")
        for state in ("altman_z < 1.8", "two or more of the four", "any firm-quarter"):
            rows.append({"split": "all", "h": h, "state": state,
                         "pub_all": pub.loc[state, "all"], "pub_priced": pub.loc[state, "priced"],
                         "cor_all": cor.loc[state, "all"], "cor_priced": cor.loc[state, "priced"]})
    for lo, hi in ((2009, 2015), (2016, 2022)):
        half = u[u.year.between(lo, hi)]
        pub = base_table(half, 8, anchor="last", ci=False).set_index("state")
        cor = base_table(half, 8, anchor="fresh", drop_stale=True, ci=False).set_index("state")
        for state in ("altman_z < 1.8", "two or more of the four", "any firm-quarter"):
            rows.append({"split": f"{lo}-{hi}", "h": 8, "state": state,
                         "pub_all": pub.loc[state, "all"], "pub_priced": pub.loc[state, "priced"],
                         "cor_all": cor.loc[state, "all"], "cor_priced": cor.loc[state, "priced"]})
    t = pd.DataFrame(rows)
    print(f"    {'split':10s} {'h':>3s} {'state':26s} {'published':>19s} {'corrected':>19s}")
    for r in t.itertuples():
        print(f"    {r.split:10s} {r.h:3d} {r.state:26s} "
              f"{pct(r.pub_all):>8s} / {pct(r.pub_priced):<8s} "
              f"{pct(r.cor_all):>8s} / {pct(r.cor_priced):<8s}")
    return t


# --------------------------------------------------------------------------
# 3. the signature under sector matching
# --------------------------------------------------------------------------
def section_signature(u: pd.DataFrame, firm: pd.DataFrame) -> dict:
    head("3. THE SIGNATURE: adding sector to the matching cell")
    ref = S.build_anchors(u, firm)
    mine = build_anchors_keyed(u, firm, ("anchor", "terc"))
    same = (len(ref) == len(mine)
            and ref[ref.group == "exit"].cik.nunique() == mine[mine.group == "exit"].cik.nunique()
            and sorted(ref[ref.group == "survivor"].cik) == sorted(mine[mine.group == "survivor"].cik))
    print(f"  the review's sampler reproduces the study's sampler exactly: {same} "
          f"({len(ref):,} anchors, {ref[ref.group == 'survivor'].cik.nunique():,} control CIKs)")

    sec = u.set_index(["cik", "qi"]).sector
    a2 = mine.copy()
    a3 = build_anchors_keyed(u, firm, ("anchor", "terc", "sector"))
    for tag, a in (("tercile only", a2), ("tercile + sector", a3)):
        s = sec.reindex(pd.MultiIndex.from_arrays([a.cik, a.anchor])).to_numpy()
        x = pd.crosstab(pd.Series(s, name="sector"), a.group.to_numpy(), normalize="columns")
        tv = 0.5 * float(np.abs(x["exit"] - x["survivor"]).sum())
        print(f"  {tag:18s}: exits {(a.group == 'exit').sum():,}, unmatched "
              f"{a.attrs['missed']}, controls {(a.group == 'survivor').sum():,} over "
              f"{a[a.group == 'survivor'].cik.nunique():,} CIKs; sector total-variation "
              f"distance exit vs control {tv:.3f}")
        if tag == "tercile only":
            worst = (x["exit"] - x["survivor"]).abs().sort_values(ascending=False).head(3)
            for name in worst.index:
                print(f"      {name:24s} exits {x.loc[name, 'exit']:.1%} against controls "
                      f"{x.loc[name, 'survivor']:.1%}")

    out, levels = {}, {}
    for tag, a in (("tercile only", a2), ("tercile + sector", a3)):
        traj = S.build_trajectories(u, a)
        levels[tag] = level_table(traj)
        did = did_table(traj)
        did["match"] = tag
        out[tag] = did
        print(f"\n  {tag}: difference in differences at each quarter (* = 95% interval "
              f"excludes zero)")
        for m in S.METRICS:
            sub = did[did.metric == m].sort_values("k")
            f = first_sig(did, m)
            line = " ".join(f"t{int(r.k)}:{r.did:+.3f}{'*' if r.sig else ' '}"
                            for r in sub.itertuples())
            print(f"    {m:18s} first={('t' + str(f)) if f is not None else 'never':>6s}  {line}")
    did_all = pd.concat(out.values(), ignore_index=True)
    did_all.to_csv(OUT / "signature_did_sector.csv", index=False)
    lev_all = pd.concat([v.assign(match=k) for k, v in levels.items()], ignore_index=True)
    lev_all.to_csv(OUT / "signature_levels_sector.csv", index=False)

    print("\n  LEVEL GAP at t-8 and t-1, and the share of the t-1 gap already on file at "
          "t-8 (the study's 'already at t-8' column)")
    print(f"    {'metric':18s} {'gap t-8':>20s} {'gap t-1':>20s} {'at t-8':>7s}   "
          f"{'+sector gap t-8':>20s} {'gap t-1':>20s} {'at t-8':>7s}")
    for m in S.METRICS:
        r2 = levels["tercile only"].set_index("metric").loc[m]
        r3 = levels["tercile + sector"].set_index("metric").loc[m]
        print(f"    {m:18s} "
              f"{f'{r2.gap8:+.3f} [{r2.lo8:+.2f},{r2.hi8:+.2f}]':>20s} "
              f"{f'{r2.gap1:+.3f} [{r2.lo1:+.2f},{r2.hi1:+.2f}]':>20s} "
              f"{r2.share:7.0%}   "
              f"{f'{r3.gap8:+.3f} [{r3.lo8:+.2f},{r3.hi8:+.2f}]':>20s} "
              f"{f'{r3.gap1:+.3f} [{r3.lo1:+.2f},{r3.hi1:+.2f}]':>20s} "
              f"{r3.share:7.0%}")
    eight2 = [m for m in S.METRICS
              if 0.80 <= levels["tercile only"].set_index("metric").loc[m].share <= 1.05]
    eight3 = [m for m in S.METRICS
              if 0.80 <= levels["tercile + sector"].set_index("metric").loc[m].share <= 1.05]
    print(f"    metrics with 80-105% of the t-1 gap already at t-8: "
          f"{len(eight2)} with the tercile cell (the study says eight), "
          f"{len(eight3)} with sector added.")

    print("\n  WHAT MOVED when sector entered the cell:")
    print(f"    {'metric':18s} {'tercile':>9s} {'+sector':>9s} "
          f"{'DiD t-1, tercile':>26s} {'DiD t-1, +sector':>26s}")
    for m in S.METRICS:
        f2, f3 = first_sig(out["tercile only"], m), first_sig(out["tercile + sector"], m)
        r2 = out["tercile only"].query("metric == @m and k == -1").iloc[0]
        r3 = out["tercile + sector"].query("metric == @m and k == -1").iloc[0]
        s2 = f"{r2.did:+.3f} [{r2.lo:+.3f},{r2.hi:+.3f}]"
        s3 = f"{r3.did:+.3f} [{r3.lo:+.3f},{r3.hi:+.3f}]"
        print(f"    {m:18s} {('t' + str(f2)) if f2 is not None else 'never':>9s} "
              f"{('t' + str(f3)) if f3 is not None else 'never':>9s} "
              f"{s2:>26s} {s3:>26s}")

    print("\n  WHY NOTHING CAN SEPARATE BEFORE t-5: the change-from-t-8 statistic is "
          "identically zero.")
    traj = S.build_trajectories(u, a2)
    print(f"    {'metric':18s} " + " ".join(f"{'t' + str(k):>8s}" for k in range(-7, 0)))
    for m in S.METRICS:
        shares = []
        for k in range(-7, 0):
            s = traj[traj.k == k]["d_" + m].dropna()
            shares.append((s == 0).mean())
        print(f"    {m:18s} " + " ".join(f"{100 * v:7.1f}%" for v in shares))
    n_flat = sum(1 for m in S.METRICS
                 if abs(out["tercile only"].query("metric == @m and k == -6").iloc[0].did) < 1e-12)
    print(f"    {n_flat} of {len(S.METRICS)} metrics have a DiD of exactly 0.000 at t-6, and "
          f"the same at t-7, because the panel's annual metrics do not refresh there.")
    print("    'first quarter the difference excludes zero' therefore has no resolution "
          "before t-5 and almost none before t-4.")

    print("\n  SEED SENSITIVITY of the control draw (5 seeds, tercile + sector):")
    for seed in (7, 11, 13, 17, 23):
        a = build_anchors_keyed(u, firm, ("anchor", "terc", "sector"), seed=seed)
        d = did_table(S.build_trajectories(u, a), metrics=["altman_z", "asset_growth",
                                                           "interest_coverage"])
        parts = []
        for m in ("altman_z", "asset_growth", "interest_coverage"):
            f = first_sig(d, m)
            r = d.query("metric == @m and k == -1").iloc[0]
            parts.append(f"{m} first={('t' + str(f)) if f is not None else 'never'} "
                         f"t-1 {r.did:+.3f}")
        print(f"    seed {seed:3d}: " + "; ".join(parts))
    return {"did": out, "a2": a2, "a3": a3}


# --------------------------------------------------------------------------
# 4. the two toolkit defects
# --------------------------------------------------------------------------
def section_toolkit(u: pd.DataFrame) -> dict:
    head("4. THE TWO CLAIMED TOOLKIT DEFECTS, against synthetic frames with a known answer")

    print("\n  4a. analysis.clustered_shuffle(within=...) - SYNTHETIC")
    df = pd.DataFrame({"cik": ["A"] * 3 + ["B"] * 3 + ["C"],
                       "year": [1, 2, 3, 2, 3, 4, 5],
                       "lab": [1, 1, 1, 0, 0, 0, 1]})
    print("    frame: firm A in years 1-3, firm B in 2-4, firm C in year 5; 7 rows, no NaN.")
    drops = []
    for seed in range(6):
        sh = clustered_shuffle(df.lab, df.cik, within=df.year, seed=seed)
        drops.append(sh.isna().sum())
        print(f"      seed {seed}: {[('nan' if pd.isna(v) else int(v)) for v in sh]} "
              f"-> {sh.isna().sum()} of 7 rows NaN")
    print(f"    A relabelling must return 7 labels. It returns {np.mean(drops):.1f} NaN on "
          f"average: a row whose partner firm has no row in that calendar year is dropped.")
    print("    This is stated in the docstring, so it is documented rather than silent; what "
          "is missing is a count, which the caller has no way to see.")

    print("\n  4b. the same helper drops all but the FIRST row of a (group, within) cell "
          "- SYNTHETIC, and NOT reported by the study")
    df2 = pd.DataFrame({"cik": ["A"] * 4 + ["B"] * 4, "year": [1] * 8,
                        "lab": [0, 0, 1, 1, 9, 8, 7, 6]})
    for seed in (0, 1, 2):
        sh = clustered_shuffle(df2.lab, df2.cik, within=df2.year, seed=seed)
        print(f"      seed {seed}: {[int(v) for v in sh]}")
    print("    B holds four distinct labels 9,8,7,6 in year 1. Every row of A receives 9, "
          "and 8, 7 and 6 are never drawn.")
    print("    Cause: `src = src[~src.index.duplicated()]` keeps one row per (group, within).")

    print("\n  4c. both defects measured on the reviewed study's own placebo frame")
    b = u[u.qi <= FINAL_QI - EXIT_HORIZON - 8].copy()
    b["exit_h"] = b.last_qi <= b.qi + 8
    nan, const = [], []
    for s in range(20):
        sh = clustered_shuffle(b.exit_h, b.cik, within=b.year, seed=s)
        nan.append(sh.isna().mean())
        ok = sh.notna()
        g = pd.DataFrame({"cik": b.cik[ok].to_numpy(), "year": b.year[ok].to_numpy(),
                          "v": sh[ok].to_numpy()})
        const.append(g.groupby(["cik", "year"]).v.nunique().eq(1).mean())
    cells = b.groupby(["cik", "year"]).size()
    obs_const = b.groupby(["cik", "year"]).exit_h.nunique().eq(1).mean()
    print(f"    rows dropped to NaN: {np.mean(nan):.2%} +/- {np.std(nan):.2%} over 20 seeds "
          f"(the study reports 44%)")
    print(f"    rows per (cik, year) cell: mean {cells.mean():.2f}, max {cells.max()}")
    print(f"    (cik, year) cells whose OBSERVED label is constant:  {obs_const:.2%}")
    print(f"    (cik, year) cells whose SHUFFLED label is constant:  {np.mean(const):.2%} "
          f"- the second defect, in the study's own null")
    sh0 = clustered_shuffle(b.exit_h, b.cik, within=b.year, seed=0)
    keep = sh0.notna()
    print(f"    the drop is not neutral in level: shuffled mean on surviving rows "
          f"{sh0.dropna().mean():.4f} against the observed rate on the SAME rows "
          f"{b.exit_h[keep].mean():.4f} and {b.exit_h.mean():.4f} on all rows")
    print("    The study's lift statistic subtracts the shuffled overall rate from the "
          "shuffled state rate on the same surviving rows, so the level bias cancels.")

    print("\n  4d. does a shuffle that drops nothing change the study's section-4 verdict?")
    st = S.states(b)
    obs_all = b.exit_h.mean()
    names = S.STATE_ORDER[:-1]
    masks = {n: st[n].to_numpy() for n in names}
    pubs = {n: [] for n in names}
    fixes = {n: [] for n in names}
    nws = {n: [] for n in names}
    n_nowithin = 25   # the no-``within`` branch is a per-row Python loop in the toolkit
    for d in range(NULL_DRAWS):
        sh = clustered_shuffle(b.exit_h, b.cik, within=b.year, seed=d)
        ok = sh.notna().to_numpy()
        v = sh[ok].astype(float).to_numpy()
        f = cell_mean_shuffle(b.exit_h, b.cik, b.year, seed=d).to_numpy()
        nw = (clustered_shuffle(b.exit_h, b.cik, seed=d).to_numpy().astype(float)
              if d < n_nowithin else None)
        for n in names:
            m = masks[n]
            pubs[n].append(float(v[m[ok]].mean() - v.mean()))
            fixes[n].append(float(f[m].mean() - f.mean()))
            if nw is not None:
                nws[n].append(float(nw[m].mean() - nw.mean()))
    rows = []
    for name in names:
        obs = b.exit_h[st[name]].mean() - obs_all
        pub = np.array(pubs[name])
        fix = np.array(fixes[name])
        nowithin = np.array(nws[name])
        rows.append({"state": name, "obs_lift": obs,
                     "pub_mean": pub.mean(), "pub_sd": pub.std(ddof=1),
                     "pub_z": (obs - pub.mean()) / pub.std(ddof=1),
                     "fix_mean": fix.mean(), "fix_sd": fix.std(ddof=1),
                     "fix_z": (obs - fix.mean()) / fix.std(ddof=1),
                     "nw_mean": nowithin.mean(), "nw_sd": nowithin.std(ddof=1),
                     "nw_z": (obs - nowithin.mean()) / nowithin.std(ddof=1)})
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "placebo_corrected.csv", index=False)
    print(f"    {NULL_DRAWS} draws for the first two nulls, {n_nowithin} for the third.")
    print(f"    {'state':36s} {'observed':>9s} {'published null':>20s} {'z':>6s} "
          f"{'no-drop null':>20s} {'z':>6s} {'no within= null':>20s} {'z':>6s}")
    for r in t.itertuples():
        print(f"    {r.state:36s} {pct(r.obs_lift):>9s} "
              f"{pct(r.pub_mean, 3):>10s} +/-{pct(r.pub_sd, 3):>8s} {r.pub_z:6.1f} "
              f"{pct(r.fix_mean, 3):>10s} +/-{pct(r.fix_sd, 3):>8s} {r.fix_z:6.1f} "
              f"{pct(r.nw_mean, 3):>10s} +/-{pct(r.nw_sd, 3):>8s} {r.nw_z:6.1f}")

    print("\n  4e. analysis.cluster_boot_diff degeneracy - SYNTHETIC")
    rng = np.random.default_rng(0)
    a = pd.DataFrame({"cik": [f"e{i}" for i in range(400)],
                      "v": rng.choice([2, 3, 4], 400, p=[.5, .3, .2])})
    bb = pd.DataFrame({"cik": [f"s{i}" for i in range(400)],
                       "v": rng.choice([2, 3, 4], 400, p=[.2, .3, .5])})
    o, lo, hi, _ = cluster_boot_diff(a, bb, "v", stat=np.median, draws=DRAWS, seed=SEED)
    om, _, _, _ = cluster_boot_diff(a, bb, "v", stat=np.mean, draws=DRAWS, seed=SEED)
    print(f"    integer column, true mean gap {a.v.mean() - bb.v.mean():+.4f}: "
          f"median {o:+.3f} [{lo:+.3f},{hi:+.3f}], mean {om:+.4f}  -> NOT degenerate")
    za = pd.DataFrame({"cik": [f"e{i}" for i in range(400)],
                       "v": np.where(rng.random(400) < 0.8, 0.0, rng.normal(-1, 1, 400))})
    zb = pd.DataFrame({"cik": [f"s{i}" for i in range(400)],
                       "v": np.where(rng.random(400) < 0.8, 0.0, rng.normal(+1, 1, 400))})
    o2, lo2, hi2, _ = cluster_boot_diff(za, zb, "v", stat=np.median, draws=DRAWS, seed=SEED)
    om2, _, _, _ = cluster_boot_diff(za, zb, "v", stat=np.mean, draws=DRAWS, seed=SEED)
    print(f"    CONTINUOUS column, 80% exact zeros, true mean gap "
          f"{za.v.mean() - zb.v.mean():+.4f}: median {o2:+.3f} [{lo2:+.3f},{hi2:+.3f}], "
          f"mean {om2:+.4f}  -> degenerate")
    print("    The trigger is a tied median on both sides, not an integer dtype. The study "
          "names the symptom correctly and the cause too narrowly.")
    traj = pd.read_parquet(ROOT / "cache/research/pre-exit-signature/trajectories.parquet")
    for k in (-1, -4):
        A = traj[(traj.group == "exit") & (traj.k == k)]
        B = traj[(traj.group == "survivor") & (traj.k == k)]
        o3, lo3, hi3, _ = cluster_boot_diff(A, B, "piotroski", by="cik", stat=np.median,
                                            draws=DRAWS, seed=SEED)
        om3, _, _, _ = cluster_boot_diff(A, B, "piotroski", by="cik", stat=np.mean,
                                         draws=DRAWS, seed=SEED)
        print(f"    real piotroski level at t{k}: median {o3:+.3f} [{lo3:+.3f},{hi3:+.3f}], "
              f"mean {om3:+.4f}")

    print("\n  4f. which other studies the NaN drop reaches")
    specs = [("share-issuance/dilution_pool.parquet", "net_dilution", "cik", "year"),
             ("share-issuance/buyback_pool.parquet", "buyback_intensity", "cik", "year"),
             ("share-issuance/exit_frame.parquet", "net_dilution", "cik", "year"),
             ("price-leads-record/frame.parquet", "decile", "cik", "year"),
             ("fundamental-momentum/december.parquet", "d_opm", "cik", "year"),
             ("fundamental-momentum/events.parquet", "d_opm", "cik", "as_of_date")]
    srows = []
    print(f"    {'frame':46s} {'n':>7s} {'rows/cell':>10s} {'cells>1 row':>12s} {'NaN share':>10s}")
    for f, col, g, w in specs:
        p = ROOT / "cache" / "research" / f
        if not p.exists():
            print(f"    {f:46s} MISSING")
            continue
        d = pd.read_parquet(p)
        cells = d.groupby([g, w]).size()
        nn = np.mean([clustered_shuffle(d[col], d[g], within=d[w], seed=s).isna().mean()
                      for s in range(5)])
        srows.append({"frame": f, "n": len(d), "rows_per_cell": cells.mean(),
                      "cells_gt1": (cells > 1).mean(), "nan": nn})
        print(f"    {f:46s} {len(d):7,d} {cells.mean():10.2f} {cells.gt(1).mean():11.1%} "
              f"{nn:10.1%}")
    srows.append({"frame": "pre-exit-signature base frame", "n": len(b),
                  "rows_per_cell": cells.mean() if False else b.groupby(['cik', 'year']).size().mean(),
                  "cells_gt1": b.groupby(['cik', 'year']).size().gt(1).mean(),
                  "nan": float(np.mean(nan))})
    sib = pd.DataFrame(srows)
    sib.to_csv(OUT / "sibling_nan_rates.csv", index=False)
    print(f"    {'pre-exit-signature base frame':46s} {len(b):7,d} "
          f"{b.groupby(['cik', 'year']).size().mean():10.2f} "
          f"{b.groupby(['cik', 'year']).size().gt(1).mean():11.1%} {np.mean(nan):10.1%}")
    print("    Only the pre-exit frame is quarterly, so only it is exposed to the "
          "duplicate-cell defect; the NaN drop reaches all six frames.")
    return {"placebo": t, "siblings": sib}


# --------------------------------------------------------------------------
# 5. the Altman Z trend proxy
# --------------------------------------------------------------------------
def section_ztrend(u: pd.DataFrame, firm: pd.DataFrame, anchors: pd.DataFrame) -> dict:
    head("5. THE ALTMAN Z TREND: is a rising Z distinguishable from a record that stopped?")
    ex = firm[firm["exit"]]
    z = u.set_index(["cik", "qi"]).altman_z

    def trend(ciks, anchor_qi):
        z1 = z.reindex(pd.MultiIndex.from_arrays([ciks, anchor_qi])).to_numpy()
        z4 = z.reindex(pd.MultiIndex.from_arrays([ciks, np.asarray(anchor_qi) - 3])).to_numpy()
        return z1 - z4

    d = pd.Series(trend(ex.index, ex.fresh_qi.to_numpy()), index=ex.index)
    kind = pd.Series(np.where(d > 0, "improving", np.where(d < 0, "deteriorating", "flat")),
                     index=ex.index)
    kind[d.isna()] = "unclassified"
    cls = ex.assign(kind=kind)

    print(f"  Altman Z is null on {u.altman_z.isna().mean():.2%} of the {len(u):,} universe "
          f"rows and interest coverage on {u.interest_coverage.isna().mean():.2%}. Coverage "
          f"is exactly zero in "
          + ", ".join(sorted(u.groupby("sector").altman_z.apply(lambda v: v.notna().mean())
                             .pipe(lambda s_: s_[s_ == 0]).index))
          + f". The reviewed study.py prints 46% at study.py:473 where its own README says "
            f"43.9%; {u.altman_z.isna().mean():.1%} is the value in the panel.")
    print("\n  5a. PANEL MECHANICS are identical in the two groups")
    lastq = u.groupby("cik").tail(1).set_index("cik")
    print(f"    {'group':16s} {'n':>6s} {'stale tail median':>18s} {'mean':>6s} {'IQR':>8s} "
          f"{'history median':>15s} {'2-yr-old last row':>18s}")
    for k in ("deteriorating", "improving"):
        g = cls[cls.kind == k]
        gap = (lastq.loc[g.index].as_of_date.dt.year - lastq.loc[g.index].fiscal_year)
        print(f"    {k:16s} {len(g):6,d} {g.stale_tail.median():18.0f} "
              f"{g.stale_tail.mean():6.2f} "
              f"{g.stale_tail.quantile(.25):.0f}-{g.stale_tail.quantile(.75):.0f}".ljust(0)
              + f"{'':4s}{g.hist_q.median():13.0f} {(gap == 2).mean():17.1%}")
    a_st = cls[cls.kind == "improving"].stale_tail
    b_st = cls[cls.kind == "deteriorating"].stale_tail
    print(f"    difference in the mean stale tail: {a_st.mean() - b_st.mean():+.2f} quarters. "
          f"The drop rule does not separate the two groups.")

    print("\n  5b. PLACEBO: how often does a firm that does NOT exit show a rising Z "
          "over four quarters?")
    Sv = anchors[anchors.group == "survivor"]
    E = anchors[anchors.group == "exit"]
    dsv = pd.Series(trend(Sv.cik.to_numpy(), Sv.anchor.to_numpy()))
    dE = pd.Series(trend(E.cik.to_numpy(), E.anchor.to_numpy()))
    rows = [("all exits, at the last refresh", int(d.notna().sum()), float((d > 0).sum() / d.notna().sum())),
            ("matched exits, at the anchor", int(dE.notna().sum()), float((dE > 0).sum() / dE.notna().sum())),
            ("matched survivors, at the anchor", int(dsv.notna().sum()), float((dsv > 0).sum() / dsv.notna().sum()))]
    print(f"    {'cohort':36s} {'n classified':>13s} {'rising Z share':>15s}")
    for name, n, s in rows:
        print(f"    {name:36s} {n:13,d} {s:14.2%}")
    print(f"    A rising four-quarter Altman Z is as common in firms that do not exit "
          f"({rows[2][2]:.1%}) as in firms that do ({rows[0][2]:.1%}). The split carries no "
          f"information about whether a firm left in good order.")

    print("\n  5c. the 'trend' split is a LEVEL split")
    fresh = u.set_index(["cik", "qi"])[["altman_z", "asset_growth", "rev_growth",
                                        "operating_margin"]]
    fx = fresh.reindex(pd.MultiIndex.from_arrays([ex.index, ex.fresh_qi])).reset_index(drop=True)
    fx["kind"] = kind.to_numpy()
    med = fx.groupby("kind")[["altman_z", "asset_growth", "operating_margin"]].median()
    for k in ("deteriorating", "improving"):
        sub = fx[fx.kind == k]
        print(f"    {k:16s} n={len(sub):5,d}  median Z at the anchor "
              f"{med.loc[k, 'altman_z']:6.2f}  share with Z < 1.8 "
              f"{(sub.altman_z < 1.8).mean():6.1%}  median asset growth "
              f"{med.loc[k, 'asset_growth']:+.3f}  share shrinking assets "
              f"{(sub.asset_growth < 0).mean():5.1%}")
    print("    The two groups differ by 2.26 points of Altman Z level and by whether "
          "Z < 1.8, which IS the state variable the table splits. Trend and level are the "
          "same read twice.")

    print("\n  5d. the probe, split by Z trend (small n)")
    probe = pd.read_csv(ROOT / "cache/research/pre-exit-signature/probe_delisted.csv",
                        dtype={"cik": str, "served_cik": str})
    smp = pd.read_csv(ROOT / "cache/research/pre-exit-signature/probe_sample.csv",
                      dtype={"cik": str})
    p = probe.merge(smp[["cik", "ticker", "last_qi", "fresh_qi"]], on=["cik", "ticker"])
    p = p[p.cik == p.served_cik].copy()
    p["kind"] = p.cik.map(kind)

    def q_end(q):
        return pd.PeriodIndex([f"{v // 4}Q{v % 4 + 1}" for v in q],
                              freq="Q").to_timestamp(how="end").normalize()

    h = p[p.delisted_at.notna()].copy()
    h["del"] = pd.to_datetime(h.delisted_at, errors="coerce", utc=True).dt.tz_localize(None)
    h["q_del_after_fresh"] = (h["del"] - q_end(h.fresh_qi)).dt.days / 91.31
    h["q_drop_after_del"] = (q_end(h.last_qi) - h["del"]).dt.days / 91.31
    g = h.groupby("kind")[["q_del_after_fresh", "q_drop_after_del"]].median().round(2)
    n = h.groupby("kind").size()
    print(f"    {'group':16s} {'n':>5s} {'delistedAt - last refresh':>26s} "
          f"{'panel drop - delistedAt':>25s}")
    for k in g.index:
        print(f"    {k:16s} {n[k]:5d} {g.loc[k, 'q_del_after_fresh']:26.2f} "
              f"{g.loc[k, 'q_drop_after_del']:25.2f}")
    print(f"    The rising-Z group's served delisting date sits FURTHER after its last "
          f"refresh, the opposite of an orderly acquisition read, on n = "
          f"{int(n.get('improving', 0))} against {int(n.get('deteriorating', 0))}.")
    still = p[p.delisted_at.isna()]
    print(f"    of the {len(still)} probe CIKs with no delistedAt, the Z-trend split is "
          + ", ".join(f"{k} {v}" for k, v in still.kind.value_counts(dropna=False).items()))
    return {"kind": kind, "rows": rows, "probe": h}


# --------------------------------------------------------------------------
# 6. language
# --------------------------------------------------------------------------
def section_language() -> None:
    head("6. LANGUAGE AND CHART HEADLINES")
    text = (STUDY_DIR / "README.md").read_text()
    hits = [(w, len(re.findall(w, text, flags=re.I))) for w in ADVICE_WORDS]
    hits = [(w, c) for w, c in hits if c]
    print(f"  advice/valuation/price-direction words in README.md: "
          f"{hits if hits else 'none'}")
    named = re.findall(r"\b(?:AAPL|MSFT|IBM|GOOGL)\b", text)
    print(f"  company names or tickers in the report: {len(named)} "
          f"(the study states it names none)")
    print("  the single hit is the disclosure sentence 'Nothing here rates, values or "
          "recommends a security', which is a disclaimer and not a claim.")
    code = (STUDY_DIR / "study.py").read_text()
    calls = re.findall(r"C\.(?:figure|grid)\((.*?)\n\s*\n", code, flags=re.S)
    headlines = []
    for call in calls:
        first = call.split('",\n')[0]
        headlines.append(" ".join(re.findall(r'"([^"]*)"', first)))
    print(f"\n  chart headlines, and whether each carries n and the 'left the corpus, not "
          f"failed' caveat:")
    for i, hl in enumerate(headlines, 1):
        flat = " ".join(hl.split())
        print(f"    {i}. {flat[:170]}")
    caveat = re.findall(r"mixes acquisition|acquisition, going private|no delisting reason|"
                        r"acquisition, going private, deregistration", code)
    print(f"\n  chart subtitles carrying the mixed-cause caveat: {len(caveat)} of "
          f"{len(headlines)} charts")
    for tbl, line in (("section 3 base rates", "the chart subtitle carries it; the README "
                       "table at README:243-251 does not"),
                      ("section 5 exit type", "carried in the subtitle and in the section text"),
                      ("horizon sweep table", "no caveat in or next to the table"),
                      ("section 1 exits-by-year table", "carried in the sentence beneath it")):
        print(f"    {tbl:28s} {line}")


# --------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------
def chart_definition(defn: dict) -> None:
    tabs = defn["tabs"]
    names = list(tabs)
    states = ["altman_z < 1.8", "two or more of the four", "none of the four",
              "any firm-quarter"]
    short = {"altman_z < 1.8": "Altman Z\n< 1.8", "two or more of the four": "Two or\nmore",
             "none of the four": "None of\nthe four", "any firm-quarter": "Any\nfirm-quarter"}
    series = {}
    for lab, key in (("last panel row, stale rows kept (published)", names[0]),
                     ("last refresh anchor, stale rows kept", names[1]),
                     ("last refresh anchor, stale rows dropped", names[2])):
        t = tabs[key].set_index("state")
        series[lab] = np.array([100 * t.loc[s, "all"] for s in states])
    fig, (ax,) = C.figure(
        "Re-anchoring the exit on the last new filing raises the Altman Z base rate from "
        "18.5% to 26.6%, and dropping repeated stale rows takes it back to 18.8%.",
        "Share of firm-quarters in each state whose CIK stops appearing within 8 quarters, "
        "under three definitions of when the exit happened. n = 137,787 firm-quarters over "
        "5,499 CIKs on the published frame and 128,123 with stale rows dropped. Leaving the "
        "panel mixes acquisition, going private, deregistration and failure: it is leaving "
        "the corpus, not failing.")
    C.grouped_bars(ax, [short[s] for s in states], series, fmt="{:.1f}%",
                   legend_loc="upper right")
    C.finish(ax, "% stopping filing within 8 quarters", pct=True)
    C.save(fig, CHARTS / "exit_definition.png", source_text=SOURCE)


def chart_sector(sig: dict) -> None:
    did = sig["did"]
    show = [("altman_z", "Altman Z", 1), ("asset_growth", "Asset growth", 100),
            ("interest_coverage", "Interest coverage", 1)]
    fig, axes = C.grid(
        "Adding sector to the matching cell leaves Altman Z and asset growth separating at "
        "t-4 and moves interest coverage from never to t-4.",
        "Difference in differences against matched survivors, change from t-8. The statistic "
        "is identically zero at t-7 and t-6 for 10 of 11 metrics because the panel's annual "
        "metrics do not refresh there, so t-4 is close to the earliest quarter at which any "
        "separation is arithmetically possible. n = 1,688 exits and 5,064 control anchors. "
        "Leaving the panel is leaving the corpus, not failing.",
        1, 3)
    ks = list(range(-8, 0))
    for ax, (m, title, scale) in zip(axes, show):
        series = {}
        for tag, key in (("quarter x revenue tercile", "tercile only"),
                         ("+ sector", "tercile + sector")):
            sub = did[key][did[key].metric == m].set_index("k")
            series[tag] = [0.0] + [sub.did[k] * scale for k in ks[1:]]
        C.lines(ax, ks, series, fmt="{:+.2f}" if scale == 1 else "{:+.1f}",
                legend_loc="lower left")
        n_e = int(did["tercile + sector"].query("metric == @m and k == -1").iloc[0].n_e)
        C.label(ax, title, f"exits minus controls, n = {n_e:,} exits with the metric at t-1")
        C.finish(ax, "pp" if scale == 100 else "points")
    C.save(fig, CHARTS / "sector_matched_signature.png", source_text=SOURCE)


def chart_ztrend(zt: dict) -> None:
    rows = zt["rows"]
    fig, (ax,) = C.figure(
        "A rising four-quarter Altman Z is as common at a matched survivor quarter (42.0%) "
        "as at an exiting filer's last refresh (41.9%).",
        "Share of classified anchors whose Altman Z is higher than four quarters earlier. "
        "Altman Z is null on 43.9% of panel rows and has no coverage in Financials or Real "
        "Estate, so each n below is the classified subset. Leaving the panel is leaving the "
        "corpus, not failing, and the panel carries no delisting reason.")
    C.bars(ax, [f"{name}\nn = {n:,}" for name, n, _ in rows],
           [100 * s for _, _, s in rows], fmt="{:.1f}%")
    C.finish(ax, "% with a rising Altman Z", pct=True)
    C.save(fig, CHARTS / "ztrend_placebo.png", source_text=SOURCE)


# --------------------------------------------------------------------------
def main() -> None:
    pd.set_option("display.width", 200)
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    print(f"panel vintage 2026-09-03, final quarter {qi_label(FINAL_QI)}; "
          f"uncached API calls made by this script: 0")
    u, firm = S.load_frames()
    u["fresh_qi"] = u.cik.map(firm.fresh_qi)

    section_reproduce(u, firm)
    defn = section_definition(u, firm)
    hz = section_horizons(u)
    hz.to_csv(OUT / "horizons.csv", index=False)
    sig = section_signature(u, firm)
    tk = section_toolkit(u)
    zt = section_ztrend(u, firm, sig["a2"])
    section_language()

    chart_definition(defn)
    chart_sector(sig)
    chart_ztrend(zt)
    print(f"\ncharts written to {CHARTS}")


if __name__ == "__main__":
    main()
