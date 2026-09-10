"""Tests for distill_toolkit.stooq against a synthetic bundle written into a
temp directory. The prices are invented; no Stooq record appears here."""

import zipfile

import pandas as pd
import pytest

from distill_toolkit import stooq

from conftest import DATES

HEADER = "<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>\n"


def _row(ticker: str, date: str, close: float, vol: int = 1000) -> str:
    return f"{ticker}.US,D,{date},000000,{close},{close},{close},{close},{vol},0\n"


@pytest.fixture
def bundle(tmp_path):
    """A synthetic bundle in Stooq's directory layout, zipped like the real one."""
    src = tmp_path / "src" / "data" / "daily" / "us" / "nasdaq stocks" / "1"
    src.mkdir(parents=True)
    # Friday 2024-01-05, Monday 2024-01-08, then a 2:1 split-shaped step on the 9th.
    (src / "fake.us.txt").write_text(
        HEADER
        + _row("FAKE", "20240105", 100.0)
        + _row("FAKE", "20240108", 101.0)
        + _row("FAKE", "20240109", 50.0)
        + _row("FAKE", "20240110", 51.0)
    )
    (src / "brk-b.us.txt").write_text(HEADER + _row("BRK-B", "20240105", 10.0))
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for p in src.rglob("*"):
            z.write(p, p.relative_to(tmp_path / "src"))
    return zip_path


def test_extract_and_index(bundle, tmp_path):
    root = stooq.extract_bundle(bundle, tmp_path / "out")
    assert set(stooq.index(root)) == {"FAKE", "BRK-B"}


def test_px_uses_last_close_on_or_before(bundle, tmp_path):
    root = stooq.extract_bundle(bundle, tmp_path / "out")
    assert stooq.px("FAKE", "2024-01-07", root=root) == 100.0  # Sunday -> Friday's close
    assert stooq.px("FAKE", "2024-01-08", root=root) == 101.0
    assert stooq.px("FAKE", "2023-12-31", root=root) is None
    assert stooq.px("NOPE", "2024-01-08", root=root) is None


def test_stooq_key_maps_dot_to_dash(bundle, tmp_path):
    root = stooq.extract_bundle(bundle, tmp_path / "out")
    assert stooq.px("BRK.B", "2024-01-05", root=root) == 10.0


def test_split_scan_flags_the_step(bundle, tmp_path):
    root = stooq.extract_bundle(bundle, tmp_path / "out")
    hits = stooq.split_scan("FAKE", since="20240101", root=root)
    assert [h[0] for h in hits] == ["20240109"]
    assert hits[0][3] == pytest.approx(50.0 / 101.0)


def test_closes_returns_sorted_series(bundle, tmp_path):
    root = stooq.extract_bundle(bundle, tmp_path / "out")
    s = stooq.closes("FAKE", root=root)
    assert s is not None
    assert list(s.values) == [100.0, 101.0, 50.0, 51.0]
    assert s.index.is_monotonic_increasing


# ---- stooq.close_at --------------------------------------------------------
def test_close_at_takes_the_last_close_on_or_before_the_day(bundle_root):
    # RAMP closes at 100 + i on business day i from 2021-01-04.
    assert stooq.close_at("RAMP", DATES[0]) == 100.0
    assert stooq.close_at("RAMP", DATES[4]) == 104.0
    # A Saturday takes Friday's print, which is one day stale and inside the window.
    assert stooq.close_at("RAMP", "2021-01-09") == 104.0


def test_close_at_refuses_a_print_older_than_the_window(bundle_root):
    far = DATES[-1] + pd.Timedelta(days=60)
    assert stooq.close_at("RAMP", far) is None
    assert stooq.close_at("RAMP", far, max_stale_days=90) == 100.0 + len(DATES) - 1
    # A weekend print is one day old, so a zero-day window rejects it.
    assert stooq.close_at("RAMP", "2021-01-09", max_stale_days=0) is None


def test_close_at_is_none_for_an_uncovered_symbol_or_a_day_before_the_series(bundle_root):
    assert stooq.close_at("NOSUCH", DATES[10]) is None
    assert stooq.close_at("RAMP", "2019-01-02") is None


def test_close_at_takes_a_string_a_date_or_a_timestamp(bundle_root):
    same = {stooq.close_at("RAMP", d) for d in
            ("2021-01-08", DATES[4], DATES[4].date(), pd.Timestamp("2021-01-08"))}
    assert same == {104.0}


@pytest.fixture
def bundle_with_a_fund(tmp_path):
    """A bundle where a delisted company's old symbol is now carried by an ETF.

    Stooq ships funds in sibling ``* etfs`` folders. GHOST here stands for a
    company that stopped filing; the symbol is live again as a fund.
    """
    us = tmp_path / "root" / "data" / "daily" / "us"
    eq = us / "nasdaq stocks" / "1"
    fund = us / "nasdaq etfs"
    eq.mkdir(parents=True)
    fund.mkdir(parents=True)
    (eq / "live.us.txt").write_text(HEADER + _row("LIVE", "20240105", 10.0))
    (fund / "ghost.us.txt").write_text(HEADER + _row("GHOST", "20240105", 99.0))
    return us.parents[2]


def test_index_excludes_funds_by_default(bundle_with_a_fund):
    root = bundle_with_a_fund
    assert set(stooq.index(root)) == {"LIVE"}
    assert set(stooq.index(root, include_etfs=True)) == {"LIVE", "GHOST"}


def test_a_reused_symbol_reads_as_absent_rather_than_as_the_fund(bundle_with_a_fund):
    """The correction this guards: a dead issuer must not quote a successor fund."""
    root = bundle_with_a_fund
    assert stooq.bars("GHOST", root) is None
    assert stooq.px("GHOST", "2024-01-05", root) is None
    assert stooq.closes("GHOST", root) is None
    # Opting in still reaches the fund, and equities are unaffected either way.
    assert stooq.bars("GHOST", root, include_etfs=True) == [("20240105", 99.0, 1000)]
    assert stooq.bars("LIVE", root) == [("20240105", 10.0, 1000)]


def test_the_two_index_variants_do_not_share_a_cache_entry(bundle_with_a_fund):
    root = bundle_with_a_fund
    assert stooq.index(root, include_etfs=True) is not stooq.index(root)
    assert len(stooq.index(root, include_etfs=True)) == len(stooq.index(root)) + 1
