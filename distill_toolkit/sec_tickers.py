"""Reader for the SEC's ``company_tickers.json`` file that you have downloaded
yourself.

This module contains no downloader and never contacts sec.gov. It reads a file
that is already on your disk. Obtaining it, and identifying yourself in the
User-Agent the way the SEC asks, is your act. See NOTICE and
docs/data-sources.md, which carries the one-line fetch.

Expected layout: the file exactly as the SEC serves it, a JSON object whose
values are ``{"cik_str": int, "ticker": str, "title": str}``::

    {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, ...}

Root resolution: an explicit ``path`` argument, else ``SEC_TICKERS`` from the
environment, else ``<DISTILL_CACHE_DIR>/sec/company_tickers.json``.

**The key.** Every row carries both a CIK and a ticker. The CIK is the stable
key and is what a join should use; the ticker is reused, so a ticker join to
this file answers "who holds that symbol today", which is a different question
from "who held it then". On one measured panel, 266 of 3,104 delisted filers
had their last ticker present in this file and **none** of the 266 pointed at
the filer that used to hold it (research/naming-the-dead).

**What the file is.** A list of CURRENT registrants with a current ticker: one
row per (company, symbol), so a multi-class issuer appears more than once. It
is a snapshot with no date on any row and no history behind it. A company whose
listing has ended leaves the file, and nothing marks that it was ever in it, so
the file cannot name a company that has died. There is no ``asof`` here for
that reason: the only date the file has is when you downloaded it, which
``vintage`` reads off the file's mtime.

The file is a US federal government work and is in the public domain.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from .client import CACHE_DIR

Record = dict[str, object]

_index_cache: dict[Path, dict[int, Record]] = {}


def default_path() -> Path:
    env = os.environ.get("SEC_TICKERS")
    return Path(env).expanduser().resolve() if env else CACHE_DIR / "sec" / "company_tickers.json"


def _resolve(path: str | Path | None) -> Path:
    return Path(path).expanduser().resolve() if path else default_path()


def index(path: str | Path | None = None) -> dict[int, Record]:
    """``{cik: {"cik": int, "name": str, "tickers": [str, ...]}}``. One read, then cached.

    Keyed on the CIK, because that is the key that survives a rename, a
    reincorporation and a symbol change. A CIK with several share classes
    carries them all in ``tickers``, in the order the file lists them.
    """
    p = _resolve(path)
    if p not in _index_cache:
        raw = json.loads(p.read_text())
        rows = raw.values() if isinstance(raw, dict) else raw
        out: dict[int, Record] = {}
        for r in rows:
            cik = int(r["cik_str"])
            rec = out.setdefault(cik, {"cik": cik, "name": r["title"], "tickers": []})
            t = str(r["ticker"]).upper()
            if t not in rec["tickers"]:
                rec["tickers"].append(t)
        _index_cache[p] = out
    return _index_cache[p]


def ticker_index(path: str | Path | None = None) -> dict[str, list[Record]]:
    """``{TICKER: [record, ...]}`` over the same file.

    A list, not a record: the same symbol can appear against more than one CIK.
    """
    out: dict[str, list[Record]] = {}
    for rec in index(path).values():
        for t in rec["tickers"]:
            out.setdefault(t, []).append(rec)
    return out


def by_cik(cik, path: str | Path | None = None) -> Record | None:
    """The record for a CIK, or ``None`` when the file does not carry it.

    ``None`` means absent from the current registrant list, which for a filer
    whose listing has ended is the normal answer, not an error.
    """
    try:
        key = int(str(cik).lstrip("0") or 0)
    except (TypeError, ValueError):
        return None
    return index(path).get(key)


def name(cik, path: str | Path | None = None) -> str | None:
    """The company name for a CIK, or ``None`` when the file cannot name it."""
    rec = by_cik(cik, path)
    return None if rec is None else str(rec["name"])


def by_ticker(ticker: str, path: str | Path | None = None) -> list[Record]:
    """Every record holding a symbol today. Empty when no one does.

    Read this as "who holds the symbol in this file's vintage". It is not
    evidence about who held it on any earlier date, and for a symbol freed by a
    delisting it is routinely a different company: see the module docstring.
    """
    return list(ticker_index(path).get(str(ticker).upper(), []))


def vintage(path: str | Path | None = None) -> date:
    """The file's modification date, which is the only date the file has.

    No row carries one. A study quoting a coverage rate off this file states
    this date, because the file's contents move whenever a listing starts or
    ends.
    """
    return date.fromtimestamp(_resolve(path).stat().st_mtime)
