"""Tests for distill_toolkit.joins. All inputs are synthetic: made-up numbers
chosen to exercise the arithmetic, not records from any data source."""

import numpy as np
import pandas as pd
import pytest

from distill_toolkit import joins


def test_split_basis_flags_detects_forward_split():
    shares = {2021: 100.0, 2022: 102.0, 2023: 510.0, 2024: 515.0}
    flags = joins.split_basis_flags(shares)
    assert flags == [(2023, pytest.approx(5.0), 5.0)]


def test_split_basis_flags_detects_reverse_split():
    shares = {2021: 1000.0, 2022: 101.0, 2023: 100.0}
    flags = joins.split_basis_flags(shares)
    assert len(flags) == 1
    assert flags[0][0] == 2022
    assert flags[0][2] == pytest.approx(0.1)


def test_split_basis_flags_ignores_organic_change_and_gaps():
    shares = {2020: 100.0, 2021: 104.0, 2023: 150.0}  # +4%, then a gap year
    assert joins.split_basis_flags(shares) == []


def test_rebase_shares_applies_factor_to_earlier_years_only():
    shares = {2021: 100.0, 2022: 102.0, 2023: 510.0}
    flags = joins.split_basis_flags(shares)
    rebased = joins.rebase_shares(shares, flags)
    assert rebased == {2021: 500.0, 2022: 510.0, 2023: 510.0}


def test_decompose_identity():
    d = joins.decompose(p0=10.0, p1=30.0, rev0=200.0, rev1=400.0, sh0=20.0, sh1=20.0)
    assert d["ret"] == pytest.approx(3.0)
    assert d["rps"] == pytest.approx(2.0)
    assert d["mult"] == pytest.approx(1.5)
    assert d["ret"] == pytest.approx(d["rps"] * d["mult"])


def _closes(start: str, n: int, step: float = 1.0) -> pd.Series:
    idx = pd.bdate_range(start, periods=n)
    return pd.Series([100.0 + i * step for i in range(n)], index=idx)


def test_forward_return_basic():
    c = _closes("2020-01-01", 400)
    r = joins.forward_return(c, pd.Timestamp("2020-03-02"), 365)
    assert r is not None and r > 0


def test_forward_return_rejects_stale_entry():
    c = _closes("2020-01-01", 20)  # series ends late January
    assert joins.forward_return(c, pd.Timestamp("2020-06-01"), 30) is None


def test_forward_return_rejects_short_exit():
    c = _closes("2020-01-01", 60)  # ends ~March; horizon a year out is far past the end
    assert joins.forward_return(c, pd.Timestamp("2020-02-03"), 365) is None


def test_forward_return_is_none_when_the_series_ends_at_entry():
    # The last close sits inside both the entry staleness window and the exit
    # gap window, so both guards pass and the exit print IS the entry print.
    # Nothing was observed over the horizon; a 0.0 here would be a manufactured
    # flat return contributed by exactly the names that stopped trading.
    c = _closes("2020-01-01", 20)
    start = c.index[-1]
    assert joins.forward_return(c, start, 30, max_exit_gap_days=45) is None


def test_market_adjust_subtracts_group_median():
    df = pd.DataFrame({"year": [1, 1, 1, 2, 2], "r": [0.1, 0.2, 0.3, 0.0, 0.4]})
    adj = joins.market_adjust(df, "r")
    assert adj.tolist() == pytest.approx([-0.1, 0.0, 0.1, -0.2, 0.2])


def _history_years(rows):
    """A /history ``years`` list: (fiscalYear, sharesOutstanding) pairs, invented."""
    return [{"fiscalYear": y, "sharesOutstanding": so} for y, so in rows]


def test_corroborate_flags_confirms_a_split_the_outstanding_series_also_shows():
    # Diluted steps x5 at FY2023; the never-restated count steps x5 two years later.
    years = _history_years([(2021, 100.0), (2022, 100.0), (2023, 101.0), (2025, 500.0)])
    flags = [(2023, 5.05, 5.0)]
    v = joins.corroborate_flags(years, flags)[0]
    assert v["verdict"] == "corroborated" and v["corroborated"]
    assert v["shares_outstanding_step_year"] == 2025


def test_corroborate_flags_contradicts_an_issuance_that_only_looks_like_a_split():
    # The count steps in the diluted series and never steps again: a real issuance.
    years = _history_years([(2022, 100.0), (2023, 500.0), (2024, 505.0), (2025, 510.0)])
    v = joins.corroborate_flags(years, [(2023, 5.0, 5.0)])[0]
    assert v["verdict"] == "contradicted" and not v["corroborated"]


def test_corroborate_flags_says_untestable_rather_than_false():
    years = _history_years([(2023, 100.0)])  # nothing after the flag year to test against
    v = joins.corroborate_flags(years, [(2023, 5.0, 5.0)])[0]
    assert v["verdict"] == "untestable" and not v["corroborated"]
    assert v["shares_outstanding_step"] is None


def test_rebase_shares_takes_only_the_corroborated_flags():
    shares = {2022: 100.0, 2023: 500.0, 2024: 505.0}
    flags = joins.split_basis_flags(shares)
    years = _history_years([(2022, 100.0), (2023, 500.0), (2024, 505.0)])
    verdicts = joins.corroborate_flags(years, flags)
    applied = [f for f, v in zip(flags, verdicts) if v["corroborated"]]
    assert flags and not applied  # the flag fires, the corroboration rejects it
    assert joins.rebase_shares(shares, applied) == shares


def test_share_series_sanity_flags_a_count_served_in_the_wrong_unit():
    outstanding = {2018: 157_200_000.0, 2019: 156_800_000.0, 2020: 155_000_000.0}
    diluted = {2018: 157_000_000.0, 2019: 156.0, 2020: 154.0}  # 2019-20 served in millions
    bad = joins.share_series_sanity(outstanding, diluted)
    assert [r["fiscal_year"] for r in bad] == [2019, 2020]
    assert bad[0]["ratio"] > 1e5


def test_share_series_sanity_passes_a_normal_corporate_action():
    outstanding = {2021: 100.0, 2022: 130.0}
    diluted = {2021: 98.0, 2022: 115.0}
    assert joins.share_series_sanity(outstanding, diluted) == []


def test_share_series_sanity_separates_a_split_basis_gap_from_a_unit_defect():
    # A 4:1 split: the restated diluted series is on the new basis, the
    # never-restated outstanding count is still on the old one.
    split = joins.share_series_sanity({2020: 100.0}, {2020: 400.0})
    assert [round(r["ratio"], 2) for r in split] == [0.25]
    # A count served in millions is off by six orders of magnitude, not by four.
    unit = joins.share_series_sanity({2020: 150_000_000.0}, {2020: 150.0})
    assert unit[0]["ratio"] > 1e5


def test_corroborate_flags_treats_a_nan_share_count_as_absent():
    # A NaN count is truthy in Python. It must not become the baseline, and
    # a window with only NaN counts is untestable, not corroborated.
    years = _history_years([(2022, float("nan")), (2023, float("nan")), (2025, float("nan"))])
    v = joins.corroborate_flags(years, [(2023, 5.0, 5.0)])[0]
    assert v["verdict"] == "untestable" and not v["corroborated"]


# ---- split-basis inference and market capitalisation -----------------------
def test_snap_rounds_an_estimate_to_a_declared_ratio_and_leaves_the_rest_alone():
    assert joins.snap(3.94) == (4.0, True)
    assert joins.snap(0.24) == (0.25, True)
    factor, snapped = joins.snap(2.7)
    assert not snapped and factor == 2.7


# A four-for-one split at fiscal 2020. The diluted count is restated two years
# back and the outstanding count is never restated, so their ratio sits at 1/4
# for 2018 and 2019 and at 1 everywhere else.
SO = {2017: 100.0, 2018: 100.0, 2019: 100.0, 2020: 400.0, 2021: 400.0}
WASD = {2017: 100.0, 2018: 400.0, 2019: 400.0, 2020: 400.0, 2021: 400.0}


def test_firm_basis_reads_a_split_out_of_the_two_share_series():
    splits, unresolved, testable = joins.firm_basis(SO, WASD)
    assert unresolved == [] and testable == set(SO)
    assert len(splits) == 1
    assert splits[0]["split_year"] == 2020
    assert splits[0]["factor"] == 4.0 and splits[0]["snapped"]
    assert splits[0]["run_len"] == 2


def test_firm_basis_leaves_an_unrepairable_run_unresolved():
    # Three flagged years is longer than the two-year restatement window, so the
    # fingerprint is real and the split it implies is not.
    wasd = {**WASD, 2017: 400.0}
    splits, unresolved, _ = joins.firm_basis(SO, wasd)
    assert splits == [] and unresolved == [2017, 2018, 2019]


def test_firm_basis_does_not_call_an_issuance_a_split():
    # The count quadruples and stays there with both series on one basis: no
    # ratio leaves [lo, hi], so there is nothing to resolve either way.
    so = {2018: 100.0, 2019: 100.0, 2020: 400.0, 2021: 400.0}
    splits, unresolved, _ = joins.firm_basis(so, dict(so))
    assert splits == [] and unresolved == []


def test_firm_basis_falls_back_to_the_implied_count():
    wasd = {y: v for y, v in WASD.items() if y != 2018}
    splits, unresolved, _ = joins.firm_basis(SO, wasd, implied_by_year={2018: 400.0})
    assert unresolved == [] and splits[0]["factor"] == 4.0


def test_rebase_puts_every_year_on_the_latest_basis():
    splits, _, _ = joins.firm_basis(SO, WASD)
    out = joins.rebase(SO, splits)
    assert out == {2017: 400.0, 2018: 400.0, 2019: 400.0, 2020: 400.0, 2021: 400.0}


def test_market_cap_multiplies_and_refuses_a_period_that_has_not_ended():
    assert joins.market_cap(1000.0, 10.0) == 10000.0
    ok = joins.market_cap([1000.0, 1000.0], [10.0, 10.0],
                          period_end=np.array(["2020-12-31", "2021-06-30"],
                                              dtype="datetime64[ns]"),
                          as_of=np.array(["2021-03-31", "2021-03-31"],
                                         dtype="datetime64[ns]"))
    # The second row's fiscal year had not ended when the close was taken.
    assert ok[0] == 10000.0 and np.isnan(ok[1])


def test_market_cap_is_nan_rather_than_zero_or_negative():
    assert np.isnan(joins.market_cap(0.0, 10.0))
    assert np.isnan(joins.market_cap(1000.0, -1.0))


def test_market_cap_on_a_rebased_count_differs_from_the_raw_one():
    splits, _, _ = joins.firm_basis(SO, WASD)
    rebased = joins.rebase(SO, splits)
    close = 25.0
    assert joins.market_cap(rebased[2018], close) == pytest.approx(
        4 * joins.market_cap(SO[2018], close))
