"""How long after its last point-in-time row a firm's listing ends, and what
its final row on file looks like against a Form 15 firm and against survivors.

Runs with no key on the published 200-firm sample. If a full export carrying
``listed_until`` is at ``cache/panel.csv`` it runs on that instead and says so.
Every number in README.md comes out of this script; the tables it prints are
also written under ``cache/research/listing-end/``.

Run from the repository root:

    DISTILL_OFFLINE=1 ./.venv/bin/python research/listing-end/study.py

Uncached API calls: 0. The client's request functions are replaced by a raiser
before anything else is imported, so a run that reaches its last line made none.
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DISTILL_OFFLINE", "1")

import distill_toolkit.client as _client  # noqa: E402


def _no_call(*_a, **_k):
    raise RuntimeError("listing-end makes no API call; every input is on disk")


_client.get = _client.post = _client.request = _client.download = _no_call

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from distill_toolkit import analysis, charts, client, stooq  # noqa: E402

HERE = Path(__file__).parent
OUT = client.CACHE_DIR / "research" / "listing-end"
CHARTS = HERE / "charts"
SEED = 20260909
DRAWS = 1000
PLACEBO = 200
SOURCES = ("form25", "form15")
METRICS = ["revenue", "operating_margin", "net_margin", "asset_growth", "fcf_margin",
           "altman_z", "piotroski", "net_dilution"]
PCT = {"operating_margin", "net_margin", "asset_growth", "fcf_margin", "net_dilution"}
QS = [0.1, 0.25, 0.5, 0.75, 0.9]


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def snapshot() -> list[list]:
    return [[str(p), s, m] for p, s, m in client.manifest()]


def load_panel() -> tuple[pd.DataFrame, str]:
    """The panel with the listing columns: the full export if it carries them,
    else the published sample."""
    path = client.panel_path()
    df = pd.read_csv(path, low_memory=False)
    if "listed_until" not in df.columns:
        alt = client.CACHE_DIR / "pit-sample.csv.gz"
        if path.name != alt.name and alt.exists():
            print(f"note: {path.name} carries no listed_until column (an export older than "
                  f"2026-09-07); running on {alt.name}")
            path, df = alt, pd.read_csv(alt, low_memory=False)
        else:
            raise KeyError("the panel on disk has no listed_until column; fetch an export "
                           "from 2026-09-07 or later, or the published sample")
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    df["listed_until"] = pd.to_datetime(df["listed_until"])
    df["is_listed_equity"] = df["is_listed_equity"].astype(str).str.lower().eq("true")
    return df.sort_values(["cik", "as_of_date"]).reset_index(drop=True), path.name


def frames(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(one row per firm at its last snapshot, listed rows with terciles, final snapshot)."""
    final = df["as_of_date"].max()
    listed = df[df["is_listed_equity"] & (df["revenue"] > 0)].copy()
    listed["tercile"] = listed.groupby("as_of_date")["revenue"].transform(
        lambda r: pd.qcut(r.rank(method="first"), 3, labels=[1, 2, 3]).astype(int)
        if len(r) >= 3 else pd.Series(2, index=r.index))
    g = df.groupby("cik")
    last = g.tail(1).set_index("cik")
    last["rows"] = g.size()
    fy_last = g["fiscal_year"].last()
    refresh = (df[df["fiscal_year"].eq(df["cik"].map(fy_last))]
               .groupby("cik")["as_of_date"].min())
    last["refresh"] = refresh
    last["survivor"] = last["as_of_date"].eq(final)
    last["dated"] = last["listed_until"].notna()
    last["gap_last"] = (last["listed_until"] - last["as_of_date"]).dt.days
    last["gap_refresh"] = (last["listed_until"] - last["refresh"]).dt.days
    last["stale_q"] = ((last["as_of_date"] - last["refresh"]).dt.days / 91.31).round().astype(int)
    terc = listed.set_index(["cik", "as_of_date"])["tercile"]
    last["tercile"] = [terc.get((c, d), np.nan) for c, d in zip(last.index, last["as_of_date"])]
    return last, listed, final


def series_facts(last: pd.DataFrame) -> pd.DataFrame:
    """For every leaver, whether the Stooq bundle holds a series under its ticker,
    and where that series starts and ends."""
    have = stooq.index()
    rows = []
    for cik, r in last[~last["survivor"]].iterrows():
        key = stooq.stooq_key(r["ticker"])
        first = end = None
        if key in have:
            bars = stooq.bars(r["ticker"]) or []
            if bars:
                first = pd.Timestamp(bars[0][0])
                end = pd.Timestamp(bars[-1][0])
        rows.append({"cik": cik, "ticker": r["ticker"], "source": r["listing_end_source"],
                     "listed_until": r["listed_until"], "series": first is not None,
                     "first_bar": first, "last_bar": end})
    out = pd.DataFrame(rows).set_index("cik")
    out["begins_after_end"] = out["series"] & out["listed_until"].notna() & (out["first_bar"] > out["listed_until"])
    out["spans_end"] = out["series"] & out["listed_until"].notna() & ~out["begins_after_end"]
    return out


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------
def t1_universe(df, last, series, panel_name) -> dict:
    leav = last[~last["survivor"]]
    have = stooq.index()
    surv_priced = last[last["survivor"]]["ticker"].map(lambda t: stooq.stooq_key(t) in have)
    dated = series[series["listed_until"].notna()]
    undated = series[series["listed_until"].isna()]
    edge = series["last_bar"].max()
    return {
        "panel": panel_name, "firms": int(df["cik"].nunique()), "rows": int(len(df)),
        "first_snapshot": str(df["as_of_date"].min().date()),
        "final_snapshot": str(df["as_of_date"].max().date()),
        "survivors": int(last["survivor"].sum()), "leavers": int(len(leav)),
        "dated": int(leav["dated"].sum()),
        "by_source": {k: int(v) for k, v in leav["listing_end_source"].value_counts(dropna=False).items()
                      if isinstance(k, str)},
        "undated": int((~leav["dated"]).sum()),
        "survivors_with_series_pct": round(100 * surv_priced.mean(), 1),
        "dated_with_series": int(dated["series"].sum()),
        "dated_series_begins_after_end": int(dated["begins_after_end"].sum()),
        "dated_series_spans_end": int(dated["spans_end"].sum()),
        "undated_with_series_to_edge": int((undated["series"] & undated["last_bar"].eq(edge)).sum()),
        "bundle_edge": str(edge.date()),
    }


def quantiles(s: pd.Series) -> dict:
    s = s.dropna()
    q = s.quantile(QS)
    return {"n": int(len(s)), "p10": q[0.1], "p25": q[0.25], "median": q[0.5],
            "p75": q[0.75], "p90": q[0.9], "mean": s.mean()}


def t2_gaps(last) -> tuple[pd.DataFrame, dict]:
    rows = []
    for src in SOURCES:
        f = last[last["listing_end_source"].eq(src) & last["dated"]]
        for col in ("gap_last", "gap_refresh", "stale_q"):
            rows.append({"source": src, "anchor": col, **quantiles(f[col])})
    tab = pd.DataFrame(rows)
    a = last[last["listing_end_source"].eq("form25") & last["dated"]].reset_index()
    b = last[last["listing_end_source"].eq("form15") & last["dated"]].reset_index()
    diffs = {}
    for col in ("gap_last", "gap_refresh"):
        obs, lo, hi, share = analysis.cluster_boot_diff(a, b, col, by="cik", stat=np.median,
                                                        draws=DRAWS, seed=SEED)
        diffs[col] = {"form25_minus_form15": obs, "lo": lo, "hi": hi, "share_le_0": share}
    return tab, diffs


def t3_form25_cuts(last) -> pd.DataFrame:
    f = last[last["listing_end_source"].eq("form25") & last["dated"]].copy()
    f["exit_year"] = f["listed_until"].dt.year
    f["half"] = np.where(f["exit_year"] <= 2018, "2011-2018", "2019-2026")
    rows = []
    for sector, s in f.groupby("sector"):
        if len(s) >= 5:
            rows.append({"cut": sector, **quantiles(s["gap_last"])})
    for half, s in f.groupby("half"):
        rows.append({"cut": half, **quantiles(s["gap_last"])})
    return pd.DataFrame(rows)[["cut", "n", "p25", "median", "p75"]]


def matched_survivors(last, listed, seed: int = SEED) -> pd.DataFrame:
    """Three survivor rows per dated leaver, same snapshot and revenue tercile."""
    rng = np.random.default_rng(seed)
    surv_ciks = set(last[last["survivor"]].index)
    pool = listed[listed["cik"].isin(surv_ciks)]
    picks = []
    for cik, r in last[last["dated"] & last["listing_end_source"].isin(SOURCES)].iterrows():
        cell = pool[(pool["as_of_date"] == r["as_of_date"]) & (pool["tercile"] == r["tercile"])]
        if cell.empty:
            continue
        k = min(3, len(cell))
        chosen = cell.iloc[rng.choice(len(cell), k, replace=False)].copy()
        chosen["matched_to"] = cik
        picks.append(chosen)
    return pd.concat(picks, ignore_index=True)


def cohort_medians(frame: pd.DataFrame) -> dict:
    return {m: {"median": float(frame[m].median()), "n": int(frame[m].notna().sum())} for m in METRICS}


def t4_final_row(last, listed) -> tuple[dict, dict, pd.DataFrame]:
    f25 = last[last["listing_end_source"].eq("form25") & last["dated"]].reset_index()
    f15 = last[last["listing_end_source"].eq("form15") & last["dated"]].reset_index()
    und = last[~last["survivor"] & ~last["dated"]].reset_index()
    ctl = matched_survivors(last, listed)
    meds = {"form25": cohort_medians(f25), "form15": cohort_medians(f15),
            "undated": cohort_medians(und), "survivors": cohort_medians(ctl),
            "survivor_rows": int(len(ctl)), "survivor_firms": int(ctl["cik"].nunique())}
    diffs = {}
    for name, a, b in (("form25_minus_survivors", f25, ctl), ("form15_minus_survivors", f15, ctl),
                       ("form25_minus_form15", f25, f15)):
        diffs[name] = {}
        for m in METRICS:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                obs, lo, hi, share = analysis.cluster_boot_diff(a, b, m, by="cik", stat=np.nanmedian,
                                                                draws=DRAWS, seed=SEED)
            diffs[name][m] = {"diff": obs, "lo": lo, "hi": hi, "share_le_0": share}
    return meds, diffs, ctl


def _median_gap(frame, labels, col, pos, neg) -> float:
    return float(np.nanmedian(frame.loc[labels.eq(pos), col])) - float(np.nanmedian(frame.loc[labels.eq(neg), col]))


def t5_placebo(last, ctl) -> pd.DataFrame:
    """Between-firm label shuffle. Every firm's label moves as one; the null is
    "this label, on the wrong firm"."""
    rows = []
    # (a) source label across the Form 25 and Form 15 firms
    ab = last[last["dated"] & last["listing_end_source"].isin(SOURCES)].reset_index()
    labels = ab["listing_end_source"]
    for col in ["gap_last", "gap_refresh"] + METRICS:
        obs = _median_gap(ab, labels, col, "form25", "form15")
        draws = []
        for k in range(PLACEBO):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                sh = analysis.clustered_shuffle(labels, ab["cik"], seed=SEED + k)
                draws.append(_median_gap(ab, sh, col, "form25", "form15"))
        d = np.asarray(draws)
        rows.append({"comparison": "form25_minus_form15", "metric": col, "observed": obs,
                     "placebo_mean": d.mean(), "placebo_sd": d.std(ddof=1),
                     "z": (obs - d.mean()) / d.std(ddof=1) if d.std(ddof=1) > 0 else np.nan,
                     "share_as_extreme": float(np.mean(np.abs(d) >= abs(obs)))})
    # (b) leaver label across Form 25 firms and their matched survivors
    f25 = last[last["listing_end_source"].eq("form25") & last["dated"]].reset_index()
    both = pd.concat([f25.assign(label="leaver"), ctl.assign(label="survivor")], ignore_index=True)
    labels = both["label"]
    for col in METRICS:
        obs = _median_gap(both, labels, col, "leaver", "survivor")
        draws = []
        for k in range(PLACEBO):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                sh = analysis.clustered_shuffle(labels, both["cik"], seed=SEED + k)
                draws.append(_median_gap(both, sh, col, "leaver", "survivor"))
        d = np.asarray(draws)
        rows.append({"comparison": "form25_minus_survivors", "metric": col, "observed": obs,
                     "placebo_mean": d.mean(), "placebo_sd": d.std(ddof=1),
                     "z": (obs - d.mean()) / d.std(ddof=1) if d.std(ddof=1) > 0 else np.nan,
                     "share_as_extreme": float(np.mean(np.abs(d) >= abs(obs)))})
    return pd.DataFrame(rows)


def t6_undated(last, series, final) -> pd.DataFrame:
    und = last[~last["survivor"] & ~last["dated"]].copy()
    und["series_to_edge"] = series.loc[und.index, "last_bar"].eq(series["last_bar"].max())
    und["quarters_to_final"] = ((final - und["as_of_date"]).dt.days / 91.31).round().astype(int)
    return und[["ticker", "sector", "as_of_date", "rows", "revenue", "series_to_edge",
                "quarters_to_final"]].sort_values("as_of_date")


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
def chart_gaps(last, source_text: str) -> None:
    fig, (ax,) = charts.figure(
        "The listing ends a median of one to two months after the last point-in-time row",
        "Days from each anchor to the Form 25 or Form 15 date. Bar is the middle half, line the 10th to 90th, dot the median.")
    labels, q = [], []
    for col, name in (("gap_last", "last row"), ("gap_refresh", "last refresh")):
        for src, sn in (("form25", "Form 25"), ("form15", "Form 15")):
            s = last[last["listing_end_source"].eq(src) & last["dated"]][col].dropna()
            labels.append(f"{sn}, {name} (n={len(s)})")
            q.append(s.quantile(QS).values)
    qdf = pd.DataFrame(q, index=labels, columns=QS)
    charts.quantile_bars(ax, labels, qdf, fmt="{:.0f} d", label_median=True)
    charts.finish(ax, "days", zero_line=False)
    charts.save(fig, CHARTS / "listing-end-gap.png", source_text)


def chart_final_row(meds, diffs, source_text: str) -> None:
    fig, axes = charts.figure(
        "On its final row a Form 25 firm sits below matched survivors on margin; the interval on a Form 15 firm spans zero",
        "Median on the last snapshot. Survivors are drawn on the same snapshot in the same revenue tercile. Whiskers: firm bootstrap 95% interval on the difference from survivors.",
        panels=2, widths=[2, 1])
    keys = [("operating_margin", "operating margin"), ("net_margin", "net margin"), ("asset_growth", "asset growth")]
    labels = [k[1] for k in keys]
    series = {c: [100 * meds[c][k]["median"] for k, _ in keys] for c in ("form25", "form15", "survivors")}
    err = {}
    for c, key in (("form25", "form25_minus_survivors"), ("form15", "form15_minus_survivors")):
        err[c] = [(100 * (meds["survivors"][k]["median"] + diffs[key][k]["lo"]),
                   100 * (meds["survivors"][k]["median"] + diffs[key][k]["hi"])) for k, _ in keys]
    charts.grouped_bars(axes[0], labels, {"Form 25": series["form25"], "Form 15": series["form15"],
                                          "survivors": series["survivors"]}, fmt="{:.0f}%",
                        err={"Form 25": err["form25"], "Form 15": err["form15"]}, legend_loc="upper left")
    lo, hi = axes[0].get_ylim()
    axes[0].set_ylim(lo, hi + 0.45 * (hi - lo))
    charts.finish(axes[0], pct=True)
    az = {c: [meds[c]["altman_z"]["median"]] for c in ("form25", "form15", "survivors")}
    err_z = {c: [(meds["survivors"]["altman_z"]["median"] + diffs[key]["altman_z"]["lo"],
                  meds["survivors"]["altman_z"]["median"] + diffs[key]["altman_z"]["hi"])]
             for c, key in (("form25", "form25_minus_survivors"), ("form15", "form15_minus_survivors"))}
    charts.grouped_bars(axes[1], ["Altman Z"], {"Form 25": az["form25"], "Form 15": az["form15"],
                                                "survivors": az["survivors"]}, fmt="{:.1f}",
                        err={"Form 25": err_z["form25"], "Form 15": err_z["form15"]}, legend_loc="lower right")
    lo, hi = axes[1].get_ylim()
    axes[1].set_ylim(lo - 0.35 * (hi - lo), hi)
    charts.finish(axes[1])
    charts.save(fig, CHARTS / "final-row.png", source_text)


# ---------------------------------------------------------------------------
def fmt_tab(df: pd.DataFrame) -> str:
    return df.to_string(index=False, float_format=lambda v: f"{v:,.2f}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    (OUT / "manifest-start.json").write_text(json.dumps(snapshot()))

    df, panel_name = load_panel()
    last, listed, final = frames(df)
    series = series_facts(last)

    t1 = t1_universe(df, last, series, panel_name)
    print("T1 universe and coverage"); print(json.dumps(t1, indent=1))
    (OUT / "t1_universe.json").write_text(json.dumps(t1, indent=1))
    series.to_csv(OUT / "t1_leaver_series.csv")
    reused = series[series["begins_after_end"] | series["spans_end"]]
    print("\nDated leavers with a series in the bundle:")
    print(reused[["ticker", "source", "listed_until", "first_bar", "last_bar", "begins_after_end"]].to_string())

    t2, t2d = t2_gaps(last)
    print("\nT2 gap to the listing end, by source"); print(fmt_tab(t2)); print(json.dumps(t2d, indent=1))
    t2.to_csv(OUT / "t2_gaps.csv", index=False); (OUT / "t2_diffs.json").write_text(json.dumps(t2d, indent=1))

    t3 = t3_form25_cuts(last)
    print("\nT3 Form 25 gap from the last row, by sector and exit-year half"); print(fmt_tab(t3))
    t3.to_csv(OUT / "t3_form25_cuts.csv", index=False)

    meds, diffs, ctl = t4_final_row(last, listed)
    print("\nT4 the final row on file, medians by cohort")
    print(json.dumps(meds, indent=1)); print(json.dumps(diffs, indent=1))
    (OUT / "t4_medians.json").write_text(json.dumps(meds, indent=1))
    (OUT / "t4_diffs.json").write_text(json.dumps(diffs, indent=1))

    t5 = t5_placebo(last, ctl)
    print("\nT5 placebo, between-firm label shuffle"); print(fmt_tab(t5))
    t5.to_csv(OUT / "t5_placebo.csv", index=False)

    t6 = t6_undated(last, series, final)
    print("\nT6 undated leavers"); print(t6.to_string())
    t6.to_csv(OUT / "t6_undated.csv")

    src = (f"Distill Markets point-in-time export, {panel_name}, snapshots {t1['first_snapshot']} to "
           f"{t1['final_snapshot']}; Stooq US daily bundle through {t1['bundle_edge']}.")
    chart_gaps(last, src)
    chart_final_row(meds, diffs, src)

    (OUT / "manifest-end.json").write_text(json.dumps(snapshot()))
    start = json.loads((OUT / "manifest-start.json").read_text())
    end = json.loads((OUT / "manifest-end.json").read_text())
    changed = [e for e in end if e not in start and not e[0].startswith(str(OUT))]
    print(f"\ncache entries that changed during the run, outside this study's folder: {len(changed)}")


if __name__ == "__main__":
    main()
