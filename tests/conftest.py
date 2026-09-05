"""Shared fixtures. Every price and every share count in the test suite is
synthetic: invented numbers in the shape of the real files, chosen to make the
arithmetic checkable by hand. No record from any data source appears here."""

import pandas as pd
import pytest

from distill_toolkit import stooq

HEADER = "<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>\n"

# Business days from a Monday, long enough for a 24-month path and a 60-day window.
DATES = pd.bdate_range("2021-01-04", periods=420)

# FLAT stands in for the benchmark: a constant benchmark makes an abnormal
# return equal to the raw one, so an expected value can be written down.
SERIES = {
    "SPY": [100.0] * len(DATES),
    "RAMP": [100.0 + i for i in range(len(DATES))],
    "SINK": [100.0 * (0.99 ** i) for i in range(len(DATES))],
    "TINY": [50.0, 51.0, 52.0],  # too short to price anything
}


def _write(root, ticker, closes):
    path = root / "data" / "daily" / "us" / "nasdaq stocks" / "1"
    path.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        f"{ticker}.US,D,{d:%Y%m%d},000000,{c},{c},{c},{c},1000,0\n"
        for d, c in zip(DATES, closes)
    )
    (path / f"{ticker.lower()}.us.txt").write_text(HEADER + rows)


@pytest.fixture
def bundle_root(tmp_path, monkeypatch):
    """A synthetic Stooq bundle on disk, wired in as the default root."""
    root = tmp_path / "stooq"
    for ticker, closes in SERIES.items():
        _write(root, ticker, closes)
    monkeypatch.setenv("STOOQ_DIR", str(root))
    stooq._index_cache.clear()
    stooq._bars_cache.clear()
    yield root
    stooq._index_cache.clear()
    stooq._bars_cache.clear()
