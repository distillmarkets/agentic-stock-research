"""Adversarial review of ``research/listing-end``.

Every number in ``research/review-listing-end/README.md`` comes out of this
script, from files on disk, with zero API calls. The reviewed study's
constructors (``load_panel``, ``frames``, ``series_facts``, ``matched_survivors``,
``cohort_medians``, ``t2_gaps``, ``_median_gap``) are imported from
``research/listing-end/study.py`` by path, not copied, so a reproduction failure
here is a real one. Nothing under ``research/listing-end/`` is written.

Run from the repository root:

    DISTILL_OFFLINE=1 ./.venv/bin/python research/review-listing-end/study.py

Tables land under ``cache/research/review-listing-end/`` and the full log at
``cache/research/review-listing-end/output.txt`` when stdout is redirected there.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DISTILL_OFFLINE", "1")
sys.dont_write_bytecode = True  # importing the reviewed study must not write a __pycache__ into its folder

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Importing the reviewed study replaces the client's request functions with a
# raiser before anything else, so this review inherits its zero-call guarantee.
_spec = importlib.util.spec_from_file_location("listing_end_study", ROOT / "research" / "listing-end" / "study.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

from distill_toolkit import analysis, charts, client, stooq  # noqa: E402

HERE = Path(__file__).parent
OUT = client.CACHE_DIR / "research" / "review-listing-end"
STUDY_OUT = client.CACHE_DIR / "research" / "listing-end"
CHARTS = HERE / "charts"
README = ROOT / "research" / "listing-end" / "README.md"
SEED = S.SEED
DRAWS = S.DRAWS
PLACEBO = S.PLACEBO
METRICS = S.METRICS
MARGINS = ["operating_margin", "net_margin"]
OTHER_SEEDS = [1, 2, 3, 4, 5]


def fmt(df: pd.DataFrame) -> str:
    return df.to_string(index=False, float_format=lambda v: f"{v:,.3f}")


def boot(a: pd.DataFrame, b: pd.DataFrame, col: str) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        obs, lo, hi, share = analysis.cluster_boot_diff(a, b, col, by="cik", stat=np.nanmedian,
                                                        draws=DRAWS, seed=SEED)
    return {"diff": obs, "lo": lo, "hi": hi, "n_a": int(a[col].notna().sum()), "n_b": int(b[col].notna().sum())}


def gap_table(name: str, a: pd.DataFrame, b: pd.DataFrame, metrics=METRICS) -> pd.DataFrame:
    rows = []
    for m in metrics:
        r = boot(a, b, m)
        rows.append({"construction": name, "metric": m, **r,
                     "excludes_zero": bool(np.isfinite(r["lo"]) and (r["lo"] > 0 or r["hi"] < 0))})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# R0. reproduction: the README's numbers against the study's own outputs
# ---------------------------------------------------------------------------
def r0_reproduction() -> pd.DataFrame:
    """The README's quoted values against what the study's script wrote to disk."""
    t1 = json.loads((STUDY_OUT / "t1_universe.json").read_text())
    t2 = pd.read_csv(STUDY_OUT / "t2_gaps.csv")
    t2d = json.loads((STUDY_OUT / "t2_diffs.json").read_text())
    t4m = json.loads((STUDY_OUT / "t4_medians.json").read_text())
    t4d = json.loads((STUDY_OUT / "t4_diffs.json").read_text())
    t5 = pd.read_csv(STUDY_OUT / "t5_placebo.csv")
    t6 = pd.read_csv(STUDY_OUT / "t6_undated.csv")

    def t2v(src, anchor, col):
        return float(t2[(t2["source"] == src) & (t2["anchor"] == anchor)][col].iloc[0])

    def t5v(comp, metric, col):
        return float(t5[(t5["comparison"] == comp) & (t5["metric"] == metric)][col].iloc[0])

    checks = [
        ("firms", 200, t1["firms"]), ("rows", 6155, t1["rows"]),
        ("survivors", 98, t1["survivors"]), ("leavers", 102, t1["leavers"]),
        ("form25", 70, t1["by_source"]["form25"]), ("form15", 15, t1["by_source"]["form15"]),
        ("migration", 1, t1["by_source"]["migration"]), ("crawl", 1, t1["by_source"]["crawl"]),
        ("undated", 15, t1["undated"]),
        ("survivors with series %", 94.9, t1["survivors_with_series_pct"]),
        ("dated with series", 8, t1["dated_with_series"]),
        ("dated series begins after end", 5, t1["dated_series_begins_after_end"]),
        ("undated series to edge", 7, t1["undated_with_series_to_edge"]),
        ("F25 median gap last row", 53, t2v("form25", "gap_last", "median")),
        ("F15 median gap last row", 45, t2v("form15", "gap_last", "median")),
        ("F25 median gap refresh", 202, t2v("form25", "gap_refresh", "median")),
        ("F15 median gap refresh", 184, t2v("form15", "gap_refresh", "median")),
        ("F25 stale quarters median", 2, t2v("form25", "stale_q", "median")),
        ("F15 stale quarters median", 1, t2v("form15", "stale_q", "median")),
        ("diff medians last row", 8, t2d["gap_last"]["form25_minus_form15"]),
        ("diff last row lo", -29, t2d["gap_last"]["lo"]), ("diff last row hi", 29, t2d["gap_last"]["hi"]),
        ("diff medians refresh", 18, t2d["gap_refresh"]["form25_minus_form15"]),
        ("diff refresh lo", -65, t2d["gap_refresh"]["lo"]), ("diff refresh hi", 97, round(t2d["gap_refresh"]["hi"])),
        ("placebo z gap last row", 0.49, round(t5v("form25_minus_form15", "gap_last", "z"), 2)),
        ("placebo share gap last row", 0.72, round(t5v("form25_minus_form15", "gap_last", "share_as_extreme"), 2)),
        ("survivor rows", 255, t4m["survivor_rows"]), ("survivor firms", 80, t4m["survivor_firms"]),
        ("F25 op margin median %", -1.6, round(100 * t4m["form25"]["operating_margin"]["median"], 1)),
        ("survivor op margin median %", 7.5, round(100 * t4m["survivors"]["operating_margin"]["median"], 1)),
        ("F25 minus surv op margin pp", -9.0, round(100 * t4d["form25_minus_survivors"]["operating_margin"]["diff"], 1)),
        ("F25 minus surv op margin lo", -13.3, round(100 * t4d["form25_minus_survivors"]["operating_margin"]["lo"], 1)),
        ("F25 minus surv op margin hi", -4.5, round(100 * t4d["form25_minus_survivors"]["operating_margin"]["hi"], 1)),
        ("F25 minus surv net margin pp", -9.6, round(100 * t4d["form25_minus_survivors"]["net_margin"]["diff"], 1)),
        ("F25 minus surv net margin lo", -14.4, round(100 * t4d["form25_minus_survivors"]["net_margin"]["lo"], 1)),
        ("F25 minus surv net margin hi", -2.5, round(100 * t4d["form25_minus_survivors"]["net_margin"]["hi"], 1)),
        ("placebo z F25 minus surv op margin", -3.13, round(t5v("form25_minus_survivors", "operating_margin", "z"), 2)),
        ("placebo z F25 minus surv net margin", -4.70, round(t5v("form25_minus_survivors", "net_margin", "z"), 2)),
        ("placebo share F25 minus surv op margin", 0.0, t5v("form25_minus_survivors", "operating_margin", "share_as_extreme")),
        ("F15 minus surv op margin pp", -9.6, round(100 * t4d["form15_minus_survivors"]["operating_margin"]["diff"], 1)),
        ("F15 minus surv op margin hi", 0.3, round(100 * t4d["form15_minus_survivors"]["operating_margin"]["hi"], 1)),
        ("F15 minus surv altman lo", -9.24, round(t4d["form15_minus_survivors"]["altman_z"]["lo"], 2)),
        ("F15 minus surv altman hi", -0.91, round(t4d["form15_minus_survivors"]["altman_z"]["hi"], 2)),
        ("F25 minus F15 altman z placebo", 1.98, round(t5v("form25_minus_form15", "altman_z", "z"), 2)),
        ("undated rows in table 6", 15, len(t6)),
        ("undated median revenue $m", 20, round(t6["revenue"].median() / 1e6)),
    ]
    rows = [{"quantity": q, "readme": r, "script": s, "match": bool(np.isclose(float(r), float(s), atol=0.051))}
            for q, r, s in checks]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# R1. the null rebuilt: year-stratum shuffles, and sector-matched survivors
# ---------------------------------------------------------------------------
def stratum_shuffle(labels: pd.Series, units: pd.Series, strata: pd.Series, seed: int) -> pd.Series:
    """Permute a label among units within each stratum. A unit's rows move as one."""
    rng = np.random.default_rng(seed)
    out = labels.copy()
    frame = pd.DataFrame({"l": labels, "u": units, "s": strata})
    for _, sub in frame.groupby("s", sort=False):
        one = sub.drop_duplicates("u")
        perm = one["l"].to_numpy()[rng.permutation(len(one))]
        out.loc[sub.index] = sub["u"].map(dict(zip(one["u"], perm))).to_numpy()
    return out


def placebo_rows(frame, labels, units, strata, cols, pos, neg, comparison, draws=PLACEBO) -> list[dict]:
    rows = []
    for col in cols:
        obs = S._median_gap(frame, labels, col, pos, neg)
        d = []
        for k in range(draws):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                sh = stratum_shuffle(labels, units, strata, seed=SEED + k)
                d.append(S._median_gap(frame, sh, col, pos, neg))
        d = np.asarray(d)
        sd = d.std(ddof=1)
        rows.append({"comparison": comparison, "metric": col, "observed": obs, "placebo_mean": d.mean(),
                     "placebo_sd": sd, "z": (obs - d.mean()) / sd if sd > 0 else np.nan,
                     "share_as_extreme": float(np.mean(np.abs(d) >= abs(obs)))})
    return rows


def r1_year_stratum_placebo(last, ctl) -> pd.DataFrame:
    # (a) the source label, permuted among Form 25 and Form 15 firms within exit-year strata
    ab = last[last["dated"] & last["listing_end_source"].isin(S.SOURCES)].reset_index()
    rows = placebo_rows(ab, ab["listing_end_source"], ab["cik"], ab["listed_until"].dt.year,
                        ["gap_last", "gap_refresh"] + METRICS, "form25", "form15", "form25_minus_form15, exit-year strata")
    # (b) the leaver label, permuted among leaver and matched-survivor firms within snapshot-date strata
    f25 = last[last["listing_end_source"].eq("form25") & last["dated"]].reset_index()
    both = pd.concat([f25.assign(label="leaver"), ctl.assign(label="survivor")], ignore_index=True)
    rows += placebo_rows(both, both["label"], both["cik"], both["as_of_date"], METRICS,
                         "leaver", "survivor", "form25_minus_survivors, snapshot strata")
    return pd.DataFrame(rows)


def matched_survivors_sector(last, listed, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The study's draw with sector added to the cell. Returns (rows, cell coverage per leaver)."""
    rng = np.random.default_rng(seed)
    surv = set(last[last["survivor"]].index)
    pool = listed[listed["cik"].isin(surv)]
    picks, cover = [], []
    for cik, r in last[last["dated"] & last["listing_end_source"].isin(S.SOURCES)].iterrows():
        cell = pool[(pool["as_of_date"] == r["as_of_date"]) & (pool["tercile"] == r["tercile"])
                    & (pool["sector"] == r["sector"])]
        k = min(3, len(cell))
        cover.append({"cik": cik, "source": r["listing_end_source"], "sector": r["sector"], "cell_size": len(cell), "drawn": k})
        if k:
            chosen = cell.iloc[rng.choice(len(cell), k, replace=False)].copy()
            chosen["matched_to"] = cik
            picks.append(chosen)
    return pd.concat(picks, ignore_index=True), pd.DataFrame(cover)


# ---------------------------------------------------------------------------
# R2. fiscal time: how stale is the leaver's last row against the survivor rows
# ---------------------------------------------------------------------------
def row_staleness(df: pd.DataFrame) -> pd.Series:
    """Quarters since this row's fiscal year first appeared for this firm; the
    study's ``stale_q`` applied to every row."""
    first = df.groupby(["cik", "fiscal_year"])["as_of_date"].transform("min")
    return ((df["as_of_date"] - first).dt.days / 91.31).round().astype(int)


def r2_staleness(df, last, listed, ctl) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stale = row_staleness(df)
    key = pd.MultiIndex.from_frame(df[["cik", "as_of_date"]])
    lookup = pd.Series(stale.to_numpy(), index=key)
    f25 = last[last["listing_end_source"].eq("form25") & last["dated"]].reset_index()
    f25["stale_q"] = f25["stale_q"].astype(int)
    c = ctl.copy()
    c["stale_q"] = [int(lookup[(k, d)]) for k, d in zip(c["cik"], c["as_of_date"])]
    c["fy_lag"] = c["as_of_date"].dt.year - c["fiscal_year"]
    f25["fy_lag"] = f25["as_of_date"].dt.year - f25["fiscal_year"]

    dist = []
    for name, fr in (("Form 25 last row", f25), ("matched survivor rows", c)):
        d = fr["stale_q"].value_counts(normalize=True).sort_index()
        dist.append({"cohort": name, "n": len(fr), "mean_stale_q": fr["stale_q"].mean(),
                     "median_stale_q": fr["stale_q"].median(), "share_0": d.get(0, 0.0), "share_1": d.get(1, 0.0),
                     "share_2": d.get(2, 0.0), "share_3plus": float((fr["stale_q"] >= 3).mean()),
                     "mean_fy_lag": fr["fy_lag"].mean(), "share_fy_lag_ge_2": float((fr["fy_lag"] >= 2).mean())})
    dist = pd.DataFrame(dist)

    # the gap by the leaver's own staleness bucket, each against its own matched rows
    by_bucket = []
    f25["bucket"] = np.where(f25["stale_q"] <= 1, "fresh (0-1q)", "stale (2q+)")
    for b, sub in f25.groupby("bucket"):
        mine = c[c["matched_to"].isin(sub["cik"])]
        for m in MARGINS + ["fcf_margin", "altman_z"]:
            by_bucket.append({"leaver_staleness": b, "n_leavers": len(sub), "metric": m, **boot(sub, mine, m)})
    by_bucket = pd.DataFrame(by_bucket)

    # (ii) survivors matched on staleness bucket as well as snapshot and tercile
    listed = listed.copy()
    listed["stale_q"] = [int(lookup[(k, d)]) for k, d in zip(listed["cik"], listed["as_of_date"])]
    listed["bucket"] = np.where(listed["stale_q"] <= 1, "fresh (0-1q)", "stale (2q+)")
    rng = np.random.default_rng(SEED)
    pool = listed[listed["cik"].isin(set(last[last["survivor"]].index))]
    picks, short = [], 0
    for _, r in f25.iterrows():
        cell = pool[(pool["as_of_date"] == r["as_of_date"]) & (pool["tercile"] == r["tercile"]) & (pool["bucket"] == r["bucket"])]
        k = min(3, len(cell))
        short += int(k < 3)
        if k:
            ch = cell.iloc[rng.choice(len(cell), k, replace=False)].copy(); ch["matched_to"] = r["cik"]; picks.append(ch)
    stale_ctl = pd.concat(picks, ignore_index=True)
    alt = gap_table(f"staleness-matched survivors ({len(stale_ctl)} rows, {short} leavers short of 3)", f25, stale_ctl)

    # (iii) anchored at the leaver's last refresh: its fresh row against survivors on that snapshot
    terc = listed.set_index(["cik", "as_of_date"])["tercile"]
    rows_at_refresh, picks = [], []
    rng = np.random.default_rng(SEED)
    for _, r in f25.iterrows():
        row = df[(df["cik"] == r["cik"]) & (df["as_of_date"] == r["refresh"])]
        if row.empty:
            continue
        row = row.iloc[0].copy()
        t = terc.get((r["cik"], r["refresh"]), np.nan)
        rows_at_refresh.append(row)
        if np.isnan(t):
            continue
        cell = pool[(pool["as_of_date"] == r["refresh"]) & (pool["tercile"] == t)]
        k = min(3, len(cell))
        if k:
            ch = cell.iloc[rng.choice(len(cell), k, replace=False)].copy(); ch["matched_to"] = r["cik"]; picks.append(ch)
    at_refresh = pd.DataFrame(rows_at_refresh)
    ref_ctl = pd.concat(picks, ignore_index=True)
    alt = pd.concat([alt, gap_table(f"anchored at last refresh ({len(at_refresh)} leaver rows, {len(ref_ctl)} survivor rows)",
                                    at_refresh, ref_ctl)], ignore_index=True)
    return dist, by_bucket, alt


# ---------------------------------------------------------------------------
# R3. the denominator: the match rate on all 200 firms, and the coverage claims
# ---------------------------------------------------------------------------
def r3_denominator(df, last, series) -> tuple[pd.DataFrame, pd.DataFrame]:
    have = stooq.index()
    last = last.copy()
    last["has_series"] = last["ticker"].map(lambda t: stooq.stooq_key(t) in have)
    last["cohort"] = np.where(last["survivor"], "survivor",
                              np.where(last["dated"], "dated leaver: " + last["listing_end_source"].astype(str), "undated leaver"))
    rows = []
    for c, sub in last.groupby("cohort"):
        rows.append({"cohort": c, "firms": len(sub), "with_series": int(sub["has_series"].sum()),
                     "rate_pct": round(100 * sub["has_series"].mean(), 1)})
    rows.append({"cohort": "all leavers", "firms": int((~last["survivor"]).sum()),
                 "with_series": int(last.loc[~last["survivor"], "has_series"].sum()),
                 "rate_pct": round(100 * last.loc[~last["survivor"], "has_series"].mean(), 1)})
    rows.append({"cohort": "whole universe", "firms": len(last), "with_series": int(last["has_series"].sum()),
                 "rate_pct": round(100 * last["has_series"].mean(), 1)})
    rate = pd.DataFrame(rows)

    # the undated leavers: where their series begins relative to their panel presence
    first_row = df.groupby("cik")["as_of_date"].min()
    und = series[series["listed_until"].isna()].copy()
    und["first_panel_row"] = first_row.reindex(und.index).to_numpy()
    und["last_panel_row"] = last.loc[und.index, "as_of_date"].to_numpy()
    und["to_edge"] = und["series"] & und["last_bar"].eq(series["last_bar"].max())
    und["series_begins_before_first_row"] = und["series"] & (und["first_bar"] < und["first_panel_row"])
    und["series_begins_after_last_row"] = und["series"] & (und["first_bar"] > und["last_panel_row"])
    return rate, und[["ticker", "series", "first_bar", "last_bar", "first_panel_row", "last_panel_row",
                      "to_edge", "series_begins_before_first_row", "series_begins_after_last_row"]].sort_values("last_panel_row")


# ---------------------------------------------------------------------------
# R4. size and the draw: within terciles, and across survivor seeds
# ---------------------------------------------------------------------------
def r4_terciles(last, ctl) -> pd.DataFrame:
    f25 = last[last["listing_end_source"].eq("form25") & last["dated"]].reset_index()
    rows = []
    for t, sub in f25.groupby("tercile"):
        mine = ctl[ctl["matched_to"].isin(sub["cik"])]
        for m in MARGINS + ["fcf_margin", "altman_z"]:
            rows.append({"tercile": int(t), "n_leavers": len(sub), "median_revenue_$m": round(sub["revenue"].median() / 1e6),
                         "metric": m, **boot(sub, mine, m)})
    return pd.DataFrame(rows)


def r4_seeds(last, listed) -> pd.DataFrame:
    f25 = last[last["listing_end_source"].eq("form25") & last["dated"]].reset_index()
    rows = []
    for seed in [SEED] + OTHER_SEEDS:
        c = S.matched_survivors(last, listed, seed=seed)
        for m in MARGINS:
            rows.append({"seed": seed, "survivor_rows": len(c), "survivor_firms": c["cik"].nunique(), "metric": m,
                         "survivor_median": float(c[m].median()), **boot(f25, c, m)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# R5. firm identity: the same gap on an early window of the same firms
# ---------------------------------------------------------------------------
def r5_early_window(df, last, listed) -> pd.DataFrame:
    """The Form 25 firms' first panel row, and their row eight quarters before the
    last, each against three survivors on that snapshot in the firm's tercile then."""
    f25 = last[last["listing_end_source"].eq("form25") & last["dated"]]
    terc = listed.set_index(["cik", "as_of_date"])["tercile"]
    pool = listed[listed["cik"].isin(set(last[last["survivor"]].index))]
    out = []
    for name, pick in (("first panel row", lambda g: g.iloc[0]), ("8 quarters before the last row", lambda g: g.iloc[-9] if len(g) >= 9 else None)):
        rng = np.random.default_rng(SEED)
        lv, picks = [], []
        for cik in f25.index:
            g = df[df["cik"] == cik].sort_values("as_of_date")
            row = pick(g)
            if row is None:
                continue
            t = terc.get((cik, row["as_of_date"]), np.nan)
            if np.isnan(t):
                continue
            cell = pool[(pool["as_of_date"] == row["as_of_date"]) & (pool["tercile"] == t)]
            k = min(3, len(cell))
            if not k:
                continue
            lv.append(row)
            ch = cell.iloc[rng.choice(len(cell), k, replace=False)].copy(); ch["matched_to"] = cik; picks.append(ch)
        lv = pd.DataFrame(lv); c = pd.concat(picks, ignore_index=True)
        span = (f25.loc[lv["cik"], "as_of_date"].to_numpy() - lv["as_of_date"].to_numpy()).astype("timedelta64[D]").astype(int) / 365.25
        for m in MARGINS + ["altman_z"]:
            out.append({"window": name, "n_leavers": len(lv), "median_years_before_last_row": round(float(np.median(span)), 1),
                        "metric": m, "leaver_median": float(lv[m].median()), "survivor_median": float(c[m].median()), **boot(lv, c, m)})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# R6. language
# ---------------------------------------------------------------------------
WORDS = r"\b(buy|sell|hold|undervalued|overvalued|cheap|expensive|target|should|opportunit|expect|forecast|" \
        r"will |upside|downside|bullish|bearish|recommend|outperform|underperform|attractive|weak|strong|best|worst|" \
        r"risk|fail|winner|loser)"


def r6_language() -> pd.DataFrame:
    text = README.read_text()
    body = re.sub(r"\|.*\|", " ", text)  # tables are numbers, not sentences
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n\n", body) if s.strip()]
    rows = []
    for s in sents:
        hits = sorted({h.strip() for h in re.findall(WORDS, s, flags=re.I)})
        if hits:
            rows.append({"hits": ", ".join(hits), "sentence": re.sub(r"\s+", " ", s)[:220]})
    em = text.count("\u2014")
    rows.append({"hits": f"em dashes in README: {em}", "sentence": ""})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
SHORT = {"study: tercile-matched, seed 20260909": "study", "sector+tercile matched": "sector",
         "staleness-matched survivors": "stale-\nmatched", "anchored at last refresh": "at\nrefresh"}


def chart_gap_constructions(table: pd.DataFrame, source_text: str) -> None:
    fig, axes = charts.figure(
        "The Form 25 minus survivors margin gap keeps its sign under every construction; one interval, net margin with sector matching, reaches zero",
        "Bar is the difference of medians, whisker the firm bootstrap 95% interval: the study's draw, sector and staleness matching, the refresh anchor, and five other survivor draws.",
        panels=2, size=(13, 5.2))
    for ax, m, title in zip(axes, MARGINS, ("operating margin", "net margin")):
        sub = table[table["metric"] == m]
        labels = [SHORT.get(c, c) for c in sub["construction"]]
        charts.bars(ax, labels, (100 * sub["diff"]).tolist(), fmt="{:.1f}pp",
                    err=list(zip(100 * sub["lo"], 100 * sub["hi"])))
        charts.label(ax, title)
        ax.tick_params(axis="x", labelsize=8)
        charts.finish(ax, "pp")
    charts.save(fig, CHARTS / "gap-constructions.png", source_text)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    (OUT / "manifest-start.json").write_text(json.dumps(S.snapshot()))

    print("R0 reproduction: README values against the study's on-disk outputs")
    r0 = r0_reproduction(); print(fmt(r0)); print(f"all match: {bool(r0['match'].all())}")
    r0.to_csv(OUT / "r0_reproduction.csv", index=False)

    df, panel_name = S.load_panel()
    last, listed, final = S.frames(df)
    series = S.series_facts(last)
    ctl = S.matched_survivors(last, listed)
    f25 = last[last["listing_end_source"].eq("form25") & last["dated"]].reset_index()
    f15 = last[last["listing_end_source"].eq("form15") & last["dated"]].reset_index()
    gaps = gap_table("study: tercile-matched, seed 20260909", f25, ctl)

    print("\nR1a/b year-stratum placebo (exit-year strata for the form label, snapshot strata for the leaver label)")
    r1 = r1_year_stratum_placebo(last, ctl); print(fmt(r1)); r1.to_csv(OUT / "r1_year_stratum_placebo.csv", index=False)

    print("\nR1c survivors matched on sector as well as snapshot and tercile")
    sctl, cover = matched_survivors_sector(last, listed)
    print("cell coverage (drawn rows per leaver):"); print(cover.groupby(["source", "drawn"]).size().unstack(fill_value=0))
    r1c = gap_table(f"sector+tercile matched ({len(sctl)} rows, {sctl['cik'].nunique()} firms)",
                    f25, sctl[sctl["matched_to"].isin(f25["cik"])])
    r1c = pd.concat([r1c, gap_table("form15 minus sector-matched survivors", f15, sctl[sctl["matched_to"].isin(f15["cik"])])], ignore_index=True)
    print(fmt(r1c)); r1c.to_csv(OUT / "r1c_sector_matched.csv", index=False); cover.to_csv(OUT / "r1c_sector_cells.csv", index=False)
    both = pd.concat([f25.assign(label="leaver"), sctl[sctl["matched_to"].isin(f25["cik"])].assign(label="survivor")], ignore_index=True)
    r1d = pd.DataFrame(placebo_rows(both, both["label"], both["cik"], both["as_of_date"], MARGINS + ["fcf_margin", "altman_z"],
                                    "leaver", "survivor", "form25_minus_sector_matched, snapshot strata"))
    print(fmt(r1d)); r1d.to_csv(OUT / "r1d_sector_matched_placebo.csv", index=False)

    print("\nR2 fiscal time: staleness of the leaver's last row against the matched survivor rows")
    dist, by_bucket, alt = r2_staleness(df, last, listed, ctl)
    print(fmt(dist)); print(fmt(by_bucket)); print(fmt(alt))
    dist.to_csv(OUT / "r2_staleness.csv", index=False); by_bucket.to_csv(OUT / "r2_gap_by_staleness.csv", index=False)
    alt.to_csv(OUT / "r2_alt_constructions.csv", index=False)

    print("\nR3 the denominator: series in the bundle by cohort, on all 200 firms")
    rate, und = r3_denominator(df, last, series); print(fmt(rate)); print(und.to_string())
    rate.to_csv(OUT / "r3_match_rate.csv", index=False); und.to_csv(OUT / "r3_undated_series.csv")

    print("\nR4a Form 25 minus its own matched survivors, within revenue terciles")
    r4a = r4_terciles(last, ctl); print(fmt(r4a)); r4a.to_csv(OUT / "r4a_terciles.csv", index=False)
    print("\nR4b the same gap under six survivor draws")
    r4b = r4_seeds(last, listed); print(fmt(r4b)); r4b.to_csv(OUT / "r4b_seeds.csv", index=False)
    for m in MARGINS:
        sub = r4b[r4b["metric"] == m]
        print(f"{m}: gap range {100 * sub['diff'].min():.1f} to {100 * sub['diff'].max():.1f}pp; "
              f"upper bound range {100 * sub['hi'].min():.1f} to {100 * sub['hi'].max():.1f}pp; "
              f"intervals excluding zero {int((sub['hi'] < 0).sum())} of {len(sub)}")

    print("\nR5 firm identity: the same firms on an early window against survivors then")
    r5 = r5_early_window(df, last, listed); print(fmt(r5)); r5.to_csv(OUT / "r5_early_window.csv", index=False)

    print("\nR6 language scan of the reviewed README")
    r6 = r6_language(); print(r6.to_string(index=False)); r6.to_csv(OUT / "r6_language.csv", index=False)

    summary = pd.concat([gaps, r1c[r1c["construction"].str.startswith("sector")], alt,
                         r4b[r4b["seed"] != SEED].assign(construction=lambda d: "seed " + d["seed"].astype(str))
                         [["construction", "metric", "diff", "lo", "hi", "n_a", "n_b"]]], ignore_index=True)
    summary = summary[summary["metric"].isin(MARGINS)]
    summary["construction"] = summary["construction"].str.replace(r" \(.*\)", "", regex=True)
    summary.to_csv(OUT / "summary_margin_gaps.csv", index=False)
    print("\nSummary: Form 25 minus survivors on the two margins under every construction"); print(fmt(summary))
    src = (f"Distill Markets point-in-time export, {panel_name}, snapshots {df['as_of_date'].min().date()} to "
           f"{final.date()}; review of research/listing-end.")
    chart_gap_constructions(summary, src)

    (OUT / "manifest-end.json").write_text(json.dumps(S.snapshot()))
    start = json.loads((OUT / "manifest-start.json").read_text())
    end = json.loads((OUT / "manifest-end.json").read_text())
    changed = [e for e in end if e not in start and not e[0].startswith(str(OUT))]
    print(f"\ncache entries that changed during the run, outside this review's folder: {len(changed)}")


if __name__ == "__main__":
    main()
