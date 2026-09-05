"""Tests for distill_toolkit.analysis. Every frame here is synthetic: made-up
paths, firm-years and share counts chosen so the expected answer can be worked
out by hand. No record from any data source appears in this file."""

import numpy as np
import pandas as pd
import pytest

from distill_toolkit import analysis, stooq

from conftest import DATES


# ---- survival -------------------------------------------------------------
def _paths(prefix="r"):
    """Four synthetic firm-years over six months.

    A halves at month 2 and then loses its path at month 4; B survives all six;
    C is censored at month 3 without failing; D halves at month 5.
    """
    rows = [
        [-0.10, -0.60, -0.70, np.nan, np.nan, np.nan],
        [0.10, 0.10, 0.10, 0.10, 0.10, 0.10],
        [0.00, 0.00, 0.00, np.nan, np.nan, np.nan],
        [0.00, 0.00, 0.00, 0.00, -0.50, -0.55],
    ]
    return pd.DataFrame(rows, columns=[f"{prefix}_{k}" for k in range(1, 7)])


def test_failure_times_are_first_crossing_and_last_observation():
    fail, last = analysis.failure_times(_paths().to_numpy())
    assert fail[0] == 2.0 and np.isnan(fail[1]) and np.isnan(fail[2]) and fail[3] == 5.0
    assert list(last) == [3.0, 6.0, 3.0, 6.0]


def test_survival_curve_keeps_a_failure_that_later_loses_its_path():
    inc = analysis.survival_curve(_paths(), horizons=6).incidence
    # A fails at month 2 with four at risk, D at month 5 with two.
    assert inc[2] == pytest.approx(0.25)
    assert inc[4] == pytest.approx(0.25)
    assert inc[6] == pytest.approx(0.625)
    # Failure is absorbing: incidence never falls back.
    assert list(inc) == sorted(inc)


def test_survival_curve_reads_the_market_adjusted_basis():
    raw = analysis.survival_curve(_paths("x"), horizons=6, prefix="x").incidence
    assert raw[6] == pytest.approx(0.625)
    with pytest.raises(KeyError):
        analysis.survival_curve(_paths("x"), horizons=6, prefix="r")


def test_survival_curve_refuses_the_delisting_event():
    with pytest.raises(ValueError, match="delisted"):
        analysis.survival_curve(_paths(), event="ended", horizons=6)


def test_crossing_reads_a_level_off_the_incidence():
    inc = analysis.survival_curve(_paths(), horizons=6).incidence
    assert analysis.crossing(inc, 0.25) == 2
    assert analysis.crossing(inc, 0.60) == 5
    assert analysis.crossing(inc, 0.90) is None


# ---- transitions ----------------------------------------------------------
def _dec():
    return pd.DataFrame({
        "cik": ["1", "2", "3", "1", "2"],
        "year": [2020, 2020, 2020, 2021, 2021],
        "fiscal_year": [2020, 2019, 2020, 2021, 2019],
        "revenue": [100.0, 200.0, 300.0, 120.0, 260.0],
        "operating_margin": [0.10, 0.20, 0.30, 0.05, 0.25],
    })


def test_transitions_pairs_only_when_a_newer_fiscal_year_arrived():
    p = analysis.transitions(_dec(), 1)
    assert list(p.cik) == ["1"]  # CIK 2's later snapshot still cites FY2019
    assert p.base_year.iloc[0] == 2020
    assert p.revenue_next.iloc[0] == pytest.approx(120.0)


def test_transitions_is_empty_when_no_year_has_a_partner():
    assert len(analysis.transitions(_dec(), 5)) == 0


def test_add_outcomes_derives_only_the_pairs_that_exist():
    p = analysis.transitions(_dec(), 1)
    out = analysis.add_outcomes(p)
    assert out.d_opm.iloc[0] == pytest.approx(-0.05)
    assert out.rev_growth.iloc[0] == pytest.approx(0.2)
    assert "d_health" not in out.columns  # no health score in this export


def test_add_outcomes_drops_a_margin_no_firm_can_have():
    pairs = pd.DataFrame({"operating_margin": [0.1, 7.0], "operating_margin_next": [0.2, 8.0]})
    assert len(analysis.add_outcomes(pairs)) == 1
    assert len(analysis.add_outcomes(pairs, drop_absurd_margins=False)) == 2


def test_add_outcomes_filters_the_absurd_margin_on_the_outcome_leg_too():
    # The base year is ordinary and the NEXT year is the artefact. The next-year
    # value is the outcome a transition study reads, so filtering only the base
    # would leave a 39.9 point change in d_opm.
    pairs = pd.DataFrame({"operating_margin": [0.1, 0.1], "operating_margin_next": [0.2, 40.0]})
    out = analysis.add_outcomes(pairs)
    assert len(out) == 1
    assert out.d_opm.iloc[0] == pytest.approx(0.1)
    assert len(analysis.add_outcomes(pairs, drop_absurd_margins=False)) == 2


# ---- coverage flags -------------------------------------------------------
def _coverage_frame():
    return pd.DataFrame({
        "ticker": ["RAMP", "TINY", "NOPE", "RAMP"],
        "cik": ["1", "2", "3", "1"],
        "year": [2021, 2021, 2021, 2030],
        "as_of_date": [DATES[200], DATES[200], DATES[200], pd.Timestamp("2030-01-04")],
    })


def test_priced_flags_are_nominal_coverage(bundle_root):
    flags = analysis.priced_flags(_coverage_frame())
    assert list(flags) == [True, True, False, True]


def test_fresh_close_flags_are_usable_coverage(bundle_root):
    dec = _coverage_frame()
    nominal = analysis.priced_flags(dec)
    usable = analysis.fresh_close_flags(dec)
    # TINY has a file but no usable history; the 2030 row has no recent close.
    assert list(usable) == [True, False, False, False]
    assert usable.sum() < nominal.sum()


# ---- event-time paths -----------------------------------------------------
def test_abnormal_path_looks_backwards_from_the_event(bundle_root):
    p = analysis.abnormal_path("RAMP", DATES[100], -2, 2)
    assert p is not None and len(p) == 5
    # Day -1 is the base close itself, so it is zero by construction.
    assert p[1] == pytest.approx(0.0)
    assert p[0] == pytest.approx(198 / 199 - 1)
    assert p[2] == pytest.approx(200 / 199 - 1)  # day 0 is the first close on or after
    assert p[4] == pytest.approx(202 / 199 - 1)


def test_abnormal_path_is_none_without_a_fresh_close(bundle_root):
    assert analysis.abnormal_path("RAMP", pd.Timestamp("2030-01-04"), -2, 2) is None
    assert analysis.abnormal_path("NOPE", DATES[100], -2, 2) is None


def test_path_between_samples_the_window_at_equal_fractions(bundle_root):
    out = analysis.path_between("RAMP", DATES[10], DATES[110], points=10, post_days=5)
    assert out is not None
    assert out["ntd"] == 99  # last close before d1 is DATES[109]
    assert out["pre"] == pytest.approx(np.log(209 / 110))
    # Halfway through 99 trading days is the close 50 days on from the first.
    assert out["p_5"] == pytest.approx(np.log(160 / 110))
    assert out["post"] == pytest.approx(np.log(214 / 209))
    assert out["total"] == pytest.approx(out["pre"] + out["post"])


def test_path_between_rejects_anchors_that_are_too_close(bundle_root):
    assert analysis.path_between("RAMP", DATES[10], DATES[15]) is None


def test_shift_trading_days_moves_on_the_price_calendar(bundle_root):
    assert analysis.shift_trading_days("RAMP", DATES[100], 0) == DATES[100]
    assert analysis.shift_trading_days("RAMP", DATES[100], 2) == DATES[102]
    assert analysis.shift_trading_days("RAMP", DATES[100], -2) == DATES[98]
    assert analysis.shift_trading_days("RAMP", DATES[100], 10_000) is None
    assert analysis.shift_trading_days("NOPE", DATES[100], 2) is None


# ---- resampling -----------------------------------------------------------
def test_cluster_bootstrap_moves_whole_groups_together():
    values = np.r_[np.zeros(50), np.full(50, 10.0)]
    groups = np.r_[np.full(50, "A"), np.full(50, "B")]
    obs, lo, hi = analysis.cluster_bootstrap(values, groups, draws=400)
    assert obs == pytest.approx(5.0)
    # Whole groups move as one, so a draw is 0, 5 or 10 and the interval spans it.
    assert lo <= 0.5 and hi >= 9.5


def test_cluster_bootstrap_drops_nan_and_survives_an_empty_input():
    obs, lo, hi = analysis.cluster_bootstrap([1.0, np.nan, 1.0], ["a", "b", "c"], draws=50)
    assert obs == pytest.approx(1.0) and lo == pytest.approx(1.0)
    assert all(np.isnan(v) for v in analysis.cluster_bootstrap([np.nan], ["a"], draws=10))


def test_cluster_boot_diff_reports_the_gap_between_two_cohorts():
    a = pd.DataFrame({"cik": ["A1", "A1", "A2"], "v": [10.0, 10.0, 10.0]})
    b = pd.DataFrame({"cik": ["B1", "B2", "B2"], "v": [4.0, 4.0, 4.0]})
    obs, lo, hi, p_le_0 = analysis.cluster_boot_diff(a, b, "v", draws=200)
    assert obs == pytest.approx(6.0)
    assert lo == pytest.approx(6.0) and hi == pytest.approx(6.0)
    assert p_le_0 == 0.0


def test_clustered_shuffle_carries_a_whole_group_label_series():
    labels = pd.Series([1, 1, 1, 2, 2, 2, 3, 3, 3])
    groups = pd.Series(["g1"] * 3 + ["g2"] * 3 + ["g3"] * 3)
    out = analysis.clustered_shuffle(labels, groups, seed=1)
    assert sorted(out) == sorted(labels)
    # Each group's label was constant and stays constant: the series moved whole.
    assert all(out[groups == g].nunique() == 1 for g in ("g1", "g2", "g3"))


def test_clustered_shuffle_within_a_period_keeps_that_period_intact():
    df = pd.DataFrame({
        "cik": ["a", "a", "b", "b", "c", "c"],
        "period": [1, 2, 1, 2, 1, 2],
        "label": [10.0, 11.0, 20.0, 21.0, 30.0, 31.0],
    })
    out = analysis.clustered_shuffle(df.label, df.cik, within=df.period, seed=3)
    for p in (1, 2):
        mask = df.period == p
        assert sorted(out[mask]) == sorted(df.label[mask])


def test_within_firm_shuffle_keeps_every_group_distribution():
    df = pd.DataFrame({"cik": ["a"] * 6 + ["b"] * 6, "v": list(range(6)) + list(range(100, 106))})
    out = analysis.within_firm_shuffle(df, "v", seed=0)
    for g in ("a", "b"):
        assert sorted(out[df.cik == g]) == sorted(df.v[df.cik == g])
    # The pairing between value and row is what the null destroys.
    assert not out.equals(df.v)


def test_extremes_vs_middle_sees_a_shape_that_q5_minus_q1_calls_null():
    df = pd.DataFrame({
        "q": [1, 2, 3, 4, 5] * 20,
        "y": [1.0, 0.5, 0.0, 0.5, 1.0] * 20,
        "cik": [f"c{i}" for i in range(50)] * 2,
    })
    q5, q1 = df[df.q == 5].y.mean(), df[df.q == 1].y.mean()
    assert q5 - q1 == pytest.approx(0.0)  # the wrong summary for a two-sided variable
    out = analysis.extremes_vs_middle(df, "q", "y", groups="cik", draws=100)
    assert out["gap"] == pytest.approx(1.0)
    assert out["n_extremes"] == 40 and out["n_middle"] == 20
    assert out["lo"] <= out["gap"] <= out["hi"]


# ---- the point-in-time record anchors --------------------------------------
def _panel() -> pd.DataFrame:
    """Two filers on a quarter-end grid. Firm 1 refreshes twice, firm 2 once.

    Firm 1 arrives in 2020Q1 carrying fiscal 2019, repeats it for two more
    quarters, then refreshes to fiscal 2020 at the December quarter end. Firm 2
    has a single row.
    """
    rows = [
        (1, "2020-03-31", 2019), (1, "2020-06-30", 2019), (1, "2020-09-30", 2019),
        (1, "2020-12-31", 2020),
        (2, "2020-06-30", 2019),
    ]
    return pd.DataFrame(
        [{"cik": c, "as_of_date": pd.Timestamp(d), "fiscal_year": fy} for c, d, fy in rows])


def test_record_refresh_events_is_the_first_quarter_a_fiscal_year_appears():
    ev = analysis.record_refresh_events(_panel())
    assert list(ev.as_of_date.dt.strftime("%Y-%m-%d")) == ["2020-03-31", "2020-12-31", "2020-06-30"]
    assert list(ev.fiscal_year) == [2019, 2020, 2019]


def test_record_refresh_events_marks_an_arrival_apart_from_a_refresh():
    ev = analysis.record_refresh_events(_panel())
    arrivals = dict(zip(zip(ev.cik, ev.fiscal_year), ev.first_panel_row))
    assert arrivals[(1, 2019)] is np.True_ or arrivals[(1, 2019)]
    assert not arrivals[(1, 2020)]
    assert arrivals[(2, 2019)]


def test_record_refresh_events_can_age_every_row_instead_of_cutting_to_events():
    full = analysis.record_refresh_events(_panel(), events_only=False)
    assert len(full) == 5
    stale = full[(full.cik == 1) & (full.as_of_date == pd.Timestamp("2020-09-30"))]
    # 31 March to 30 September 2020 is 183 days of a record that did not change.
    assert int(stale.fy_age_days.iloc[0]) == 183
    assert int(full.is_refresh.sum()) == 3


# ---- exits ------------------------------------------------------------------
def _exit_panel() -> pd.DataFrame:
    """Firm 1 stops filing in 2020 after two stale quarters. Firm 2 files throughout."""
    rows = []
    for d in pd.date_range("2018-03-31", "2020-12-31", freq="QE"):
        fy = 2019 if d >= pd.Timestamp("2020-06-30") else 2018
        rows.append({"cik": 1, "as_of_date": d, "fiscal_year": fy})
    for d in pd.date_range("2018-03-31", "2024-12-31", freq="QE"):
        rows.append({"cik": 2, "as_of_date": d, "fiscal_year": d.year - 1})
    return pd.DataFrame(rows)


def test_exit_frame_dates_the_stop_and_the_last_refresh_apart():
    firms = analysis.exit_frame(_exit_panel())
    assert firms.loc[1, "last_row"] == pd.Timestamp("2020-12-31")
    assert firms.loc[1, "last_refresh"] == pd.Timestamp("2020-06-30")
    # Two quarters of a repeated annual block between the refresh and the drop.
    assert firms.loc[1, "stale_tail_quarters"] == 2
    assert bool(firms.loc[1, "exit"]) and not bool(firms.loc[2, "exit"])


def test_exit_frame_moves_the_exit_date_with_the_anchor():
    late = analysis.exit_frame(_exit_panel(), anchor="last_row")
    early = analysis.exit_frame(_exit_panel(), anchor="last_refresh")
    assert late.loc[1, "exit_date"] > early.loc[1, "exit_date"]
    with pytest.raises(ValueError, match="anchor"):
        analysis.exit_frame(_exit_panel(), anchor="delisted_at")


def test_exit_frame_censors_an_anchor_row_whose_window_has_not_closed():
    panel = _exit_panel()
    rows = pd.DataFrame({"cik": [1, 1, 2],
                         "as_of_date": [pd.Timestamp("2018-12-31"),
                                        pd.Timestamp("2020-12-31"),
                                        pd.Timestamp("2018-12-31")]})
    out = analysis.exit_frame(panel, rows=rows)
    # 2018Q4 plus eight quarters is 2020Q4, inside the 2024Q4 vintage: observable.
    assert out.exit_observable.tolist() == [True, True, True]
    assert out.exit.tolist() == [1.0, 1.0, 0.0]
    late = analysis.exit_frame(panel, rows=rows, runway_quarters=32)
    assert late.exit_observable.tolist() == [False, False, False]
    assert late.exit.isna().all()


def test_exit_frame_marks_the_rows_that_repeat_one_filing():
    rows = pd.DataFrame({"cik": [1, 1],
                         "as_of_date": [pd.Timestamp("2020-06-30"), pd.Timestamp("2020-12-31")]})
    out = analysis.exit_frame(_exit_panel(), rows=rows)
    assert out.after_last_refresh.tolist() == [False, True]


# ---- ranking ----------------------------------------------------------------
def _atom_frame() -> pd.DataFrame:
    """Nine rows in one year, two thirds of them exactly zero: the shape that breaks qcut."""
    return pd.DataFrame({"year": [2020] * 9, "v": [0, 0, 0, 0, 0, 0, 1.0, 2.0, 3.0]})


def test_qcut_within_splits_an_atom_at_zero_across_bins():
    q = analysis.qcut_within(_atom_frame(), "v", "year", q=3, min_per_bin=1)
    assert sorted(q.value_counts().to_dict().values()) == [3, 3, 3]
    # The six zeros land in bins 1, 1, 1, 2, 2, 2 because the rank comes first.
    assert q.tolist()[:6] == [1.0, 1.0, 1.0, 2.0, 2.0, 2.0]
    with pytest.raises(ValueError):
        pd.qcut(_atom_frame().v, 3)


def test_qcut_within_leaves_a_cohort_too_thin_to_cut_as_nan():
    d = pd.DataFrame({"year": [2020, 2020] + [2021] * 30, "v": list(range(32))})
    q = analysis.qcut_within(d, "v", "year", q=5, min_per_bin=5)
    assert q[d.year == 2020].isna().all()
    assert q[d.year == 2021].notna().all()


def test_tercile_is_qcut_within_at_three():
    d = _atom_frame()
    assert analysis.tercile(d, "v", "year", min_per_bin=1).equals(
        analysis.qcut_within(d, "v", "year", q=3, min_per_bin=1))


# ---- firm type against firm timing -----------------------------------------
def _ladder_frame() -> pd.DataFrame:
    """Twenty firms, five years each. The outcome is a firm constant and the
    column is that constant plus year noise, so the sort is entirely about which
    firm and not at all about which year."""
    rng = np.random.default_rng(0)
    rows = []
    for cik in range(60):
        level = cik / 10.0
        for year in range(2015, 2020):
            rows.append({"cik": cik, "year": year, "col": level + rng.normal(0, 0.01),
                         "out": level})
    return pd.DataFrame(rows)


def test_decomposition_ladder_separates_which_firm_from_which_year():
    t = analysis.decomposition_ladder(_ladder_frame(), "col", "out", q=5, draws=50,
                                      min_history=5)
    assert list(t.index) == ["this row's value", "the firm's mean over prior rows only",
                             "the within-firm rank of this row",
                             "the within-firm demeaned value"]
    assert t.loc["this row's value", "gap"] > 4.0
    # Timing carries nothing here, so demeaning the firm out takes the gap to zero.
    assert abs(t.loc["the within-firm demeaned value", "gap"]) < 0.5
    assert t.loc["the within-firm rank of this row", "n"] == 300
    # A backward mean needs two prior rows, so the first two of each firm drop.
    assert t.loc["the firm's mean over prior rows only", "n"] == 180


def test_presample_label_fixes_the_label_on_a_disjoint_window():
    rows = []
    for cik, level in ((1, 10.0), (2, 20.0)):
        for year in (2010, 2011, 2014, 2015):
            rows.append({"cik": cik, "year": year, "v": level})
    rows.append({"cik": 3, "year": 2010, "v": 99.0})   # one label row only
    rows.append({"cik": 3, "year": 2015, "v": 99.0})
    d = pd.DataFrame(rows)
    out = analysis.presample_label(d, "v", label_years=(2010, 2011), eval_years=(2014, 2015))
    assert set(out.year) == {2014, 2015}
    assert set(out.cik) == {1, 2}                       # firm 3 fails min_rows
    assert out[out.cik == 1].presample_v.tolist() == [10.0, 10.0]


def test_presample_label_refuses_windows_that_touch():
    d = pd.DataFrame({"cik": [1], "year": [2010], "v": [1.0]})
    with pytest.raises(ValueError, match="overlap"):
        analysis.presample_label(d, "v", label_years=(2010, 2013), eval_years=(2013, 2015))


def test_year_stratum_shuffle_permutes_inside_a_cell_and_nowhere_else():
    d = pd.DataFrame({"year": [2020] * 4 + [2021] * 4,
                      "s": ["a", "a", "b", "b"] * 2,
                      "v": [1.0, 2.0, 30.0, 40.0, 5.0, 6.0, 70.0, 80.0]})
    out = analysis.year_stratum_shuffle(d, "v", "s", seed=3)
    for (_y, _s), g in d.groupby(["year", "s"]):
        assert sorted(out.loc[g.index]) == sorted(g.v)
    assert out.index.equals(d.index)


# ---- cluster resampling -----------------------------------------------------
def test_cluster_resample_index_draws_whole_groups():
    groups = np.array([0, 0, 0, 1, 1, 1, 2, 2, 2])
    draws = list(analysis.cluster_resample_index(groups, draws=20, seed=1))
    assert all(len(d) == 9 for d in draws)
    for d in draws:
        counts = np.bincount(groups[d], minlength=3)
        assert set(counts) <= {0, 3, 6, 9}              # a group arrives whole or not at all
    again = list(analysis.cluster_resample_index(groups, draws=20, seed=1))
    assert all((a == b).all() for a, b in zip(draws, again))


def test_boot_ratio_is_the_ratio_and_its_interval_collapses_when_nothing_varies():
    groups = np.arange(30)
    num = np.full(30, 2.0)
    den = np.full(30, 1.0)
    obs, lo, hi = analysis.boot_ratio(num, den, groups, draws=50)
    assert (obs, lo, hi) == (2.0, 2.0, 2.0)
    with pytest.raises(ValueError, match="same number of rows"):
        analysis.boot_ratio(num, den[:5], groups)


def test_boot_ratio_takes_a_wide_denominator():
    groups = np.arange(20)
    num = np.full((20, 1), 4.0)
    den = np.full((20, 6), 2.0)
    obs, lo, hi = analysis.boot_ratio(num, den, groups, draws=30)
    assert obs == pytest.approx(2.0)
    assert lo == pytest.approx(2.0) and hi == pytest.approx(2.0)


# ---- daily event time -------------------------------------------------------
def test_daily_abnormal_is_bar_to_bar_and_not_a_differenced_cumulative(bundle_root):
    ar = analysis.daily_abnormal("RAMP", DATES[10], 0, 2)
    # RAMP closes at 100 + i and SPY is flat, so day k's abnormal return is 1/(99+k).
    assert ar == pytest.approx([1 / 109, 1 / 110, 1 / 111])
    cum = analysis.abnormal_path("RAMP", DATES[10], 0, 2)
    assert np.diff(cum)[0] != pytest.approx(ar[1])


def test_daily_abnormal_refuses_a_window_that_runs_off_the_series(bundle_root):
    assert analysis.daily_abnormal("RAMP", DATES[0], -5, 5) is None
    assert analysis.daily_abnormal("RAMP", DATES[-1], 0, 5) is None
    assert analysis.daily_abnormal("NOSUCH", DATES[10], 0, 2) is None


def test_med_abs_ratio_scales_the_event_day_by_the_quiet_days():
    offsets = np.arange(-7, 8)
    mat = np.full((5, len(offsets)), 0.02)
    mat[:, np.abs(offsets) >= 6] = 0.01
    mat[:, offsets == 0] = 0.05
    assert analysis.med_abs_ratio(mat, offsets, day=0, quiet_min=6) == pytest.approx(5.0)


# ---- calendar-day segments --------------------------------------------------
def test_segment_returns_compounds_each_segment_off_its_own_start(bundle_root):
    ev = pd.DataFrame({"ticker": ["RAMP"], "as_of_date": [DATES[100]]})
    out = analysis.segment_returns(
        ev, {"early": (0, 30), "late": (30, 60), "whole": (0, 60)})
    early, late, whole = out.early.iloc[0], out.late.iloc[0], out.whole.iloc[0]
    assert (1 + early) * (1 + late) - 1 == pytest.approx(whole)
    # A flat benchmark makes the adjusted return equal the raw one.
    assert out.early.iloc[0] == pytest.approx(out.early_raw.iloc[0])
    assert out.early_bench.iloc[0] == pytest.approx(0.0)


def test_segment_returns_prices_its_endpoints_where_close_at_does(bundle_root):
    ev = pd.DataFrame({"ticker": ["RAMP"], "as_of_date": [DATES[100]]})
    out = analysis.segment_returns(ev, {"seg": (0, 30)})
    base = stooq.close_at("RAMP", DATES[99])
    end = stooq.close_at("RAMP", DATES[100] + pd.Timedelta(days=30))
    assert out.seg_raw.iloc[0] == pytest.approx(end / base - 1)
    assert out.seg_end.iloc[0] <= DATES[100] + pd.Timedelta(days=30)


def test_segment_returns_holds_a_hard_right_edge(bundle_root):
    ev = pd.DataFrame({"ticker": ["RAMP"], "as_of_date": [DATES[-1]]})
    out = analysis.segment_returns(ev, {"past_the_edge": (0, 400)})
    assert np.isnan(out.past_the_edge.iloc[0])
    slack = analysis.segment_returns(ev, {"past_the_edge": (0, 400)}, edge_slack_days=500)
    assert not np.isnan(slack.past_the_edge.iloc[0])


def test_segment_returns_shifts_the_anchor_and_drops_a_stale_event(bundle_root):
    ev = pd.DataFrame({"ticker": ["RAMP", "RAMP"], "as_of_date": [DATES[100], DATES[100]]})
    plain = analysis.segment_returns(ev, {"s": (0, 30)})
    moved = analysis.segment_returns(ev, {"s": (0, 30)}, anchor_shift=20)
    assert (moved.anchor_used > plain.anchor_used).all()
    far = pd.DataFrame({"ticker": ["RAMP"], "as_of_date": [DATES[0] - pd.Timedelta(days=90)]})
    assert len(analysis.segment_returns(far, {"s": (0, 30)})) == 0


def test_segment_returns_names_a_bare_pair_after_its_offsets(bundle_root):
    ev = pd.DataFrame({"ticker": ["RAMP"], "as_of_date": [DATES[100]]})
    out = analysis.segment_returns(ev, [(0, 30), (-30, 0)])
    assert {"s_0_30", "s_-30_0"} <= set(out.columns)


def test_market_adjust_by_subtracts_the_cohort_median():
    f = pd.DataFrame({"year": [2020, 2020, 2020, 2021, 2021, 2021],
                      "r_1": [1.0, 2.0, 6.0, 10.0, 20.0, 60.0]})
    adj = analysis.market_adjust_by(f, ["r_1"], by="year")
    assert adj.r_1.tolist() == [-1.0, 0.0, 4.0, -10.0, 0.0, 40.0]
    assert list(adj.columns) == ["r_1"] and adj.index.equals(f.index)


# ---- variance attribution ---------------------------------------------------
def _orthogonal_blocks(n: int = 40):
    a = np.tile([1.0, 1.0, -1.0, -1.0], n // 4)
    b = np.tile([1.0, -1.0, 1.0, -1.0], n // 4)
    return 2 * a + b, {"A": a.reshape(-1, 1), "B": b.reshape(-1, 1)}


def test_r2_lattice_covers_every_subset():
    y, blocks = _orthogonal_blocks()
    lat = analysis.r2_lattice(y, blocks)
    assert set(lat) == {frozenset(), frozenset({"A"}), frozenset({"B"}), frozenset({"A", "B"})}
    assert lat[frozenset({"A"})] == pytest.approx(0.8)
    assert lat[frozenset({"B"})] == pytest.approx(0.2)
    assert lat[frozenset({"A", "B"})] == pytest.approx(1.0)


def test_r2_lattice_refuses_a_lattice_that_would_not_finish():
    y, _ = _orthogonal_blocks()
    many = {str(i): np.zeros((len(y), 1)) for i in range(13)}
    with pytest.raises(ValueError, match="max_blocks"):
        analysis.r2_lattice(y, many)


def test_shapley_values_sum_to_the_full_model_and_bracket_every_ordering():
    y, blocks = _orthogonal_blocks()
    lat = analysis.r2_lattice(y, blocks)
    t = analysis.shapley(lat, order=["A", "B"])
    assert t.shapley.sum() == pytest.approx(lat[frozenset({"A", "B"})])
    assert t.loc["A", "shapley"] == pytest.approx(0.8)
    assert (t.min_incr <= t.shapley + 1e-12).all() and (t.shapley <= t.max_incr + 1e-12).all()
    # First on the ladder, a block is credited with everything it explains alone.
    assert t.loc["A", "order_incr"] == pytest.approx(t.loc["A", "alone"])


# ---- fiscal dating ----------------------------------------------------------
def _history_docs():
    """Two synthetic /history responses, the second a later vintage of one year."""
    return [
        {"cikNumber": 11, "years": [{"fiscalYear": 2020, "periodEnd": "2020-12-31"},
                                    {"fiscalYear": 2019, "periodEnd": "2019-12-31"}]},
        {"cikNumber": 22, "years": [{"fiscalYear": 2020, "periodEnd": "2021-01-30"}]},
        {"__distill_error__": {"status": 404}},
    ]


def test_fiscal_periods_dates_each_filed_year():
    h = analysis.fiscal_periods(_history_docs())
    assert len(h) == 3
    row = h[(h.cik == 22) & (h.fiscal_year == 2020)].iloc[0]
    # A January year end labelled 2020 sits one calendar year later than its label.
    assert row.year_offset == -1 and row.month_day == "01-30"


def test_overlap_years_is_one_when_the_window_is_the_filed_year():
    pe = np.array(["2020-12-31"], dtype="datetime64[ns]")
    same = analysis.overlap_years(pe, np.array(["2020-01-01"], dtype="datetime64[ns]"),
                                  np.array(["2020-12-31"], dtype="datetime64[ns]"))
    after = analysis.overlap_years(pe, np.array(["2021-01-01"], dtype="datetime64[ns]"),
                                   np.array(["2021-12-31"], dtype="datetime64[ns]"))
    half = analysis.overlap_years(pe, np.array(["2020-07-01"], dtype="datetime64[ns]"),
                                  np.array(["2021-06-30"], dtype="datetime64[ns]"))
    assert same[0] == pytest.approx(1.0, abs=0.01)
    assert after[0] == 0.0
    assert half[0] == pytest.approx(0.5, abs=0.02)


# ---- revisions --------------------------------------------------------------
def test_revision_filings_counts_filings_and_not_facts():
    rows = [
        {"ticker": "AAA", "changedAccession": "acc-1", "changedFiled": "2021-03-01",
         "relDelta": -0.30, "conceptGroup": "revenue"},
        {"ticker": "AAA", "changedAccession": "acc-1", "changedFiled": "2021-03-01",
         "relDelta": 0.05, "conceptGroup": "assets"},
        {"ticker": "AAA", "changedAccession": "acc-2", "changedFiled": "2022-03-01",
         "relDelta": 0.40, "conceptGroup": "revenue"},
        {"ticker": "BBB", "changedAccession": "acc-1", "changedFiled": "2021-03-01",
         "relDelta": 0.01, "conceptGroup": "revenue"},
    ]
    out = analysis.revision_filings(rows)
    assert len(out) == 3                                  # four facts, three filings
    one = out[(out.ticker == "AAA") & (out.filing_key == "acc-1")].iloc[0]
    assert one.n_facts == 2
    assert one.relDelta == pytest.approx(-0.30)           # the largest move represents it
    assert bool(one.any_down) and not bool(one.any_up)
    assert out[out.ticker == "BBB"].any_down.tolist() == [False]


def test_revision_filings_falls_back_to_the_filed_date_without_an_accession():
    rows = [{"ticker": "AAA", "changedAccession": None, "changedFiled": "2021-03-01",
             "relDelta": -0.5}]
    assert analysis.revision_filings(rows).filing_key.tolist() == ["2021-03-01"]


# ---- multiplicity -----------------------------------------------------------
def test_family_chance_counts_what_the_grid_gives_away():
    cells = {"clears": (1.0, np.zeros(100)), "does not": (0.0, np.zeros(100))}
    out = analysis.family_chance(cells)
    assert out["n_cells"] == 2 and out["observed_clear"] == 1
    # Every synthetic family is built from a null value of zero, which clears nothing.
    assert out["expected"] == 0.0 and out["p_any"] == 0.0
    assert out["p_at_least_observed"] == 0.0


def test_family_chance_requires_every_null_when_a_cell_carries_several():
    both = {"cell": (1.0, {"a": np.zeros(50), "b": np.full(50, 5.0)})}
    one = {"cell": (1.0, {"a": np.zeros(50)})}
    assert analysis.family_chance(both)["observed_clear"] == 0
    assert analysis.family_chance(one)["observed_clear"] == 1


# ---- forward_paths, rewritten --------------------------------------------
def _row_wise_forward_paths(dec, horizons=6, keep=()):
    """The reindex-per-row implementation this module replaced, kept here so the
    rewrite is checked against the thing it has to reproduce and not against
    itself."""
    idx = stooq.index()
    dec = dec[dec.ticker.map(lambda t: stooq.stooq_key(t) in idx)]
    rows = []
    for t, g in dec.groupby("ticker"):
        c = stooq.closes(t)
        if c is None or len(c) < 30:
            continue
        last = c.index[-1]
        for r in g.itertuples():
            before = c.index[c.index <= r.as_of_date]
            if before.empty or (r.as_of_date - before.max()).days > 14:
                continue
            grid = pd.DatetimeIndex(
                [r.as_of_date + pd.DateOffset(months=k) for k in range(horizons + 1)])
            px = c.reindex(c.index.union(grid)).ffill().reindex(grid)
            p0 = px.iloc[0]
            if not p0 or p0 <= 0:
                continue
            path = (px / p0 - 1).to_numpy(copy=True)
            path[[i for i, d in enumerate(grid)
                  if d > last + pd.Timedelta(days=45)]] = np.nan
            row = {"cik": r.cik, "ticker": t, "year": r.year, "as_of_date": r.as_of_date,
                   "delisted_in_window": bool(last < grid[-1])}
            row.update({k: getattr(r, k) for k in keep})
            row.update({f"r_{k}": path[k] for k in range(1, horizons + 1)})
            rows.append(row)
    out = pd.DataFrame(rows)
    for k in range(1, horizons + 1):
        out[f"x_{k}"] = out[f"r_{k}"] - out.groupby("year")[f"r_{k}"].transform("median")
    return out


def _dec_frame() -> pd.DataFrame:
    """Snapshots on two priced tickers, one uncovered ticker and one stale anchor."""
    rows = []
    for ticker in ("RAMP", "SINK", "NOSUCH"):
        for i in (30, 90, 150, 210, 270):
            rows.append({"cik": hash(ticker) % 1000, "ticker": ticker,
                         "as_of_date": DATES[i], "year": int(DATES[i].year),
                         "revenue": float(i)})
    rows.append({"cik": 7, "ticker": "RAMP",
                 "as_of_date": DATES[0] - pd.Timedelta(days=60),
                 "year": 2020, "revenue": 1.0})
    return pd.DataFrame(rows)


def test_forward_paths_matches_the_implementation_it_replaced(bundle_root):
    dec = _dec_frame()
    old = _row_wise_forward_paths(dec, horizons=6, keep=("revenue",))
    new = analysis.forward_paths(dec, horizons=6, keep=("revenue",))
    pd.testing.assert_frame_equal(old, new, check_exact=True)
    assert len(new) == 10                                  # the stale anchor is dropped


def test_revision_filings_works_on_rows_with_no_accession_field_at_all():
    rows = [{"ticker": "AAA", "changedFiled": "2021-03-01", "relDelta": -0.5},
            {"ticker": "AAA", "changedFiled": "2021-03-01", "relDelta": -0.2}]
    out = analysis.revision_filings(rows)
    assert len(out) == 1 and out.n_facts.iloc[0] == 2


def test_fiscal_periods_reads_a_directory_of_cached_responses(tmp_path):
    import json
    (tmp_path / "api_v1_sec_fundamentals_AAA_history.abc.json").write_text(
        json.dumps(_history_docs()[0]))
    (tmp_path / "api_v1_sec_revisions_AAA.abc.json").write_text(json.dumps({"revisions": []}))
    h = analysis.fiscal_periods(tmp_path)
    assert sorted(h.fiscal_year) == [2019, 2020] and set(h.cik) == {11}
