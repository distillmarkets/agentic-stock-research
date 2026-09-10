"""Readers for Stooq end-of-day files that you have downloaded yourself.

This module contains no downloader and never contacts stooq.com. It reads a
bundle or directory that is already on your disk. Readers here cover equities
only by default: Stooq's ``* etfs`` folders are excluded unless you ask for them,
because funds inherit the symbols of companies that have delisted. Obtaining the files, and
complying with Stooq's terms and those of its upstream vendors, is your
responsibility. See NOTICE and docs/data-sources.md.

Expected layout, as Stooq ships its daily US bundle::

    <root>/data/daily/us/{nasdaq,nyse,nysemkt} {stocks,etfs}/{1,2,3}/<ticker>.us.txt

File header: ``<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>``
with dates as ``YYYYMMDD``. Closes are split-adjusted retroactively to the
download date and are not dividend-adjusted, so every return computed from
them is a price return. The file set is current listings only, so delisted
issuers are absent: see docs/traps.md, trap 3.

Root resolution: an explicit ``root`` argument, else ``STOOQ_DIR`` from the
environment, else ``<DISTILL_CACHE_DIR>/stooq_us``.
"""

from __future__ import annotations

import bisect
import os
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from .client import CACHE_DIR

if TYPE_CHECKING:
    import pandas as pd

Bar = tuple[str, float, int]

_index_cache: dict[tuple[Path, bool], dict[str, Path]] = {}
_bars_cache: dict[tuple[Path, str, bool], list[Bar] | None] = {}


def default_root() -> Path:
    env = os.environ.get("STOOQ_DIR")
    return Path(env).expanduser().resolve() if env else CACHE_DIR / "stooq_us"


def _resolve(root: str | Path | None) -> Path:
    return Path(root).expanduser().resolve() if root else default_root()


def stooq_key(ticker: str) -> str:
    """Stooq's file naming for a ticker: ``BRK.B`` is stored as ``BRK-B``."""
    return ticker.replace(".", "-").upper()


def extract_bundle(zip_path: str | Path, dest: str | Path | None = None) -> Path:
    """Unpack a Stooq bundle that is already on disk into ``dest``.

    Only ``.txt`` price files are extracted. Returns the destination root.
    """
    dest_root = _resolve(dest)
    dest_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(Path(zip_path).expanduser()) as z:
        members = [n for n in z.namelist() if n.endswith(".txt")]
        z.extractall(dest_root, members=members)
    _index_cache.pop(dest_root, None)
    return dest_root


def _is_etf(path: Path, root: Path) -> bool:
    """True when a price file sits under one of Stooq's ``* etfs`` folders."""
    try:
        parts = path.relative_to(root).parts[:-1]
    except ValueError:
        parts = path.parts[:-1]
    return any(seg.lower().endswith("etfs") for seg in parts)


def index(root: str | Path | None = None, *, include_etfs: bool = False) -> dict[str, Path]:
    """``{TICKER: path}`` over the ``*.us.txt`` files under the root. One walk, then cached.

    **Equities only by default.** Stooq ships funds in sibling ``* etfs`` folders,
    and a fund routinely carries a symbol that a delisted company used to hold, so
    indexing the whole tree prices dead issuers off a successor ETF. Pass
    ``include_etfs=True`` for the full file set; equity files still win any symbol
    that appears in both.
    """
    r = _resolve(root)
    key = (r, include_etfs)
    if key not in _index_cache:
        m: dict[str, Path] = {}
        paths = sorted(r.rglob("*.us.txt"))
        equities = [p for p in paths if not _is_etf(p, r)]
        funds = [p for p in paths if _is_etf(p, r)] if include_etfs else []
        for p in equities + funds:
            m.setdefault(p.name[: -len(".us.txt")].upper(), p)
        _index_cache[key] = m
    return _index_cache[key]


def bars(
    ticker: str, root: str | Path | None = None, *, include_etfs: bool = False
) -> list[Bar] | None:
    """``[(YYYYMMDD, close, volume)]`` ascending, or ``None`` if the symbol has no file.

    ``None`` means absent from current listings. Delisted issuers are simply not
    in the Stooq file set. Reads the equities-only index unless ``include_etfs``
    is set, so a symbol now carried by a fund reads as absent rather than
    returning the fund's prices.
    """
    r = _resolve(root)
    key = (r, stooq_key(ticker), include_etfs)
    if key in _bars_cache:
        return _bars_cache[key]
    path = index(r, include_etfs=include_etfs).get(key[1])
    if path is None:
        _bars_cache[key] = None
        return None
    out: list[Bar] = []
    with path.open() as f:
        next(f, None)
        for line in f:
            c = line.rstrip("\n").split(",")
            if len(c) < 9:
                continue
            try:
                out.append((c[2], float(c[7]), int(float(c[8]))))
            except ValueError:
                continue
    out.sort(key=lambda b: b[0])
    _bars_cache[key] = out
    return out


def closes(
    ticker: str, root: str | Path | None = None, *, include_etfs: bool = False
) -> "pd.Series | None":
    """Closes as a pandas Series indexed by date, or ``None`` if uncovered."""
    import pandas as pd

    b = bars(ticker, root, include_etfs=include_etfs)
    if not b:
        return None
    s = pd.Series(
        [x[1] for x in b],
        index=pd.to_datetime([x[0] for x in b], format="%Y%m%d", errors="coerce"),
    ).dropna()
    return s.sort_index()


def asof(series: list[Bar], yyyymmdd: str) -> tuple[str, float] | None:
    """Last close on or before ``yyyymmdd``. Returns ``(date, close)`` or ``None``.

    Use this rather than an exact-date lookup: fiscal period ends land on
    weekends and holidays constantly.
    """
    ds = [b[0] for b in series]
    i = bisect.bisect_right(ds, yyyymmdd) - 1
    return (series[i][0], series[i][1]) if i >= 0 else None


def px(
    ticker: str, iso_date: str, root: str | Path | None = None, *, include_etfs: bool = False
) -> float | None:
    """Close on or before an ISO date such as ``2026-01-31``. ``None`` if uncovered."""
    b = bars(ticker, root, include_etfs=include_etfs)
    if not b:
        return None
    r = asof(b, iso_date.replace("-", ""))
    return r[1] if r else None


def split_scan(
    ticker: str,
    since: str = "20000101",
    lo: float = 0.80,
    hi: float = 1.25,
    root: str | Path | None = None,
) -> list[tuple[str, float, float, float]]:
    """Day-over-day moves outside ``[lo, hi]``: candidate split artifacts or real events.

    Run this before trusting a long-window return, and resolve every hit to a
    real event or treat the series as suspect. Returns ``(date, prev, close, ratio)``.
    """
    b = [x for x in (bars(ticker, root) or []) if x[0] >= since]
    out = []
    for i in range(1, len(b)):
        p0, p1 = b[i - 1][1], b[i][1]
        if p0 > 0 and not (lo <= p1 / p0 <= hi):
            out.append((b[i][0], p0, p1, p1 / p0))
    return out


def close_at(
    ticker: str,
    day,
    max_stale_days: int = 14,
    root: str | Path | None = None,
) -> float | None:
    """Last close on or before ``day``, refused when it is more than ``max_stale_days`` old.

    ``px`` answers "the last close there was", which on a name whose series
    stopped is a print from any distance in the past and looks like a live
    price. This is the same lookup with the staleness rule every price study
    needs: a snapshot date that no close comes within a fortnight of is not
    priced, and returning the stale print instead puts a frozen level into a
    return.

    A fiscal period end lands on a weekend or a holiday constantly, so the rule
    has to be "on or before, within a window" rather than an exact-date lookup.
    ``None`` when the symbol is absent from the bundle (a delisted issuer is
    absent entirely, see docs/traps.md trap 3), when nothing precedes ``day``,
    or when the last print is too old.

    ``day`` may be an ISO string, a ``datetime.date`` or a pandas ``Timestamp``.
    """
    b = bars(ticker, root)
    if not b:
        return None
    key = day.strftime("%Y%m%d") if hasattr(day, "strftime") else str(day).replace("-", "")[:8]
    r = asof(b, key)
    if r is None:
        return None
    found = date(int(r[0][:4]), int(r[0][4:6]), int(r[0][6:8]))
    want = date(int(key[:4]), int(key[4:6]), int(key[6:8]))
    return None if (want - found).days > max_stale_days else r[1]
