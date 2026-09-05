"""Regression tests for the two resampling nulls in distill_toolkit.analysis.
Every frame here is synthetic: invented firms, years and labels with a known
answer, not records from any data source."""

import numpy as np
import pandas as pd
import pytest

from distill_toolkit import analysis


def _quarterly(n_firms: int = 8, years=(2019, 2020, 2021), seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for cik in range(n_firms):
        for y in years:
            for q in range(4):
                rows.append({"cik": cik, "year": y, "q": q, "label": rng.integers(0, 2)})
    return pd.DataFrame(rows)


def test_clustered_shuffle_within_keeps_every_row_of_the_partner_cell():
    # A quarterly frame has four rows per (firm, year). The shuffled series
    # must carry the partner's four labels, not one of them repeated four
    # times: a constant cell is a different, weaker null.
    df = _quarterly()
    out = analysis.clustered_shuffle(df["label"], df["cik"], within=df["year"], seed=3)
    assert out.notna().all()
    observed_const = df.groupby(["cik", "year"])["label"].nunique().eq(1).mean()
    shuffled_const = out.groupby([df["cik"], df["year"]]).nunique().eq(1).mean()
    assert shuffled_const == pytest.approx(observed_const)
    # The multiset of labels inside each year is preserved.
    for y, g in df.groupby("year"):
        assert sorted(out[g.index]) == sorted(g["label"])


def test_clustered_shuffle_within_drops_no_row_on_an_unbalanced_panel():
    # Firms of different lifespans: a partner may lack the key entirely. The
    # row must still get a label from the same year, never NaN, so a rate
    # computed over the shuffled series keeps its denominator.
    df = _quarterly(n_firms=6)
    df = df[~((df["cik"] < 3) & (df["year"] == 2021))].reset_index(drop=True)
    out = analysis.clustered_shuffle(df["label"], df["cik"], within=df["year"], seed=1)
    assert len(out) == len(df)
    assert out.notna().all()


def test_clustered_shuffle_without_within_is_unchanged():
    df = _quarterly(n_firms=4, years=(2020,))
    out = analysis.clustered_shuffle(df["label"], df["cik"], seed=0)
    assert len(out) == len(df) and out.notna().all()
    assert sorted(out) == sorted(df["label"])


def test_cluster_boot_diff_flags_a_tied_median():
    # 80% zeros on both sides: the medians tie at zero in every replicate and
    # the interval collapses to [0, 0] although the means differ. The helper
    # must say so rather than return a precise-looking null.
    rng = np.random.default_rng(0)
    a = pd.DataFrame({"cik": np.repeat(range(20), 5), "v": np.where(rng.random(100) < 0.8, 0.0, -2.0)})
    b = pd.DataFrame({"cik": np.repeat(range(20, 40), 5), "v": np.where(rng.random(100) < 0.8, 0.0, 1.0)})
    with pytest.warns(RuntimeWarning, match="tied statistic"):
        obs, lo, hi, _ = analysis.cluster_boot_diff(a, b, "v", draws=100)
    assert obs == 0.0 and lo == 0.0 and hi == 0.0


def test_cluster_boot_diff_is_silent_on_a_real_difference():
    rng = np.random.default_rng(1)
    a = pd.DataFrame({"cik": np.repeat(range(20), 5), "v": rng.normal(1.0, 0.1, 100)})
    b = pd.DataFrame({"cik": np.repeat(range(20, 40), 5), "v": rng.normal(0.0, 0.1, 100)})
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        obs, lo, hi, _ = analysis.cluster_boot_diff(a, b, "v", draws=100)
    assert lo > 0.5 and obs == pytest.approx(1.0, abs=0.1)


def test_clustered_shuffle_within_keeps_the_partner_path_whole_on_an_unbalanced_panel():
    # A label that is constant within each firm (a firm type) must stay
    # constant within each firm after the shuffle, including on the rows
    # whose partner has no cell at that key. Drawing those rows from other
    # firms would give the null less persistence than the data has.
    df = _quarterly(n_firms=8, years=(2018, 2019, 2020, 2021))
    df = df[~((df["cik"] < 4) & (df["year"] > 2019))].reset_index(drop=True)
    df["label"] = df["cik"] % 3
    with pytest.warns(RuntimeWarning, match="nearest key"):
        out = analysis.clustered_shuffle(df["label"], df["cik"], within=df["year"], seed=2)
    assert out.notna().all()
    assert (out.groupby(df["cik"]).nunique() == 1).all()


def test_clustered_shuffle_within_accepts_string_keys():
    # A month key such as "2024-03" must work: nearest is measured along the
    # sorted key list, not by subtracting keys.
    df = pd.DataFrame({
        "cik": [1, 1, 1, 2, 2, 3, 3, 3, 4, 4],
        "m": ["2024-01", "2024-02", "2024-03", "2024-01", "2024-03",
              "2024-02", "2024-03", "2024-04", "2024-02", "2024-04"],
        "label": [1, 1, 1, 0, 0, 1, 1, 1, 0, 0],
    })
    with pytest.warns(RuntimeWarning, match="nearest key"):
        out = analysis.clustered_shuffle(df["label"], df["cik"], within=df["m"], seed=5)
    assert out.notna().all()
    assert (out.groupby(df["cik"]).nunique() == 1).all()
