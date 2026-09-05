"""The pre-exit signature, price-free.

What the point-in-time filing record shows in the eight quarters before a filer
leaves it, measured on the whole panel (every CIK, no prices needed), and what
share of firm-quarters in a simple distress state stop filing within eight
quarters on the whole universe against the priced subset.

Reproduces every number in ``research/pre-exit-signature/README.md`` from files
already on disk:

* ``cache/panel.csv`` - point-in-time panel, ``screen/export`` vintage 2026-09-03,
  final quarter 2026-06-30.
* ``cache/stooq_us/`` - Stooq daily bundle through 2026-08-14, read only to mark
  a ticker priced or not. No return is computed anywhere in this study, so
  there is nothing to market-adjust.
* ``cache/research/pre-exit-signature/probe_delisted.csv`` - 150 cached responses
  from ``/sec/fundamentals/{t}/as-of/2026-09-03?period=annual``, written by
  ``probe_delisted.py``. That script is the only thing here that spends an API
  call; this one makes none.

Run from the repository root::

    ./.venv/bin/python research/pre-exit-signature/study.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from distill_toolkit import charts as C  # noqa: E402
from distill_toolkit import stooq  # noqa: E402
from distill_toolkit.analysis import (  # noqa: E402
    cluster_boot_diff,
    cluster_bootstrap,
    clustered_shuffle,
    within_firm_shuffle,
)
from panel_base import (  # noqa: E402
    CACHE,
    CHARTS,
    EXIT_HORIZON,
    FINAL_QI,
    PANEL_VINTAGE,
    build_universe,
    qi_label,
)

SOURCE = ("Distill point-in-time panel, screen/export vintage 2026-09-03; "
          "Stooq US bundle 2026-08-14")

METRICS = ["rev_growth", "operating_margin", "fcf_margin", "interest_coverage", "altman_z",
           "piotroski", "m_score_5", "accruals_ratio", "asset_growth", "net_dilution", "dso"]
#: Metrics whose median quarter-on-quarter change is degenerate at zero because the
#: served value is an integer score; the mean is reported for these instead.
DISCRETE = ("piotroski",)
SEED = 7
DRAWS = 300
PLACEBO_DRAWS = 200


# --------------------------------------------------------------------------
# helpers written for this study (no toolkit equivalent exists)
# --------------------------------------------------------------------------
def tercile(s: pd.Series) -> pd.Series:
    """1/2/3 by rank within the group. ``pd.qcut`` raises on a group of four."""
    r = s.rank(method="first").to_numpy()
    n = len(r)
    return pd.Series(np.minimum(3, ((r - 1) * 3 // n + 1).astype(int)), index=s.index)


def rate_ci(flags: np.ndarray, groups: np.ndarray, draws: int = DRAWS,
            seed: int = SEED) -> tuple[float, float, float]:
    """Share true, with a firm-clustered bootstrap interval."""
    return cluster_bootstrap(np.asarray(flags, dtype=float), np.asarray(groups),
                             stat=np.mean, draws=draws, seed=seed)


def pct(x: float, nd: int = 2) -> str:
    return "nan" if not np.isfinite(x) else f"{100 * x:.{nd}f}%"


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Universe rows with derived columns, and one row per CIK."""
    u, firm = build_universe()
    lag = u[["cik", "qi", "revenue"]].copy()
    lag["qi"] += 4
    lag = lag.rename(columns={"revenue": "rev_lag4"})
    u = u.merge(lag, on=["cik", "qi"], how="left")
    u["rev_growth"] = u.revenue / u.rev_lag4 - 1
    u["first_qi"] = u.cik.map(firm.first_qi)
    u["last_qi"] = u.cik.map(firm.last_qi)
    u["is_exit"] = u.cik.map(firm["exit"])
    u["year"] = u.qi // 4
    idx = stooq.index()
    keyed = {t: stooq.stooq_key(t) in idx for t in u.ticker.unique()}
    u["priced"] = u.ticker.map(keyed)
    firm["priced"] = firm.ticker.map(keyed)
    return u, firm


# --------------------------------------------------------------------------
# 1. how many exits, when, and what the last panel row actually dates
# --------------------------------------------------------------------------
def section_exits(u: pd.DataFrame, firm: pd.DataFrame) -> dict:
    print("\n" + "=" * 78)
    print("1. EXITS: a CIK whose last panel row is 8+ quarters before 2026-06-30")
    print("=" * 78)
    ex = firm[firm["exit"]]
    print(f"panel vintage {PANEL_VINTAGE}, final quarter {qi_label(FINAL_QI)}, "
          f"exit cutoff {qi_label(FINAL_QI - EXIT_HORIZON)}")
    print(f"universe: {len(u):,} firm-quarters, {len(firm):,} CIKs "
          f"(listed equity, revenue > 0, ticker maps to one CIK)")
    print(f"exits: {len(ex):,} CIKs ({len(ex) / len(firm):.2%}); "
          f"still present: {(~firm['exit']).sum():,}")

    by_year = ex.groupby(ex.last_qi // 4).size()
    print("\nexits by panel-drop year")
    for y, n in by_year.items():
        print(f"  {y}  {n:4d}")
    by_q = ex.groupby(ex.last_qi % 4 + 1).size()
    print("exits by calendar quarter of the drop: "
          + ", ".join(f"Q{q} {n:,} ({n / len(ex):.1%})" for q, n in by_q.items()))

    print("\nthe last panel row is a drop date, not a filing date")
    print(f"  quarters between the last record refresh and the drop, exits:     "
          f"median {ex.stale_tail.median():.0f}, mean {ex.stale_tail.mean():.2f}, "
          f"IQR {ex.stale_tail.quantile(.25):.0f}-{ex.stale_tail.quantile(.75):.0f}")
    sv = firm[~firm["exit"]]
    print(f"  same for CIKs still in the panel:                                 "
          f"median {sv.stale_tail.median():.0f}, mean {sv.stale_tail.mean():.2f}")
    lastrow = u.groupby("cik").tail(1).set_index("cik")
    lag_ex = (lastrow.loc[ex.index].as_of_date.dt.year - lastrow.loc[ex.index].fiscal_year)
    print(f"  as-of year minus fiscal year on the last row, exits: "
          + ", ".join(f"{k}yr {v:,} ({v / len(ex):.0%})"
                      for k, v in lag_ex.value_counts().sort_index().items()))

    print("\nStooq match rate on the honest denominator")
    print(f"  firm-quarters with a series under the panel ticker: {u.priced.mean():.2%} "
          f"(n = {len(u):,})")
    print(f"  CIKs with a series:                                 {firm.priced.mean():.2%} "
          f"(n = {len(firm):,})")
    print(f"  exited CIKs with a series:                          {ex.priced.mean():.2%} "
          f"(n = {len(ex):,})")
    print(f"  share of exited CIKs that are unpriced:             {1 - ex.priced.mean():.2%}")
    print(f"  share of unpriced CIKs that exited:                 "
          f"{firm[~firm.priced]['exit'].mean():.2%} (n = {(~firm.priced).sum():,})")

    hist = firm[firm["exit"]].hist_q
    print(f"\nquarters of panel history before the last refresh, exits: "
          f"median {hist.median():.0f}, 25th {hist.quantile(.25):.0f}, "
          f"share with fewer than 8: {(hist < 7).mean():.1%}")
    return {"by_year": by_year, "n_exit": len(ex), "n_firm": len(firm)}


def section_probe(firm: pd.DataFrame) -> dict:
    print("\n" + "-" * 78)
    print("1b. API probe: the panel's last row against the served delistedAt (150 calls)")
    print("-" * 78)
    f = CACHE / "probe_delisted.csv"
    if not f.exists():
        print("  probe_delisted.csv not present; run probe_delisted.py to regenerate it")
        return {}
    d = pd.read_csv(f, dtype={"cik": str, "served_cik": str})
    s = pd.read_csv(CACHE / "probe_sample.csv", dtype={"cik": str})
    d = d.merge(s[["cik", "ticker", "last_qi", "fresh_qi"]], on=["cik", "ticker"])
    print(f"  sampled exited CIKs: {len(d)}; HTTP status: "
          + ", ".join(f"{k} {v}" for k, v in d.status.value_counts().items()))
    same = d[d.cik == d.served_cik]
    print(f"  ticker resolves to the panel's CIK: {len(same)} ({len(same) / len(d):.1%}); "
          f"resolves to another CIK: {len(d) - len(same)} ({1 - len(same) / len(d):.1%})")
    has = same[same.delisted_at.notna()].copy()
    none = same[same.delisted_at.isna()]
    print(f"  carries a delistedAt: {len(has)} of {len(same)} ({len(has) / len(same):.1%}); "
          f"carries none: {len(none)}")
    still = none[none.last_filed_at.notna()]
    print(f"    of the {len(none)} with no delistedAt, {len(still)} hold an annual filing "
          f"dated {still.last_filed_at.min()} or later, so they still file and left the export")

    def q_end(q):
        return pd.PeriodIndex([f"{v // 4}Q{v % 4 + 1}" for v in q],
                              freq="Q").to_timestamp(how="end").normalize()

    has["del"] = pd.to_datetime(has.delisted_at, errors="coerce", utc=True).dt.tz_localize(None)
    has["drop_date"] = q_end(has.last_qi)
    has["fresh_date"] = q_end(has.fresh_qi)
    has["q_drop_after_del"] = (has.drop_date - has["del"]).dt.days / 91.31
    has["q_del_after_fresh"] = (has["del"] - has.fresh_date).dt.days / 91.31
    print(f"  the panel's last row FOLLOWS delistedAt for "
          f"{(has.q_drop_after_del > 0).mean():.1%} of {len(has)}: "
          f"median {has.q_drop_after_del.median():+.2f} quarters "
          f"(IQR {has.q_drop_after_del.quantile(.25):+.2f} to "
          f"{has.q_drop_after_del.quantile(.75):+.2f})")
    print(f"  the last record refresh PRECEDES delistedAt for "
          f"{(has.q_del_after_fresh > 0).mean():.1%} of {len(has)}: "
          f"median {has.q_del_after_fresh.median():+.2f} quarters "
          f"(IQR {has.q_del_after_fresh.quantile(.25):+.2f} to "
          f"{has.q_del_after_fresh.quantile(.75):+.2f})")
    print("  the probe reads a date and never a reason: acquisition, going private, "
          "deregistration and bankruptcy all arrive as one delistedAt.")
    return {"probe": has, "n_probe": len(d), "n_same": len(same), "n_has": len(has),
            "n_none": len(none), "n_still": len(still)}


# --------------------------------------------------------------------------
# 2. the signature over the eight quarters before the record goes stale
# --------------------------------------------------------------------------
def build_anchors(u: pd.DataFrame, firm: pd.DataFrame) -> pd.DataFrame:
    """One anchor per exit, three matched survivor anchors, on quarter and revenue tercile.

    ``t-1`` is the anchor: the last quarter at which a new annual filing
    refreshed the CIK's panel row. ``t-8`` is seven quarters earlier. A survivor
    anchor is any quarter of a still-present CIK with seven quarters of history
    behind it and eight quarters of panel rows ahead of it, so the control is a
    firm-quarter that demonstrably did not exit over the same horizon.
    """
    ex = firm[firm["exit"] & (firm.hist_q >= 7)]
    e = pd.DataFrame({"cik": ex.index, "anchor": ex.fresh_qi.to_numpy(), "group": "exit"})
    s = u[(~u.is_exit) & (u.qi - u.first_qi >= 7) & (u.last_qi - u.qi >= EXIT_HORIZON)]
    s = s[["cik", "qi"]].rename(columns={"qi": "anchor"}).assign(group="survivor")
    cand = pd.concat([e, s], ignore_index=True)
    rev = u.set_index(["cik", "qi"]).revenue
    cand["revenue"] = rev.reindex(pd.MultiIndex.from_arrays([cand.cik, cand.anchor])).to_numpy()
    cand = cand.dropna(subset=["revenue"]).copy()
    cand["terc"] = cand.groupby("anchor").revenue.transform(tercile)
    E, S = cand[cand.group == "exit"], cand[cand.group == "survivor"]
    rng = np.random.default_rng(SEED)
    pools = {k: g.index.to_numpy() for k, g in S.groupby(["anchor", "terc"], observed=True)}
    picks, missed = [], 0
    for r in E.itertuples():
        pool = pools.get((r.anchor, r.terc))
        if pool is None or len(pool) == 0:
            missed += 1
            continue
        picks.append(rng.choice(pool, size=min(3, len(pool)), replace=False))
    ctrl = S.loc[np.concatenate(picks)]
    out = pd.concat([E, ctrl], ignore_index=True)
    out["aid"] = np.arange(len(out))
    out.attrs["missed"] = missed
    return out


def build_trajectories(u: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame:
    rep = anchors.loc[anchors.index.repeat(EXIT_HORIZON)].copy()
    rep["k"] = np.tile(np.arange(-EXIT_HORIZON, 0), len(anchors))
    rep["qi"] = rep.anchor + rep.k + 1
    vals = u.set_index(["cik", "qi"])[METRICS]
    mi = pd.MultiIndex.from_arrays([rep.cik, rep.qi])
    traj = pd.concat([rep.reset_index(drop=True), vals.reindex(mi).reset_index(drop=True)], axis=1)
    base = traj[traj.k == -EXIT_HORIZON].set_index("aid")[METRICS]
    for m in METRICS:
        traj["d_" + m] = traj[m].to_numpy() - base[m].reindex(traj.aid).to_numpy()
    return traj


def section_signature(traj: pd.DataFrame, anchors: pd.DataFrame) -> dict:
    print("\n" + "=" * 78)
    print("2. SIGNATURE: t-8 to t-1, exits against survivors matched on quarter and "
          "revenue tercile")
    print("=" * 78)
    E = anchors[anchors.group == "exit"]
    S = anchors[anchors.group == "survivor"]
    print(f"  exit anchors: {len(E):,} CIKs (of {anchors.attrs.get('missed', 0) + len(E):,} "
          f"exits with 8 quarters of history); unmatched: {anchors.attrs.get('missed', 0)}")
    print(f"  control anchors: {len(S):,} firm-quarters over {S.cik.nunique():,} CIKs "
          f"(3 per exit, drawn inside the same quarter and revenue tercile)")
    print(f"  anchor years {E.anchor.min() // 4} to {E.anchor.max() // 4}; "
          f"t-1 is the last quarter at which a new annual filing refreshed the row")
    print("\n  non-null share of each metric across the 8-quarter windows:")
    for m in METRICS:
        print(f"    {m:20s} {traj[m].notna().mean():.1%}")

    print("\n  LEVELS: median at t-8 and t-1, exit minus survivor "
          "(cluster bootstrap by CIK, 95%)")
    print(f"    {'metric':20s} {'exit t-8':>10s} {'surv t-8':>10s} {'gap t-8':>22s} "
          f"{'exit t-1':>10s} {'gap t-1':>22s} {'t-8 / t-1':>9s}")
    levels = []
    for m in METRICS:
        stat = np.mean if m in DISCRETE else np.median
        row = {"metric": m}
        for k in (-EXIT_HORIZON, -1):
            a = traj[(traj.group == "exit") & (traj.k == k)]
            b = traj[(traj.group == "survivor") & (traj.k == k)]
            o, lo, hi, _ = cluster_boot_diff(a, b, m, by="cik", stat=stat,
                                             draws=DRAWS, seed=SEED)
            row[f"exit_{k}"] = stat(a[m].dropna())
            row[f"surv_{k}"] = stat(b[m].dropna())
            row[f"gap_{k}"], row[f"lo_{k}"], row[f"hi_{k}"] = o, lo, hi
            row[f"ne_{k}"], row[f"ns_{k}"] = a[m].notna().sum(), b[m].notna().sum()
        row["share_at_t8"] = (row["gap_-8"] / row["gap_-1"]) if row["gap_-1"] else np.nan
        levels.append(row)
        print(f"    {m:20s} {row['exit_-8']:10.3f} {row['surv_-8']:10.3f} "
              f"{row['gap_-8']:+8.3f} [{row['lo_-8']:+.3f},{row['hi_-8']:+.3f}] "
              f"{row['exit_-1']:10.3f} "
              f"{row['gap_-1']:+8.3f} [{row['lo_-1']:+.3f},{row['hi_-1']:+.3f}] "
              f"{row['share_at_t8']:7.0%}")
    levels = pd.DataFrame(levels)

    print("\n  TRAJECTORY: change from t-8, exits minus survivors at each quarter "
          "(difference in differences)")
    rows = []
    for m in METRICS:
        stat = np.mean if m in DISCRETE else np.median
        for k in range(-EXIT_HORIZON + 1, 0):
            a = traj[(traj.group == "exit") & (traj.k == k)]
            b = traj[(traj.group == "survivor") & (traj.k == k)]
            o, lo, hi, _ = cluster_boot_diff(a, b, "d_" + m, by="cik", stat=stat,
                                             draws=DRAWS, seed=SEED)
            rows.append({"metric": m, "k": k, "did": o, "lo": lo, "hi": hi,
                         "n_e": int(a["d_" + m].notna().sum()),
                         "n_s": int(b["d_" + m].notna().sum()),
                         "exit_move": stat(a["d_" + m].dropna()),
                         "surv_move": stat(b["d_" + m].dropna())})
    did = pd.DataFrame(rows)
    did["sig"] = (did.lo > 0) | (did.hi < 0)
    print(f"    {'metric':20s} {'first quarter the DiD excludes 0':>34s} "
          f"{'exit move t-8..t-1':>19s} {'DiD at t-1':>24s}   n exit/ctrl")
    for m in METRICS:
        sub = did[did.metric == m]
        first = sub[sub.sig].k.min() if sub.sig.any() else None
        last = sub[sub.k == -1].iloc[0]
        first_s = f"t{first}" if first is not None else "never"
        print(f"    {m:20s} {first_s:>34s} {last.exit_move:+19.3f} "
              f"{last.did:+9.3f} [{last.lo:+.3f},{last.hi:+.3f}]   "
              f"{last.n_e}/{last.n_s}")
    return {"levels": levels, "did": did, "anchors": anchors}


# --------------------------------------------------------------------------
# 3. base rates
# --------------------------------------------------------------------------
STATE_ORDER = ["altman_z < 1.8", "interest_coverage < 1",
               "fcf_margin < 0 and revenue falling", "piotroski <= 2",
               "two or more of the four", "none of the four", "any firm-quarter"]


def states(b: pd.DataFrame) -> dict[str, pd.Series]:
    s = {
        "altman_z < 1.8": b.altman_z < 1.8,
        "interest_coverage < 1": b.interest_coverage < 1,
        "fcf_margin < 0 and revenue falling": (b.fcf_margin < 0) & (b.rev_growth < 0),
        "piotroski <= 2": b.piotroski <= 2,
    }
    s = {k: v.fillna(False) for k, v in s.items()}
    cnt = sum(v.astype(int) for v in s.values())
    s["two or more of the four"] = cnt >= 2
    s["none of the four"] = cnt == 0
    s["any firm-quarter"] = pd.Series(True, index=b.index)
    return s


def section_base_rates(u: pd.DataFrame, horizon: int = EXIT_HORIZON) -> dict:
    """Share of firm-quarters in a state whose CIK stops filing within ``horizon`` quarters.

    Anchors stop at ``FINAL_QI - EXIT_HORIZON - horizon`` so the outcome is
    censored by the panel edge in neither direction: a flagged firm's last row is
    at or before ``FINAL_QI - EXIT_HORIZON`` and so is a confirmed exit under the
    study's own definition, and an unflagged firm demonstrably has a panel row
    after ``qi + horizon``. Anchoring instead at ``FINAL_QI - horizon`` labels
    every firm still filing at the last usable quarter an exit, because the panel
    simply stops there, which on this vintage adds about two points to the
    unconditional rate.
    """
    b = u[u.qi <= FINAL_QI - EXIT_HORIZON - horizon].copy()
    b["exit_h"] = b.last_qi <= b.qi + horizon
    st = states(b)
    rows = []
    for name in STATE_ORDER:
        v = st[name]
        sub = b[v]
        pr, gh = sub[sub.priced], sub[~sub.priced]
        a_r, a_lo, a_hi = rate_ci(sub.exit_h, sub.cik)
        p_r, p_lo, p_hi = rate_ci(pr.exit_h, pr.cik)
        rows.append({
            "state": name, "n": len(sub), "ciks": sub.cik.nunique(),
            "exit_ciks": sub[sub.exit_h].cik.nunique(),
            "all": a_r, "all_lo": a_lo, "all_hi": a_hi,
            "n_priced": len(pr), "priced": p_r, "priced_lo": p_lo, "priced_hi": p_hi,
            "n_ghost": len(gh), "ghost": gh.exit_h.mean(),
            "ratio": a_r / p_r if p_r else np.nan,
        })
    return {"table": pd.DataFrame(rows), "base": b, "states": st, "horizon": horizon}


def print_base_rates(res: dict) -> None:
    h = res["horizon"]
    t = res["table"]
    print(f"\n  horizon {h} quarters; anchors up to "
          f"{qi_label(FINAL_QI - EXIT_HORIZON - h)}; "
          f"n = {len(res['base']):,} firm-quarters over {res['base'].cik.nunique():,} CIKs")
    print(f"    {'state':36s} {'n':>8s} {'CIKs':>6s} {'exits':>6s} "
          f"{'whole universe':>24s} {'priced subset':>24s} {'x':>5s}")
    for r in t.itertuples():
        print(f"    {r.state:36s} {r.n:8,d} {r.ciks:6,d} {r.exit_ciks:6,d} "
              f"{pct(getattr(r, 'all')):>8s} [{pct(r.all_lo)},{pct(r.all_hi)}] "
              f"{pct(r.priced):>8s} [{pct(r.priced_lo)},{pct(r.priced_hi)}] "
              f"{r.ratio:5.2f}")


# --------------------------------------------------------------------------
# 4. placebo
# --------------------------------------------------------------------------
def section_placebo(res: dict) -> pd.DataFrame:
    print("\n" + "=" * 78)
    print("4. PLACEBO: the exit label shuffled between firms within calendar year, and "
          "the state shuffled within each firm's own quarters")
    print("=" * 78)
    b, st = res["base"], res["states"]
    obs_all = b.exit_h.mean()
    rows = []
    lifts_null = {name: [] for name in STATE_ORDER[:-1]}
    for d in range(PLACEBO_DRAWS):
        sh = clustered_shuffle(b.exit_h, b.cik, within=b.year, seed=d)
        ok = sh.notna()
        shv = sh[ok].astype(float)
        overall = shv.mean()
        for name in STATE_ORDER[:-1]:
            v = st[name][ok]
            lifts_null[name].append(shv[v.to_numpy()].mean() - overall)
    within_null = {name: [] for name in STATE_ORDER[:-1]}
    for d in range(PLACEBO_DRAWS):
        for j, name in enumerate(STATE_ORDER[:-1]):
            f = b.assign(_s=st[name].astype(float))
            sh = within_firm_shuffle(f, "_s", by="cik", seed=d * 97 + j)
            m = sh.to_numpy() > 0.5
            within_null[name].append(b.exit_h[m].mean() - obs_all)
    for name in STATE_ORDER[:-1]:
        v = st[name]
        obs = b.exit_h[v].mean() - obs_all
        n1 = np.array(lifts_null[name])
        n2 = np.array(within_null[name])
        rows.append({"state": name, "obs_lift": obs,
                     "null_between_mean": n1.mean(), "null_between_sd": n1.std(ddof=1),
                     "z_between": (obs - n1.mean()) / n1.std(ddof=1),
                     "p95_between": np.percentile(np.abs(n1), 95),
                     "null_within_mean": n2.mean(), "null_within_sd": n2.std(ddof=1),
                     "z_within": (obs - n2.mean()) / n2.std(ddof=1)})
    t = pd.DataFrame(rows)
    print(f"  {PLACEBO_DRAWS} draws each. Lift = exit rate in the state minus the exit "
          f"rate over all firm-quarters ({pct(obs_all)}).")
    print(f"    {'state':36s} {'observed lift':>14s} {'between-firm null':>22s} {'z':>7s} "
          f"{'within-firm null':>22s} {'z':>7s}")
    for r in t.itertuples():
        print(f"    {r.state:36s} {pct(r.obs_lift):>14s} "
              f"{pct(r.null_between_mean):>9s} +/- {pct(r.null_between_sd):>7s} "
              f"{r.z_between:7.1f} "
              f"{pct(r.null_within_mean):>9s} +/- {pct(r.null_within_sd):>7s} "
              f"{r.z_within:7.1f}")
    return t


# --------------------------------------------------------------------------
# 5. acquired-looking against distress-looking (a proxy, and only a proxy)
# --------------------------------------------------------------------------
def section_exit_type(u: pd.DataFrame, firm: pd.DataFrame, res: dict) -> dict:
    print("\n" + "=" * 78)
    print("5. ALTMAN-Z TREND OVER THE LAST FOUR QUARTERS: a proxy, not a reason code")
    print("=" * 78)
    ex = firm[firm["exit"]]
    z = u.set_index(["cik", "qi"]).altman_z
    z1 = z.reindex(pd.MultiIndex.from_arrays([ex.index, ex.fresh_qi])).to_numpy()
    z4 = z.reindex(pd.MultiIndex.from_arrays([ex.index, ex.fresh_qi - 3])).to_numpy()
    d = pd.Series(z1 - z4, index=ex.index)
    kind = pd.Series(np.where(d > 0, "improving", np.where(d < 0, "deteriorating", "flat")),
                     index=ex.index)
    kind[d.isna()] = "unclassified"
    n_cls = int(d.notna().sum())
    print(f"  classifiable exits: {n_cls:,} of {len(ex):,} ({n_cls / len(ex):.1%}). "
          f"Altman Z is null on 46% of panel rows and has no coverage in Financials or "
          f"Real Estate, so the classified set is a different universe.")
    print("  " + ", ".join(f"{k} {v:,}" for k, v in kind.value_counts().items()))
    print(f"  median Z change over the four quarters: improving "
          f"{d[kind == 'improving'].median():+.3f}, deteriorating "
          f"{d[kind == 'deteriorating'].median():+.3f}")
    cls = ex.assign(kind=kind)
    for col, lab in (("stale_tail", "quarters from last refresh to panel drop"),):
        print(f"  {lab}: improving {cls[cls.kind == 'improving'][col].median():.0f}, "
              f"deteriorating {cls[cls.kind == 'deteriorating'][col].median():.0f}")
    lastq = u.groupby("cik").tail(1).set_index("cik")
    for k in ("improving", "deteriorating"):
        g = cls[cls.kind == k]
        r = lastq.loc[g.index]
        print(f"  {k:14s} n={len(g):5,d}  median revenue at the last row "
              f"${r.revenue.median() / 1e6:,.0f}m  median Z {z.reindex(pd.MultiIndex.from_arrays([g.index, g.fresh_qi])).median():.2f}"
              f"  median operating margin {r.operating_margin.median():.1%}"
              f"  priced {g.priced.mean():.1%}")

    b = res["base"].copy()
    b["kind"] = b.cik.map(kind).fillna("still filing")
    st = res["states"]
    rows = []
    for name in STATE_ORDER:
        v = st[name]
        sub = b[v]
        row = {"state": name, "n": len(sub)}
        for k in ("deteriorating", "improving", "unclassified"):
            row[k] = (sub.exit_h & (sub.kind == k)).mean()
        row["all"] = sub.exit_h.mean()
        row["check"] = row["deteriorating"] + row["improving"] + row["unclassified"]
        denom = row["deteriorating"] + row["improving"]
        row["share_det"] = row["deteriorating"] / denom if denom else np.nan
        rows.append(row)
    t = pd.DataFrame(rows)
    print("\n  share of firm-quarters in each state that exit within 8 quarters, "
          "split by the exiting firm's Z trend")
    print(f"    {'state':36s} {'n':>8s} {'exit (any)':>11s} {'Z falling':>11s} "
          f"{'Z rising':>11s} {'no Z':>11s} {'Z fall/cls':>11s}")
    for r in t.itertuples():
        print(f"    {r.state:36s} {r.n:8,d} {pct(getattr(r, 'all')):>11s} "
              f"{pct(r.deteriorating):>11s} {pct(r.improving):>11s} "
              f"{pct(r.unclassified):>11s} {pct(r.share_det):>11s}   "
              f"(parts sum to {pct(r.check)})")
    print("  This split is a proxy. Nothing in the panel says whether a firm was acquired, "
          "went private, deregistered or failed.")
    return {"kind": kind, "table": t, "cls": cls}


# --------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------
def chart_exits(ex_res: dict, probe: dict) -> None:
    by_year = ex_res["by_year"]
    fig, (ax1, ax2) = C.figure(
        f"{ex_res['n_exit']:,} of {ex_res['n_firm']:,} panel CIKs stopped appearing at least "
        "8 quarters before the 2026-06-30 vintage, and the drop lags the served delisting date.",
        "Left: exits by the year of the last panel row. Right: how far the last panel row "
        "falls after the served delistedAt, 130 sampled exited CIKs, median 2.92 quarters.",
        panels=2, widths=(3, 2))
    yrs = [y for y in by_year.index if y >= 2012]
    C.bars(ax1, [str(y) for y in yrs], [by_year[y] for y in yrs], fmt="{:.0f}")
    C.label(ax1, "Exits by panel-drop year", f"n = {int(by_year[yrs].sum()):,} CIKs, 2012-2024")
    C.finish(ax1, "CIKs")
    ax1.tick_params(axis="x", rotation=90)
    if probe:
        g = probe["probe"].q_drop_after_del
        edges = [0, 1, 2, 3, 4, 5]
        labels = ["before", "0 to 1", "1 to 2", "2 to 3", "3 to 4", "4 to 5", "5+"]
        counts = ([(g < 0).sum()]
                  + [((g >= edges[i]) & (g < edges[i + 1])).sum() for i in range(5)]
                  + [(g >= 5).sum()])
        C.bars(ax2, labels, [100 * c / len(g) for c in counts], fmt="{:.0f}%", color=C.AMBER)
        C.label(ax2, "Quarters the panel drop falls AFTER delistedAt",
                f"n = {len(g)} sampled exited CIKs with a served delisting date")
        C.finish(ax2, "% of sampled exits", pct=True)
        ax2.tick_params(axis="x", rotation=45)
    C.save(fig, CHARTS / "exits.png", source_text=SOURCE)


def chart_signature(sig: dict) -> None:
    did = sig["did"]
    show = [("operating_margin", "Operating margin", 100),
            ("altman_z", "Altman Z", 1),
            ("asset_growth", "Asset growth", 100),
            ("rev_growth", "Revenue growth", 100),
            ("interest_coverage", "Interest coverage", 1),
            ("fcf_margin", "FCF margin", 100)]
    fig, axes = C.grid(
        "Most of the pre-exit gap is a level, not a slope: exiting filers already sit 1.81 "
        "Altman Z and 4.0pp of operating margin below matched survivors two years out.",
        "Median change from t-8, exits (n = 1,688 CIKs) against survivors matched on quarter "
        "and revenue tercile (n = 5,064 anchors, 1,936 CIKs). t-1 is the last quarter at which "
        "a new annual filing refreshed the row. Asset growth and Altman Z separate from t-4; "
        "coverage and FCF margin never do.",
        2, 3)
    ks = list(range(-8, 0))
    for ax, (m, title, scale) in zip(axes, show):
        sub = did[did.metric == m].set_index("k")
        e = [0.0] + [sub.exit_move[k] * scale for k in ks[1:]]
        s = [0.0] + [sub.surv_move[k] * scale for k in ks[1:]]
        C.lines(ax, ks, {"exits": e, "survivors": s},
                fmt="{:+.2f}" if scale == 1 else "{:+.1f}", legend_loc="lower left")
        n_e = int(sub.n_e[-1])
        C.label(ax, title, f"change from t-8, n = {n_e:,} exits with the metric at t-1")
        C.finish(ax, "pp" if scale == 100 else "points")
    C.save(fig, CHARTS / "signature.png", source_text=SOURCE)


def chart_base_rates(res: dict) -> None:
    t = res["table"]
    short = {"altman_z < 1.8": "Altman Z\n< 1.8", "interest_coverage < 1": "Interest\ncover < 1",
             "fcf_margin < 0 and revenue falling": "FCF < 0 and\nrevenue falling",
             "piotroski <= 2": "Piotroski\n<= 2", "two or more of the four": "Two or\nmore",
             "none of the four": "None of\nthe four", "any firm-quarter": "Any\nfirm-quarter"}
    fig, (ax,) = C.figure(
        "A firm-quarter with Altman Z below 1.8 stops filing within 8 quarters 18.5% of the "
        "time on the whole SEC panel and 3.6% of the time on the priced subset.",
        "Share of firm-quarters that leave the panel within 8 quarters, anchors 2009 to "
        "2022Q2, n = 137,787 firm-quarters over 5,499 CIKs. Panel exit mixes acquisition, "
        "going private, deregistration and failure.")
    labs = [short[s] for s in t.state]
    C.grouped_bars(ax, labs, {"whole panel": (100 * t["all"]).to_numpy(),
                              "priced subset only": (100 * t["priced"]).to_numpy()},
                   fmt="{:.1f}%", legend_loc="upper right")
    C.finish(ax, "% stopping filing within 8 quarters", pct=True)
    C.save(fig, CHARTS / "base_rates.png", source_text=SOURCE)


def chart_placebo(pl: pd.DataFrame) -> None:
    short = {"altman_z < 1.8": "Altman Z\n< 1.8", "interest_coverage < 1": "Interest\ncover < 1",
             "fcf_margin < 0 and revenue falling": "FCF < 0 and\nrevenue falling",
             "piotroski <= 2": "Piotroski\n<= 2", "two or more of the four": "Two or\nmore",
             "none of the four": "None of\nthe four"}
    fig, (ax,) = C.figure(
        "Every state's exit lift is many times the spread of a firm-clustered shuffle of the "
        "exit label within calendar year.",
        "Observed lift over the 13.2% base rate against the 95th percentile of the absolute "
        "lift over 200 shuffled draws, n = 137,787 firm-quarters over 5,499 CIKs.")
    labs = [short[s] for s in pl.state]
    C.grouped_bars(ax, labs, {"observed lift": (100 * pl.obs_lift).to_numpy(),
                              "95th pct of shuffled lift": (100 * pl.p95_between).to_numpy()},
                   fmt="{:+.1f}", legend_loc="upper right")
    C.finish(ax, "percentage points")
    C.save(fig, CHARTS / "placebo.png", source_text=SOURCE)


def chart_exit_type(et: dict) -> None:
    t = et["table"]
    short = {"altman_z < 1.8": "Altman Z\n< 1.8", "interest_coverage < 1": "Interest\ncover < 1",
             "fcf_margin < 0 and revenue falling": "FCF < 0 and\nrevenue falling",
             "piotroski <= 2": "Piotroski\n<= 2", "two or more of the four": "Two or\nmore",
             "none of the four": "None of\nthe four", "any firm-quarter": "Any\nfirm-quarter"}
    fig, (ax,) = C.figure(
        "Of the 1,016 exits whose Altman Z can be read over their last four quarters, 58% "
        "left with a falling Z; in the healthiest state the split reverses.",
        "Share of firm-quarters in each state that exit within 8 quarters, split by whether "
        "the exiting firm's Altman Z fell or rose over its last four quarters. The split is a "
        "proxy: the panel carries no delisting reason.")
    labs = [short[s] for s in t.state]
    C.grouped_bars(ax, labs, {"Z falling": (100 * t.deteriorating).to_numpy(),
                              "Z rising": (100 * t.improving).to_numpy(),
                              "no Z on file": (100 * t.unclassified).to_numpy()},
                   fmt="{:.1f}", legend_loc="upper right")
    C.finish(ax, "% of firm-quarters", pct=True)
    C.save(fig, CHARTS / "exit_type.png", source_text=SOURCE)


# --------------------------------------------------------------------------
def main() -> None:
    pd.set_option("display.width", 200)
    CACHE.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    u, firm = load_frames()

    ex_res = section_exits(u, firm)
    probe = section_probe(firm)

    anchors = build_anchors(u, firm)
    traj = build_trajectories(u, anchors)
    traj.to_parquet(CACHE / "trajectories.parquet")
    sig = section_signature(traj, anchors)
    sig["levels"].to_csv(CACHE / "signature_levels.csv", index=False)
    sig["did"].to_csv(CACHE / "signature_did.csv", index=False)

    print("\n" + "=" * 78)
    print("3. BASE RATES: share of firm-quarters in a state that stop filing within h quarters")
    print("=" * 78)
    res = section_base_rates(u, EXIT_HORIZON)
    print_base_rates(res)
    res["table"].to_csv(CACHE / "base_rates_h8.csv", index=False)
    for h in (4, 12):
        alt = section_base_rates(u, h)
        print_base_rates(alt)
        alt["table"].to_csv(CACHE / f"base_rates_h{h}.csv", index=False)

    print("\n  OUT OF SAMPLE: the same h = 8 table split at the median anchor year")
    for lo, hi in ((2009, 2015), (2016, 2022)):
        half = u[u.year.between(lo, hi)]
        alt = section_base_rates(half, EXIT_HORIZON)
        print(f"  anchor years {lo}-{hi}")
        print_base_rates(alt)
        alt["table"].to_csv(CACHE / f"base_rates_h8_{lo}_{hi}.csv", index=False)

    pl = section_placebo(res)
    pl.to_csv(CACHE / "placebo.csv", index=False)

    et = section_exit_type(u, firm, res)
    et["table"].to_csv(CACHE / "exit_type.csv", index=False)

    chart_exits(ex_res, probe)
    chart_signature(sig)
    chart_base_rates(res)
    chart_placebo(pl)
    chart_exit_type(et)
    print(f"\ncharts written to {CHARTS}")


if __name__ == "__main__":
    main()
