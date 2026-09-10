"""Tests for distill_toolkit.sec_tickers against a synthetic file written into a
temp directory. Every CIK, symbol and company name below is invented; no SEC
record appears here."""

import json

import pytest

from distill_toolkit import sec_tickers

# Invented registrants. CIK 111 has two share classes, CIK 222 holds a symbol
# that CIK 333 also carries, and CIK 999 is deliberately absent from the file:
# it is the shape of a company whose listing has ended.
SYNTHETIC = {
    "0": {"cik_str": 111, "ticker": "AAAA", "title": "Invented Alpha Corp"},
    "1": {"cik_str": 111, "ticker": "AAAB", "title": "Invented Alpha Corp"},
    "2": {"cik_str": 222, "ticker": "BBBB", "title": "Invented Beta Inc"},
    "3": {"cik_str": 333, "ticker": "BBBB", "title": "Invented Beta Therapeutics"},
}


@pytest.fixture
def ticker_file(tmp_path):
    p = tmp_path / "company_tickers.json"
    p.write_text(json.dumps(SYNTHETIC))
    return p


def test_index_is_keyed_on_cik_and_collects_classes(ticker_file):
    idx = sec_tickers.index(ticker_file)
    assert set(idx) == {111, 222, 333}
    assert idx[111]["tickers"] == ["AAAA", "AAAB"]
    assert idx[111]["name"] == "Invented Alpha Corp"


def test_absent_cik_is_none_not_empty(ticker_file):
    assert sec_tickers.by_cik(999, ticker_file) is None
    assert sec_tickers.name(999, ticker_file) is None
    assert sec_tickers.by_ticker("ZZZZ", ticker_file) == []


def test_a_zero_padded_cik_resolves(ticker_file):
    assert sec_tickers.name("0000000111", ticker_file) == "Invented Alpha Corp"
    assert sec_tickers.by_cik("0000000999", ticker_file) is None


def test_a_shared_symbol_returns_every_holder(ticker_file):
    holders = sec_tickers.by_ticker("bbbb", ticker_file)
    assert sorted(h["cik"] for h in holders) == [222, 333]


def test_vintage_is_the_files_own_date(ticker_file):
    import datetime

    assert sec_tickers.vintage(ticker_file) <= datetime.date.today()
