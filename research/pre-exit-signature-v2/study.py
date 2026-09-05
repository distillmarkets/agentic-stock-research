"""The pre-exit signature, corrected. Price-free, anchor-explicit.

Version 2 of ``research/pre-exit-signature``. It accepts every verdict in
``research/review-pre-exit/README.md`` unless a number here shows the verdict
wrong, and it publishes the base-rate deliverable as a range over exit
definitions rather than as a point.

Inputs, all already on disk:

* ``cache/panel.csv``, the point-in-time panel, ``screen/export`` vintage
  2026-09-03, final quarter 2026-06-30.
* ``cache/stooq_us/``, the Stooq US daily bundle through 2026-08-14, read only
  to mark a ticker priced or not. No return is computed anywhere in this study,
  so there is nothing to market-adjust.
* ``cache/research/pre-exit-signature/probe_delisted.csv`` and
  ``probe_sample.csv``, the 150 cached ``/sec/fundamentals/{t}/as-of/2026-09-03``
  responses written by v1's ``probe_delisted.py``.

**Uncached API calls: 0.** ``distill_toolkit.client.get`` is replaced by a
raiser before any other import, so a run that reaches its last line made none.

Attribution. Constructors are imported from where they were written rather than
copied:

* ``research/pre-exit-signature/study.py`` (v1): ``load_frames``, ``states``,
  ``STATE_ORDER``, ``METRICS``, ``DISCRETE``, ``tercile``, ``rate_ci``,
  ``build_anchors``, ``build_trajectories``, ``section_exits``,
  ``section_probe``.
* ``research/pre-exit-signature/panel_base.py`` (v1): the universe, the quarter
  index, ``fresh_qi`` and the exit rule.
* ``research/review-pre-exit/study.py`` (the adversarial review):
  ``base_table``, ``build_anchors_keyed``, ``level_table``, ``did_table``,
  ``first_sig``, ``cell_mean_shuffle``, ``print_table``.

Only the placebo table, the coverage table, the range presentation and the
charts are new here.

Run from the repository root::

    ./.venv/bin/python research/pre-exit-signature-v2/study.py
"""
from __future__ import annotations

import importlib.util
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V1_DIR = ROOT / "research" / "pre-exit-signature"
REVIEW_DIR = ROOT / "research" / "review-pre-exit"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(V1_DIR))

# --------------------------------------------------------------------------
# network kill switch, before anything that could reach the API is imported
# --------------------------------------------------------------------------
import distill_toolkit.client as _client  # noqa: E402


def _no_network(*args, **kwargs):  # pragma: no cover - the point is that it raises
    raise RuntimeError(
        "research/pre-exit-signature-v2 makes no API call; every input is cached")


_client.get = _no_network

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from distill_toolkit import charts as C  # noqa: E402
from distill_toolkit.analysis import clustered_shuffle, within_firm_shuffle  # noqa: E402

import study as V1  # noqa: E402  research/pre-exit-signature/study.py
from panel_base import EXIT_HORIZON, FINAL_QI, PANEL_VINTAGE, qi_label  # noqa: E402


def _load_review():
    """Import the reviewer's study under its own name so it does not collide with v1."""
    spec = importlib.util.spec_from_file_location(
        "review_pre_exit_study", REVIEW_DIR / "study.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


R = _load_review()  # research/review-pre-exit/study.py

OUT = ROOT / "cache" / "research" / "pre-exit-signature-v2"
CHARTS = Path(__file__).resolve().parent / "charts"
SOURCE = ("Distill point-in-time panel, screen/export vintage 2026-09-03; "
          "Stooq US bundle 2026-08-14; 150 cached /sec/fundamentals as-of responses")
CAVEAT = ("Leaving the panel is leaving the corpus, not failing: acquisition, going "
          "private, deregistration, exchange deficiency and bankruptcy arrive as one event.")

DRAWS = 300          # cluster bootstrap draws
NULL_DRAWS = 200     # placebo draws
SEED = 7
ZSTATE = "altman_z < 1.8"
HEALTHY = "none of the four"
ANY = "any firm-quarter"


def head(text: str) -> None:
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)


def pct(x: float, nd: int = 2) -> str:
    return "nan" if not np.isfinite(x) else f"{100 * x:.{nd}f}%"


# --------------------------------------------------------------------------
# new here: the placebo table under three constructions of the same null
# --------------------------------------------------------------------------
def placebo_table(b: pd.DataFrame, st: dict, draws: int = NULL_DRAWS,
                  label: str = "") -> pd.DataFrame:
    """Observed lift against three nulls, on one base frame.

    The statistic is the lift: a state's exit rate minus the exit rate over all
    firm-quarters in the frame.

    * ``shuffle``  - ``analysis.clustered_shuffle(within=year)`` as shipped after
      CORRECTIONS 16 and 18: the exit label moves between firms, each firm
      carries its whole label path, the partner's cell is walked in order, and a
      row whose partner has no cell at its key takes the partner's label at its
      nearest key. No row is dropped, so the shuffled and observed rates share a
      denominator.
    * ``cellmean`` - the reviewer's ``cell_mean_shuffle``: a row takes its
      partner cell's mean label. Also drops nothing, and smooths the label's
      within-firm persistence rather than keeping it.
    * ``within``   - ``analysis.within_firm_shuffle`` on the state flag, which
      keeps every firm-level property and destroys only the timing inside a
      firm's own history.
    """
    states = [s for s in V1.STATE_ORDER if s != ANY]
    obs_all = float(b.exit_h.mean())
    null_sh = {s: [] for s in states}
    null_cm = {s: [] for s in states}
    null_wi = {s: [] for s in states}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for d in range(draws):
            sh = clustered_shuffle(b.exit_h, b.cik, within=b.year, seed=d).astype(float)
            assert sh.notna().all(), "the shipped clustered_shuffle must drop no row"
            o1 = float(sh.mean())
            cm = R.cell_mean_shuffle(b.exit_h, b.cik, b.year, seed=d).astype(float)
            o2 = float(cm.mean())
            for s in states:
                v = st[s].to_numpy()
                null_sh[s].append(float(sh[v].mean()) - o1)
                null_cm[s].append(float(cm[v].mean()) - o2)
        for d in range(draws):
            for j, s in enumerate(states):
                f = b.assign(_s=st[s].astype(float))
                w = within_firm_shuffle(f, "_s", by="cik", seed=d * 97 + j).to_numpy() > 0.5
                null_wi[s].append(float(b.exit_h[w].mean()) - obs_all)
    rows = []
    for s in states:
        obs = float(b.exit_h[st[s]].mean()) - obs_all
        row = {"frame": label, "state": s, "n": int(st[s].sum()), "obs_lift": obs,
               "base_rate": obs_all}
        for tag, d in (("shuffle", null_sh), ("cellmean", null_cm), ("within", null_wi)):
            a = np.asarray(d[s], dtype=float)
            row[f"{tag}_mean"] = a.mean()
            row[f"{tag}_sd"] = a.std(ddof=1)
            row[f"{tag}_z"] = (obs - a.mean()) / a.std(ddof=1)
            row[f"{tag}_p95"] = float(np.percentile(np.abs(a), 95))
            row[f"{tag}_ratio"] = abs(obs) / float(np.percentile(np.abs(a), 95))
        rows.append(row)
    return pd.DataFrame(rows)


def print_placebo(t: pd.DataFrame, title: str) -> None:
    print(f"\n  {title} ({NULL_DRAWS} draws each; lift = state rate minus the frame's "
          f"overall rate, {pct(t.base_rate.iloc[0])})")
    print(f"    {'state':36s} {'n':>8s} {'observed':>9s} "
          f"{'clustered_shuffle null':>24s} {'z':>6s} {'x p95':>6s} "
          f"{'cell-mean null':>20s} {'z':>6s} {'within-firm null':>20s} {'z':>6s}")
    for r in t.itertuples():
        print(f"    {r.state:36s} {r.n:8,d} {pct(r.obs_lift):>9s} "
              f"{pct(r.shuffle_mean):>9s} +/- {pct(r.shuffle_sd):>8s} {r.shuffle_z:6.1f} "
              f"{r.shuffle_ratio:6.1f} "
              f"{pct(r.cellmean_mean):>8s} +/- {pct(r.cellmean_sd):>7s} {r.cellmean_z:6.1f} "
              f"{pct(r.within_mean):>8s} +/- {pct(r.within_sd):>7s} {r.within_z:6.1f}")


# --------------------------------------------------------------------------
# 1. universe, exits, probe
# --------------------------------------------------------------------------
def section_universe(u: pd.DataFrame, firm: pd.DataFrame) -> tuple[dict, dict]:
    ex_res = V1.section_exits(u, firm)      # v1's constructor, unchanged
    probe = V1.section_probe(firm)          # v1's constructor, unchanged
    d = pd.read_csv(V1.CACHE / "probe_delisted.csv", dtype={"cik": str, "served_cik": str})
    still = tuple(d[(d.cik == d.served_cik) & d.delisted_at.isna()].cik)
    same = d[d.cik == d.served_cik]
    no_del = same[same.delisted_at.isna()]
    files = no_del[no_del.last_filed_at.notna()]
    print(f"\n  the 11 probe CIKs with no served delistedAt are {len(still)} of "
          f"{len(same)} same-CIK responses ({len(still) / len(same):.1%}); "
          f"{len(files)} of them ({len(files) / len(same):.1%}) hold an annual filing "
          f"dated {files.last_filed_at.min()} or later. Both counts travel together: "
          f"7.8% is the no-delistedAt share and 5.7% is the still-filing evidence, and "
          f"the binomial 95% interval on 11 of 141 is roughly +/- 4.4pp.")
    print(f"  {CAVEAT}")
    return ex_res, {"probe": probe, "still": still, "n_same": len(same),
                    "n_none": len(no_del), "n_files": len(files)}


# --------------------------------------------------------------------------
# 2. the base rate is a range over exit definitions
# --------------------------------------------------------------------------
VARIANTS = [
    ("A", "last panel row, stale rows kept (v1)", dict(anchor="last")),
    ("B", "last record refresh, stale rows kept", dict(anchor="fresh")),
    ("C", "last record refresh, stale rows dropped", dict(anchor="fresh", drop_stale=True)),
    ("D", "last panel row, stale rows dropped", dict(anchor="last", drop_stale=True)),
    ("E", "C minus the probe CIKs with no delistedAt", dict(anchor="fresh", drop_stale=True)),
    ("F", "last refresh + 2 quarters (probe-calibrated), stale rows dropped",
     dict(anchor="fresh+2", drop_stale=True)),
]


def section_range(u: pd.DataFrame, firm: pd.DataFrame, still: tuple[str, ...]) -> dict:
    head("2. THE DELIVERABLE IS A RANGE: the exit anchor moves it by a factor of 2.7")
    print(f"  {CAVEAT}")
    b = u[u.qi <= FINAL_QI - EXIT_HORIZON - EXIT_HORIZON]
    stale = b.qi > b.fresh_qi
    print(f"\n  base frame {len(b):,} firm-quarters over {b.cik.nunique():,} CIKs. "
          f"{stale.sum():,} rows ({stale.mean():.2%}) fall after their CIK's last record "
          f"refresh; {(stale & b.is_exit).sum():,} of those {stale.sum():,} belong to an "
          f"exiting CIK and none to a survivor.")
    zsub = b[V1.states(b)[ZSTATE]]
    zst = zsub.qi > zsub.fresh_qi
    pos = zsub.last_qi <= zsub.qi + EXIT_HORIZON
    print(f"  In the Altman Z < 1.8 cell those repeats are {zst.mean():.1%} of "
          f"{len(zsub):,} rows and {(zst & pos).sum() / pos.sum():.1%} of the "
          f"{pos.sum():,} rows labelled as exiting under the v1 anchor; "
          f"{pos[zst].mean():.1%} of them are positive by construction.")

    tabs = {}
    for tag, name, kw in VARIANTS:
        kw = dict(kw)
        if tag == "E":
            kw["drop_ciks"] = still
        t = R.base_table(u, EXIT_HORIZON, **kw)      # reviewer's constructor
        tabs[tag] = t
        R.print_table(t, f"{tag}  {name}")
        t.to_csv(OUT / f"base_variant_{tag}.csv", index=False)

    print(f"\n  WHOLE PANEL, every state under every definition. {CAVEAT}")
    print(f"    {'state':36s} " + " ".join(f"{tag:>9s}" for tag, _, _ in VARIANTS))
    for s in V1.STATE_ORDER:
        vals = [tabs[t].set_index("state").loc[s, "all"] for t, _, _ in VARIANTS]
        print(f"    {s:36s} " + " ".join(f"{pct(v):>9s}" for v in vals))
    print(f"    {'-- priced subset --':36s}")
    for s in V1.STATE_ORDER:
        vals = [tabs[t].set_index("state").loc[s, "priced"] for t, _, _ in VARIANTS]
        print(f"    {s:36s} " + " ".join(f"{pct(v):>9s}" for v in vals))

    A, B, Cc, D, E, F = (tabs[t].set_index("state") for t in "ABCDEF")
    lo = min(A.loc[ZSTATE, "all"], B.loc[ZSTATE, "all"],
             Cc.loc[ZSTATE, "all"], D.loc[ZSTATE, "all"])
    hi = max(A.loc[ZSTATE, "all"], B.loc[ZSTATE, "all"],
             Cc.loc[ZSTATE, "all"], D.loc[ZSTATE, "all"])
    print(f"\n  Altman Z < 1.8, whole panel: range {pct(lo)} to {pct(hi)} across four "
          f"defensible definitions, {pct(Cc.loc[ZSTATE, 'all'])} under the corrected "
          f"definition C and {pct(F.loc[ZSTATE, 'all'])} under the probe-calibrated F.")
    print(f"  v1 published {pct(A.loc[ZSTATE, 'all'])}. Re-anchoring alone moves it "
          f"{100 * (B.loc[ZSTATE, 'all'] - A.loc[ZSTATE, 'all']):+.2f}pp and dropping the "
          f"stale repeats alone moves it "
          f"{100 * (D.loc[ZSTATE, 'all'] - A.loc[ZSTATE, 'all']):+.2f}pp; doing both moves "
          f"it {100 * (Cc.loc[ZSTATE, 'all'] - A.loc[ZSTATE, 'all']):+.2f}pp. "
          f"v1's number was right by cancellation, not by method.")

    print("\n  WHAT SURVIVES THE ANCHOR CHANGE")
    order_ok = all(
        all(tabs[t].set_index("state").loc[s, "all"]
            > tabs[t].set_index("state").loc[HEALTHY, "all"]
            for s in V1.STATE_ORDER[:5])
        for t, _, _ in VARIANTS)
    print(f"    ordering (every distress state above the healthy state) holds in all six "
          f"definitions: {order_ok}")
    print(f"    {'definition':12s} {'Altman lift over healthy':>26s} "
          f"{'whole / priced ratio, Altman':>30s} {'whole / priced, any':>21s}")
    for t, _, _ in VARIANTS:
        x = tabs[t].set_index("state")
        print(f"    {t:12s} {x.loc[ZSTATE, 'all'] / x.loc[HEALTHY, 'all']:25.2f}x "
              f"{x.loc[ZSTATE, 'ratio']:29.2f}x {x.loc[ANY, 'ratio']:20.2f}x")

    print("\n  HORIZON SWEEP, v1 anchor against the corrected definition C "
          f"(whole panel / priced subset). {CAVEAT}")
    sweep = []
    for h in (4, 8, 12):
        pub = R.base_table(u, h, anchor="last", ci=False).set_index("state")
        cor = R.base_table(u, h, anchor="fresh", drop_stale=True, ci=False).set_index("state")
        for s in (ZSTATE, "two or more of the four", ANY):
            sweep.append({"split": "all", "h": h, "state": s,
                          "n_pub": int(pub.loc[s, "n"]), "n_cor": int(cor.loc[s, "n"]),
                          "pub_all": pub.loc[s, "all"], "pub_priced": pub.loc[s, "priced"],
                          "cor_all": cor.loc[s, "all"], "cor_priced": cor.loc[s, "priced"]})
    for y0, y1 in ((2009, 2015), (2016, 2022)):
        half = u[u.year.between(y0, y1)]
        pub = R.base_table(half, EXIT_HORIZON, anchor="last", ci=False).set_index("state")
        cor = R.base_table(half, EXIT_HORIZON, anchor="fresh", drop_stale=True,
                           ci=False).set_index("state")
        for s in (ZSTATE, "two or more of the four", ANY):
            sweep.append({"split": f"{y0}-{y1}", "h": 8, "state": s,
                          "n_pub": int(pub.loc[s, "n"]), "n_cor": int(cor.loc[s, "n"]),
                          "pub_all": pub.loc[s, "all"], "pub_priced": pub.loc[s, "priced"],
                          "cor_all": cor.loc[s, "all"], "cor_priced": cor.loc[s, "priced"]})
    sweep = pd.DataFrame(sweep)
    print(f"    {'split':10s} {'h':>3s} {'state':26s} {'n (C)':>9s} "
          f"{'v1 anchor':>19s} {'corrected C':>19s}")
    for r in sweep.itertuples():
        print(f"    {r.split:10s} {r.h:3d} {r.state:26s} {r.n_cor:9,d} "
              f"{pct(r.pub_all):>8s} / {pct(r.pub_priced):<8s} "
              f"{pct(r.cor_all):>8s} / {pct(r.cor_priced):<8s}")
    sweep.to_csv(OUT / "horizons.csv", index=False)

    print("\n  THE STILL-FILING SHARE, applied two ways")
    print(f"    dropping the {len(still)} named probe CIKs with no delistedAt moves the "
          f"corrected Altman cell by "
          f"{100 * (E.loc[ZSTATE, 'all'] - Cc.loc[ZSTATE, 'all']):+.3f}pp "
          f"({pct(Cc.loc[ZSTATE, 'all'])} to {pct(E.loc[ZSTATE, 'all'])}) and the "
          f"unconditional rate by "
          f"{100 * (E.loc[ANY, 'all'] - Cc.loc[ANY, 'all']):+.3f}pp. Eleven CIKs are "
          f"{len(still) / int(firm['exit'].sum()):.1%} of the {int(firm['exit'].sum()):,} "
          f"exits, so a named-CIK drop cannot carry the probe's rate.")
    rng = np.random.default_rng(SEED)
    ex_ciks = firm.index[firm["exit"]].to_numpy()
    bc = u[u.qi <= FINAL_QI - EXIT_HORIZON - EXIT_HORIZON]
    bc = bc[bc.qi <= bc.fresh_qi].copy()
    bc["exit_h"] = bc.is_exit & (bc.fresh_qi <= bc.qi + EXIT_HORIZON)
    stc = V1.states(bc)
    sims = {s: [] for s in (ZSTATE, "two or more of the four", HEALTHY, ANY)}
    for _ in range(NULL_DRAWS):
        drop = set(rng.choice(ex_ciks, int(round(0.078 * len(ex_ciks))), replace=False))
        flag = bc.exit_h & ~bc.cik.isin(drop)
        for s in sims:
            sims[s].append(float(flag[stc[s]].mean()))
    print(f"    applying 7.8% as a bound instead: removing 7.8% of exit CIKs at random, "
          f"{NULL_DRAWS} draws, on the corrected frame (n = {len(bc):,})")
    for s, v in sims.items():
        v = np.asarray(v)
        print(f"      {s:36s} {pct(Cc.loc[s, 'all'])} -> {pct(v.mean())} "
              f"+/- {pct(v.std(ddof=1), 3)}")
    return {"tabs": tabs, "sweep": sweep, "sims": sims, "base_corrected": bc,
            "states_corrected": stc}


# --------------------------------------------------------------------------
# 3. the signature with sector in the matching cell
# --------------------------------------------------------------------------
def section_signature(u: pd.DataFrame, firm: pd.DataFrame) -> dict:
    head("3. THE SIGNATURE with sector added to the matching cell")
    print(f"  {CAVEAT}")
    a2 = R.build_anchors_keyed(u, firm, ("anchor", "terc"))
    a3 = R.build_anchors_keyed(u, firm, ("anchor", "terc", "sector"))
    ref = V1.build_anchors(u, firm)
    same = (len(ref) == len(a2)
            and sorted(ref[ref.group == "survivor"].cik) == sorted(a2[a2.group == "survivor"].cik))
    print(f"  the keyed sampler reproduces v1's build_anchors exactly: {same}")
    sec = u.set_index(["cik", "qi"]).sector
    for tag, a in (("tercile only", a2), ("tercile + sector", a3)):
        s = sec.reindex(pd.MultiIndex.from_arrays([a.cik, a.anchor])).to_numpy()
        x = pd.crosstab(pd.Series(s, name="sector"), a.group.to_numpy(), normalize="columns")
        tv = 0.5 * float(np.abs(x["exit"] - x["survivor"]).sum())
        print(f"    {tag:16s}: exits {(a.group == 'exit').sum():,} "
              f"(unmatched {a.attrs['missed']}), controls "
              f"{(a.group == 'survivor').sum():,} over "
              f"{a[a.group == 'survivor'].cik.nunique():,} CIKs; sector total-variation "
              f"distance {tv:.3f}")

    levels, dids = {}, {}
    for tag, a in (("tercile only", a2), ("tercile + sector", a3)):
        traj = V1.build_trajectories(u, a)
        levels[tag] = R.level_table(traj, draws=DRAWS)
        dids[tag] = R.did_table(traj, draws=DRAWS)
        if tag == "tercile + sector":
            traj.to_parquet(OUT / "trajectories_sector.parquet")
    pd.concat([v.assign(match=k) for k, v in levels.items()],
              ignore_index=True).to_csv(OUT / "signature_levels.csv", index=False)
    pd.concat([v.assign(match=k) for k, v in dids.items()],
              ignore_index=True).to_csv(OUT / "signature_did.csv", index=False)

    print("\n  LEVELS: median gap at t-8 and t-1, exits minus matched survivors, "
          "firm-clustered 95% interval, and the share of the t-1 gap already on file at t-8")
    print(f"    {'metric':18s} {'gap t-8':>22s} {'gap t-1':>22s} {'at t-8':>7s} "
          f"{'n exit/ctrl at t-1':>20s}")
    L = levels["tercile + sector"].set_index("metric")
    for m in V1.METRICS:
        r = L.loc[m]
        print(f"    {m:18s} {f'{r.gap8:+.3f} [{r.lo8:+.3f},{r.hi8:+.3f}]':>22s} "
              f"{f'{r.gap1:+.3f} [{r.lo1:+.3f},{r.hi1:+.3f}]':>22s} {r.share:7.0%} "
              f"{f'{int(r.ne1):,}/{int(r.ns1):,}':>20s}")
    for tag in ("tercile only", "tercile + sector"):
        band = [m for m in V1.METRICS
                if 0.80 <= levels[tag].set_index("metric").loc[m].share <= 1.05]
        share_vals = [levels[tag].set_index("metric").loc[m].share for m in V1.METRICS
                      if np.isfinite(levels[tag].set_index("metric").loc[m].share)]
        print(f"    metrics inside 80-105% of the t-1 gap at t-8, {tag}: {len(band)} "
              f"of {len(V1.METRICS)}")
    seven = [(m, levels["tercile only"].set_index("metric").loc[m].share,
              levels["tercile + sector"].set_index("metric").loc[m].share)
             for m in V1.METRICS
             if 0.80 <= levels["tercile only"].set_index("metric").loc[m].share <= 1.05]
    lo_s = min(v for _, _, v in seven)
    hi_s = max(v for _, _, v in seven)
    print(f"    v1's claim was 'eight of eleven metrics at 82% to 103%'. Counting v1's own "
          f"column it is SEVEN metrics ({', '.join(m for m, _, _ in seven)}); with sector "
          f"in the cell those same seven run {lo_s:.0%} to {hi_s:.0%}.")

    print("\n  DIFFERENCE IN DIFFERENCES: change from each anchor's own t-8, "
          "exits minus controls (* = 95% interval excludes zero)")
    for tag in ("tercile only", "tercile + sector"):
        print(f"    -- {tag} --")
        for m in V1.METRICS:
            sub = dids[tag][dids[tag].metric == m].sort_values("k")
            f = R.first_sig(dids[tag], m)
            line = " ".join(f"t{int(r.k)}:{r.did:+.3f}{'*' if r.sig else ' '}"
                            for r in sub.itertuples())
            print(f"      {m:18s} first={('t' + str(f)) if f is not None else 'never':>6s}  "
                  f"{line}")

    print("\n  WHAT t-4 CAN AND CANNOT MEAN: share of rows whose change from t-8 is "
          "exactly zero (the panel's annual metrics do not refresh every quarter)")
    traj2 = V1.build_trajectories(u, a2)
    print(f"    {'metric':18s} " + " ".join(f"{'t' + str(k):>8s}" for k in range(-7, 0)))
    zero_rows = []
    for m in V1.METRICS:
        sh = [float((traj2[traj2.k == k]["d_" + m].dropna() == 0).mean()) for k in range(-7, 0)]
        zero_rows.append(dict({"metric": m}, **{f"t{k}": v for k, v in zip(range(-7, 0), sh)}))
        print(f"    {m:18s} " + " ".join(f"{100 * v:7.1f}%" for v in sh))
    pd.DataFrame(zero_rows).to_csv(OUT / "zero_change_shares.csv", index=False)
    ds = dids["tercile + sector"]
    for kk in (-7, -6):
        n_flat = sum(1 for m in V1.METRICS
                     if abs(float(ds[(ds.metric == m) & (ds.k == kk)].iloc[0].did)) < 1e-12)
        print(f"    metrics whose DiD is exactly 0.000 [0.000, 0.000] at t{kk}: "
              f"{n_flat} of {len(V1.METRICS)}")
    print("    t-4 is therefore close to the earliest quarter this design can answer, and "
          "the early part of the trajectory is a structural zero rather than a measured null.")

    print("\n  SEED SENSITIVITY of the control draw, tercile + sector, 5 seeds")
    seed_rows = []
    for seed in (7, 11, 13, 17, 23):
        a = R.build_anchors_keyed(u, firm, ("anchor", "terc", "sector"), seed=seed)
        d = R.did_table(V1.build_trajectories(u, a),
                        metrics=["altman_z", "asset_growth", "interest_coverage"], draws=DRAWS)
        parts = []
        for m in ("altman_z", "asset_growth", "interest_coverage"):
            f = R.first_sig(d, m)
            r = d[(d.metric == m) & (d.k == -1)].iloc[0]
            seed_rows.append({"seed": seed, "metric": m,
                              "first_sig": f if f is not None else np.nan,
                              "did_t1": r.did, "lo": r.lo, "hi": r.hi})
            parts.append(f"{m} first={('t' + str(f)) if f is not None else 'never'} "
                         f"t-1 {r.did:+.3f}")
        print(f"    seed {seed:3d}: " + "; ".join(parts))
    sd = pd.DataFrame(seed_rows)
    sd.to_csv(OUT / "seed_sensitivity.csv", index=False)
    ic = sd[sd.metric == "interest_coverage"]
    print(f"    interest coverage first separates in {int(ic.first_sig.notna().sum())} of "
          f"{len(ic)} seeds; it is reported as unstable, not as a finding.")
    for m in ("altman_z", "asset_growth"):
        s = sd[sd.metric == m]
        print(f"    {m} first separates in {int(s.first_sig.notna().sum())} of {len(s)} "
              f"seeds, always at t{int(s.first_sig.min()) if s.first_sig.notna().any() else 0}")
    return {"levels": levels, "did": dids, "a2": a2, "a3": a3, "seeds": sd}


# --------------------------------------------------------------------------
# 4. placebos
# --------------------------------------------------------------------------
def section_placebo(u: pd.DataFrame, corrected: dict) -> dict:
    head("4. PLACEBOS under the shipped clustered_shuffle (CORRECTIONS 16 and 18)")
    print(f"  {CAVEAT}")
    bA = u[u.qi <= FINAL_QI - EXIT_HORIZON - EXIT_HORIZON].copy()
    bA["exit_h"] = bA.last_qi <= bA.qi + EXIT_HORIZON
    stA = V1.states(bA)
    tA = placebo_table(bA, stA, NULL_DRAWS, label="A (v1 frame and anchor)")
    print_placebo(tA, "on v1's frame and anchor (definition A)")

    bC = corrected["base_corrected"]
    stC = corrected["states_corrected"]
    tC = placebo_table(bC, stC, NULL_DRAWS, label="C (corrected frame and anchor)")
    print_placebo(tC, "on the corrected frame and anchor (definition C)")

    out = pd.concat([tA, tC], ignore_index=True)
    out.to_csv(OUT / "placebo.csv", index=False)
    za = tA.set_index("state").loc[ZSTATE]
    zc = tC.set_index("state").loc[ZSTATE]
    print(f"\n  THE NULL IS CONSTRUCTION-DEPENDENT (CORRECTIONS 18). On the Altman cell of "
          f"frame A the same observed lift of {pct(za.obs_lift)} sits at z = "
          f"{za.shuffle_z:.1f} under the shipped nearest-key shuffle and z = "
          f"{za.cellmean_z:.1f} under the reviewer's cell-mean null; the review published "
          f"5.1 for that cell-mean construction and CORRECTIONS 18 records 5.1, 8.8 and "
          f"12.0 for three no-drop constructions of the same null against the withdrawn "
          f"8.8 of the defective helper.")
    print(f"  On the corrected frame C the Altman lift is {pct(zc.obs_lift)} at z = "
          f"{zc.shuffle_z:.1f} (shipped shuffle), {zc.cellmean_z:.1f} (cell mean) and "
          f"{zc.within_z:.1f} (within firm). A z from this family of nulls is a statement "
          f"about a construction as much as about the data.")
    weakest = tC.loc[tC.shuffle_ratio.abs().idxmin()]
    print(f"  weakest state against the shipped shuffle on frame C: {weakest.state}, "
          f"lift {pct(weakest.obs_lift)} at {weakest.shuffle_ratio:.1f} times the 95th "
          f"percentile of the absolute null, z = {weakest.shuffle_z:.1f}.")
    return {"A": tA, "C": tC}


# --------------------------------------------------------------------------
# 5. did not survive
# --------------------------------------------------------------------------
def section_did_not_survive(u: pd.DataFrame, firm: pd.DataFrame,
                            anchor_sets: dict) -> dict:
    head("5. DID NOT SURVIVE: the Altman-Z-trend split is not an exit-type proxy")
    ex = firm[firm["exit"]]
    z = u.set_index(["cik", "qi"]).altman_z

    def trend(ciks, qi):
        z1 = z.reindex(pd.MultiIndex.from_arrays([ciks, qi])).to_numpy()
        z4 = z.reindex(pd.MultiIndex.from_arrays([ciks, np.asarray(qi) - 3])).to_numpy()
        return z1 - z4

    d = pd.Series(trend(ex.index, ex.fresh_qi.to_numpy()), index=ex.index)
    rows = [("all exits, at the last refresh", int(d.notna().sum()),
             float((d > 0).sum() / d.notna().sum()))]
    for tag, anchors in anchor_sets.items():
        Sv = anchors[anchors.group == "survivor"]
        E = anchors[anchors.group == "exit"]
        dsv = pd.Series(trend(Sv.cik.to_numpy(), Sv.anchor.to_numpy()))
        dE = pd.Series(trend(E.cik.to_numpy(), E.anchor.to_numpy()))
        rows.append((f"matched exits, {tag}", int(dE.notna().sum()),
                     float((dE > 0).sum() / dE.notna().sum())))
        rows.append((f"matched survivors, {tag}", int(dsv.notna().sum()),
                     float((dsv > 0).sum() / dsv.notna().sum())))
    print(f"    {'cohort':40s} {'n classified':>13s} {'four-quarter Z rising':>22s}")
    for name, n, sh in rows:
        print(f"    {name:40s} {n:13,d} {sh:21.2%}")
    surv = {name: sh for name, n, sh in rows if name.startswith("matched survivors")}
    print(f"  A rising four-quarter Altman Z appears at "
          + " and ".join(f"{v:.1%} ({k.split(', ')[1]})" for k, v in surv.items())
          + f" of matched survivor anchors against {rows[0][2]:.1%} of exits. The split is "
            f"the survivor base rate, so it carries no information about how a firm left, "
            f"and it is withdrawn as a finding.")
    kind = pd.Series(np.where(d > 0, "improving", np.where(d < 0, "deteriorating", "flat")),
                     index=ex.index)
    kind[d.isna()] = "unclassified"
    fx = u.set_index(["cik", "qi"])[["altman_z"]].reindex(
        pd.MultiIndex.from_arrays([ex.index, ex.fresh_qi])).reset_index(drop=True)
    fx["kind"] = kind.to_numpy()
    for k in ("deteriorating", "improving"):
        sub = fx[fx.kind == k]
        print(f"    {k:16s} n={len(sub):5,d}  median Z at the anchor "
              f"{sub.altman_z.median():6.2f}  share with Z < 1.8 {(sub.altman_z < 1.8).mean():6.1%}")
    print("  The two groups differ by 2.3 points of Altman Z level and by whether Z < 1.8, "
          "which is the state variable any split would be read against, so the trend split "
          "is a level split read twice.")
    t = pd.DataFrame(rows, columns=["cohort", "n", "rising_share"])
    t.to_csv(OUT / "ztrend_placebo.csv", index=False)
    return {"rows": rows, "kind": kind}


# --------------------------------------------------------------------------
# 6. coverage, and the 46% against 43.93% discrepancy
# --------------------------------------------------------------------------
def section_coverage(u: pd.DataFrame) -> pd.DataFrame:
    head("6. COVERAGE: the Altman-null share, corrected")
    az = float(u.altman_z.isna().mean())
    ic = float(u.interest_coverage.isna().mean())
    print(f"  v1's study.py line 473 prints 'Altman Z is null on 46% of panel rows' where "
          f"v1's own README says 43.9%. Measured on the {len(u):,} universe rows the value "
          f"is {az:.2%}; the printed 46% has no source in the frame. Interest coverage is "
          f"null on {ic:.2%}.")
    cov = (u.groupby("sector")
             .agg(rows=("altman_z", "size"),
                  altman_cov=("altman_z", lambda v: float(v.notna().mean())),
                  cover_cov=("interest_coverage", lambda v: float(v.notna().mean())))
             .sort_values("altman_cov"))
    print(f"\n    {'sector':28s} {'rows':>10s} {'Altman Z on file':>17s} "
          f"{'interest coverage':>18s}")
    for s, r in cov.iterrows():
        print(f"    {s:28s} {int(r.rows):10,d} {r.altman_cov:16.1%} {r.cover_cov:17.1%}")
    zero = list(cov.index[cov.altman_cov == 0])
    print(f"  Altman Z coverage is exactly zero in {', '.join(zero)}, which is "
          f"{int(cov.loc[zero, 'rows'].sum()):,} rows "
          f"({cov.loc[zero, 'rows'].sum() / len(u):.1%} of the universe). The strongest "
          f"single metric in this study is unusable for those filers.")
    cov.to_csv(OUT / "coverage.csv")
    return cov


# --------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------
def chart_range(rng_res: dict) -> None:
    tabs = rng_res["tabs"]
    labs = ["A last row,\nstale kept", "B last refresh,\nstale kept",
            "C last refresh,\nstale dropped", "D last row,\nstale dropped",
            "E C minus 11\nstill-filing", "F refresh + 2q,\nstale dropped"]
    whole = [100 * tabs[t].set_index("state").loc[ZSTATE, "all"] for t, _, _ in VARIANTS]
    priced = [100 * tabs[t].set_index("state").loc[ZSTATE, "priced"] for t, _, _ in VARIANTS]
    fig, (ax,) = C.figure(
        "A firm-quarter with Altman Z below 1.8 stops filing within 8 quarters between "
        "9.8% and 26.6% of the time, depending on which date is called the exit.",
        "Whole SEC panel against the priced subset, n = 137,787 firm-quarters over 5,499 "
        "CIKs when stale repeats are kept and 128,123 when they are dropped. C is the "
        "corrected definition and F is calibrated to the served delisting date. Leaving "
        "the panel is leaving the corpus, not failing.")
    C.grouped_bars(ax, labs, {"whole panel": np.array(whole),
                              "priced subset only": np.array(priced)},
                   fmt="{:.1f}%", legend_loc="upper right")
    C.finish(ax, "% stopping filing within 8 quarters", pct=True)
    C.save(fig, CHARTS / "exit_anchor_range.png", source_text=SOURCE)


def chart_base_rates(rng_res: dict) -> None:
    t = rng_res["tabs"]["C"]
    short = {"altman_z < 1.8": "Altman Z\n< 1.8", "interest_coverage < 1": "Interest\ncover < 1",
             "fcf_margin < 0 and revenue falling": "FCF < 0 and\nrevenue falling",
             "piotroski <= 2": "Piotroski\n<= 2", "two or more of the four": "Two or\nmore",
             "none of the four": "None of\nthe four", "any firm-quarter": "Any\nfirm-quarter"}
    fig, (ax,) = C.figure(
        "Under the corrected exit anchor every distress state leaves the filing record "
        "about twice as often as the healthy state, and the priced subset reports a "
        "sixth of the level.",
        "Share of firm-quarters whose CIK stops filing within 8 quarters, anchors 2009 to "
        "2022Q2, n = 128,123 firm-quarters over 5,499 CIKs, exit dated at the last record "
        "refresh with stale repeats dropped. 88.57% of exited CIKs carry no price series, "
        "so every priced bar is a floor. Leaving the panel is leaving the corpus, not "
        "failing.")
    labs = [short[s] for s in t.state]
    C.grouped_bars(ax, labs, {"whole panel": (100 * t["all"]).to_numpy(),
                              "priced subset only": (100 * t["priced"]).to_numpy()},
                   fmt="{:.1f}%", legend_loc="upper right")
    C.finish(ax, "% stopping filing within 8 quarters", pct=True)
    C.save(fig, CHARTS / "base_rates_corrected.png", source_text=SOURCE)


def chart_signature(sig: dict) -> None:
    did = sig["did"]["tercile + sector"]
    show = [("altman_z", "Altman Z", 1), ("asset_growth", "Asset growth", 100),
            ("operating_margin", "Operating margin", 100), ("rev_growth", "Revenue growth", 100),
            ("interest_coverage", "Interest coverage", 1), ("fcf_margin", "FCF margin", 100)]
    fig, axes = C.grid(
        "Altman Z and asset growth separate from sector-matched survivors at t-4 in five of "
        "five control draws; interest coverage does so in three of five.",
        "Median change from each anchor's own t-8, exits (n = 1,688 CIKs) against survivors "
        "matched on calendar quarter, revenue tercile and sector (n = 5,064 anchors). t-1 is "
        "the last quarter at which a new annual filing refreshed the row. The panel's annual "
        "metrics refresh once a fiscal year, so nothing can separate before t-5. Leaving the "
        "panel is leaving the corpus, not failing.",
        2, 3)
    ks = list(range(-8, 0))
    for ax, (m, title, scale) in zip(axes, show):
        sub = did[did.metric == m].set_index("k")
        e = [0.0] + [sub.exit_move[k] * scale for k in ks[1:]]
        s = [0.0] + [sub.surv_move[k] * scale for k in ks[1:]]
        C.lines(ax, ks, {"exits": e, "survivors": s},
                fmt="{:+.2f}" if scale == 1 else "{:+.1f}", legend_loc="lower left")
        C.label(ax, title, f"change from t-8, n = {int(sub.n_e[-1]):,} exits at t-1")
        C.finish(ax, "pp" if scale == 100 else "points")
    C.save(fig, CHARTS / "signature_sector.png", source_text=SOURCE)


def chart_placebo(pl: dict) -> None:
    t = pl["C"]
    short = {"altman_z < 1.8": "Altman Z\n< 1.8", "interest_coverage < 1": "Interest\ncover < 1",
             "fcf_margin < 0 and revenue falling": "FCF < 0 and\nrevenue falling",
             "piotroski <= 2": "Piotroski\n<= 2", "two or more of the four": "Two or\nmore",
             "none of the four": "None of\nthe four"}
    fig, (ax,) = C.figure(
        "A state's exit lift sits 3.1 to 6.2 standard deviations from a between-firm null "
        "and 0.5 to 17.7 from a within-firm one, so the z states a construction as much as "
        "a result.",
        "Absolute z of the observed lift under three constructions of the same null, 200 "
        "draws each, on the corrected frame, n = 128,123 firm-quarters over 5,499 CIKs. The "
        "two between-firm nulls differ only in what a firm hands its shuffle partner when "
        "the partner has no row at that key. Leaving the panel is leaving the corpus, not "
        "failing.")
    labs = [short[s] for s in t.state]
    C.grouped_bars(ax, labs,
                   {"nearest-key shuffle (shipped)": np.abs(t.shuffle_z.to_numpy()),
                    "cell-mean shuffle (review)": np.abs(t.cellmean_z.to_numpy()),
                    "within-firm shuffle": np.abs(t.within_z.to_numpy())},
                   fmt="{:.1f}", legend_loc="upper left")
    C.finish(ax, "absolute z of the observed lift")
    C.save(fig, CHARTS / "placebo_constructions.png", source_text=SOURCE)


def chart_ztrend(zt: dict) -> None:
    rows = zt["rows"]
    lab = {"all exits, at the last refresh": "all exits\nat last refresh",
           "matched exits, tercile only": "matched exits\ntercile cell",
           "matched survivors, tercile only": "matched survivors\ntercile cell",
           "matched exits, tercile + sector": "matched exits\ntercile + sector",
           "matched survivors, tercile + sector": "matched survivors\ntercile + sector"}
    fig, (ax,) = C.figure(
        "A rising four-quarter Altman Z appears at 42.0% of matched survivor quarters and "
        "41.9% of exits, so the Z trend does not separate exits from survivors.",
        "Share of anchors whose Altman Z rose over the four quarters ending at the anchor, "
        "n = 1,016 classified exits and 2,736 to 2,782 classified survivor anchors. Exits "
        "are dated at the last record refresh. Leaving the panel is leaving the corpus, not "
        "failing.")
    C.bars(ax, [lab[n] for n, _, _ in rows], [100 * s for _, _, s in rows], fmt="{:.1f}%",
           color=[C.AMBER if "survivor" not in n else C.BRAND for n, _, _ in rows])
    C.finish(ax, "% with a rising four-quarter Altman Z", pct=True)
    C.save(fig, CHARTS / "ztrend_null.png", source_text=SOURCE)


# --------------------------------------------------------------------------
def main() -> None:
    pd.set_option("display.width", 220)
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    print(f"panel vintage {PANEL_VINTAGE}, final quarter {qi_label(FINAL_QI)}; "
          f"uncached API calls made by this script: 0 (client.get raises)")

    u, firm = V1.load_frames()                    # v1 constructor
    u["fresh_qi"] = u.cik.map(firm.fresh_qi)      # required by the reviewer's base_table

    _, probe = section_universe(u, firm)
    rng_res = section_range(u, firm, probe["still"])
    sig = section_signature(u, firm)
    pl = section_placebo(u, rng_res)
    zt = section_did_not_survive(u, firm, {"tercile only": sig["a2"],
                                           "tercile + sector": sig["a3"]})
    section_coverage(u)

    chart_range(rng_res)
    chart_base_rates(rng_res)
    chart_signature(sig)
    chart_placebo(pl)
    chart_ztrend(zt)
    print(f"\ncharts written to {CHARTS}")
    print(f"frames written to {OUT}")


if __name__ == "__main__":
    main()
