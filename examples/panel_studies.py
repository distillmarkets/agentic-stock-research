"""Panel studies on the Distill point-in-time fundamentals grid.

Input: the panel on disk, the full export or the published sample (client.panel_path).
Every study uses December as-of snapshots of listed equities with revenue > 0.
Transitions come from analysis.transitions, which only counts a pair when the
later snapshot cites a NEWER fiscal year (i.e. a new filing actually arrived;
no phantom transitions from stale rows).

Studies:
  A. Accruals (Sloan): accruals_ratio quintile at T -> next-FY margin/health changes
  B. Capital cycle: capex_intensity x asset_growth at T -> op-margin change over 2 FYs
  C. Boom cell today: who currently sits in the cell
  E. Persistence: health-score bucket transition matrix; score persistence;
     panel-exit rates by health bucket (delisting proxy)
"""

import pandas as pd

from distill_toolkit import analysis, client


HEALTH_BINS = [0, 30, 50, 70, 85, 100]
HEALTH_LABELS = ["0-30", "30-50", "50-70", "70-85", "85-100"]


def load_december_snapshots() -> pd.DataFrame:
    df = pd.read_csv(client.panel_path(), parse_dates=["as_of_date"])
    if "health_score" not in df.columns:
        # If the export carries no health score column, the health sections are
        # skipped, not faked; the score lives on /sec/financial-health/{ticker}.
        df["health_score"] = float("nan")
        print("note: this export has no health_score column; health-score sections are skipped")
    dec = df[
        (df.as_of_date.dt.month == 12) & df.is_listed_equity & (df.revenue > 0)
    ].copy()
    dec["year"] = dec.as_of_date.dt.year
    return dec


def study_accruals(p: pd.DataFrame) -> pd.DataFrame:
    s = p.dropna(subset=["accruals_ratio", "net_margin", "net_margin_next"]).copy()
    s["acc_q"] = s.groupby("base_year").accruals_ratio.transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop")
    )
    s["d_netm"] = s.net_margin_next - s.net_margin
    s["d_health"] = s.health_score_next - s.health_score
    return s.groupby("acc_q").agg(
        n=("d_netm", "size"),
        d_net_margin_med=("d_netm", "median"),
        pct_health_drop10=("d_health", lambda x: (x <= -10).mean() * 100),
    ).round(4)


def study_capital_cycle(p2: pd.DataFrame):
    s = p2.dropna(subset=["capex_intensity", "asset_growth",
                          "operating_margin", "operating_margin_next"])
    s = analysis.add_outcomes(s)
    for col, q in (("capex_intensity", "cap_q"), ("asset_growth", "ag_q")):
        s[q] = s.groupby("base_year")[col].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates="drop")
        )
    quintiles = s.groupby("cap_q").agg(
        n=("d_opm", "size"),
        capex_med=("capex_intensity", "median"),
        d_operating_margin_med=("d_opm", "median"),
        pct_opm_drop5pp=("d_opm", lambda x: (x <= -0.05).mean() * 100),
    ).round(4)
    boom = s[(s.cap_q == 4) & (s.ag_q == 4)]
    quiet = s[(s.cap_q == 0) & (s.ag_q == 0)]
    cells = pd.DataFrame(
        {
            "n": [len(boom), len(quiet)],
            "d_operating_margin_med": [boom.d_opm.median(), quiet.d_opm.median()],
            "pct_opm_drop5pp": [
                (boom.d_opm <= -0.05).mean() * 100,
                (quiet.d_opm <= -0.05).mean() * 100,
            ],
        },
        index=["boom (hi capex, hi growth)", "quiet (lo capex, lo growth)"],
    ).round(4)
    return quintiles, cells


def study_boom_cell_today(df: pd.DataFrame, today: str) -> pd.DataFrame:
    latest = df[df.as_of_date <= today].as_of_date.max()
    snap = df[
        (df.as_of_date == latest) & df.is_listed_equity & (df.revenue > 0)
    ].dropna(subset=["capex_intensity", "asset_growth"]).copy()
    snap = snap[snap.operating_margin.abs() < 1]
    snap["cap_q"] = pd.qcut(snap.capex_intensity, 5, labels=False, duplicates="drop")
    snap["ag_q"] = pd.qcut(snap.asset_growth, 5, labels=False, duplicates="drop")
    return snap[(snap.cap_q == 4) & (snap.ag_q == 4)].sort_values(
        "revenue", ascending=False
    )


def study_persistence(p: pd.DataFrame, dec: pd.DataFrame):
    s = p.dropna(subset=["health_score", "health_score_next"]).copy()
    s["bucket"] = pd.cut(s.health_score, HEALTH_BINS, labels=HEALTH_LABELS,
                         include_lowest=True)
    s["bucket_next"] = pd.cut(s.health_score_next, HEALTH_BINS,
                              labels=HEALTH_LABELS, include_lowest=True)
    tm = (pd.crosstab(s.bucket, s.bucket_next, normalize="index") * 100).round(1)

    alive = dec.groupby("cik").year.max()
    base = dec[(dec.year >= 2013) & (dec.year <= 2023)].copy()
    base["gone_2y"] = base.cik.map(alive) <= base.year + 1
    base["hbucket"] = pd.cut(base.health_score, HEALTH_BINS, labels=HEALTH_LABELS,
                             include_lowest=True)
    exit_rates = (base.groupby("hbucket", observed=True).gone_2y.mean() * 100).round(1)
    return tm, exit_rates


def main():
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    df = pd.read_csv(client.panel_path(), parse_dates=["as_of_date"])

    # A free key's export is the current snapshot only (one as_of_date). That runs
    # the cross-sectional study (C: boom cell today) but not the transition studies;
    # those need the Pro as-of history grid.
    if df.as_of_date.nunique() == 1:
        print(f"panel is a single snapshot ({df.as_of_date.iloc[0].date()}), free-tier cut.")
        print("Running the cross-sectional study; A/B/E need the Pro history grid.\n")
        boom = study_boom_cell_today(df, today)
        cols = ["ticker", "sector", "fiscal_year", "revenue", "capex_intensity",
                "asset_growth", "operating_margin", "health_score", "piotroski"]
        cols = [c for c in cols if c in boom.columns]
        print(f"STUDY C - boom cell today: {len(boom)} firms; largest by revenue:")
        print(boom[cols].head(15).to_string(index=False))
        return

    dec = load_december_snapshots()
    p1 = analysis.transitions(dec, 1)
    p2 = analysis.transitions(dec, 2)
    print(f"panel rows={len(df)}, 1y transitions={len(p1)}, 2y={len(p2)}\n")

    print("STUDY A - accruals quintile (0=low) -> next-FY changes")
    print(study_accruals(p1).to_string(), "\n")

    quintiles, cells = study_capital_cycle(p2)
    print("STUDY B - capex quintile (0=low) -> 2-FY op-margin change")
    print(quintiles.to_string(), "\n")
    print(cells.to_string(), "\n")

    boom = study_boom_cell_today(df, today)
    print(f"STUDY C - boom cell today: {len(boom)} firms; largest by revenue:")
    cols = ["ticker", "sector", "fiscal_year", "revenue", "capex_intensity",
            "asset_growth", "operating_margin", "health_score", "piotroski"]
    cols = [c for c in cols if c in boom.columns]
    print(boom[cols].head(15).to_string(index=False), "\n")

    if dec.health_score.isna().all():
        print("STUDY E skipped: no health_score in this export")
        return
    tm, exit_rates = study_persistence(p1, dec)
    print("STUDY E - health bucket transition matrix (%, row=now, col=next FY)")
    print(tm.to_string(), "\n")
    print("panel-exit within ~2y by health bucket (delisting proxy, %):")
    print(exit_rates.to_string())


if __name__ == "__main__":
    main()
