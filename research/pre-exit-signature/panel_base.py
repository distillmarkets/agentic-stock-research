"""Universe, exit definition and quarter indexing shared by the study and its probe.

Everything here is derived from ``cache/panel.csv`` alone (the 2026-09-03
``screen/export`` vintage, final quarter 2026-06-30). No price file, no API.

Definitions, in one place because every number in the study depends on them:

* ``qi`` is a quarter index, ``year * 4 + (month - 1) // 3``. The panel's final
  quarter, 2026-06-30, is ``FINAL_QI``.
* A CIK **exits** when its last panel row is at least eight quarters before that
  final quarter (``last_qi <= FINAL_QI - 8``). A firm-quarter panel row exists
  for as long as the export carries the filer, so "never reappears" is automatic:
  the test is on the maximum.
* ``fresh_qi`` is the first quarter carrying the CIK's final ``fiscal_year``,
  which is the last quarter at which a new annual filing refreshed the record.
  Between ``fresh_qi`` and ``last_qi`` the row repeats: the export keeps serving
  a filer whose newest full fiscal year is up to two years old, so the last row
  is a drop date and not a filing date.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "cache" / "panel.csv"
CACHE = ROOT / "cache" / "research" / "pre-exit-signature"
CHARTS = Path(__file__).resolve().parent / "charts"
PANEL_VINTAGE = "2026-09-03"
FINAL_QI = 2026 * 4 + 1  # 2026-06-30
EXIT_HORIZON = 8         # quarters


def quarter_index(dates: pd.Series) -> pd.Series:
    return dates.dt.year * 4 + (dates.dt.month - 1) // 3


def qi_label(q: int) -> str:
    return f"{q // 4}Q{q % 4 + 1}"


def load_panel() -> pd.DataFrame:
    return pd.read_csv(PANEL, parse_dates=["as_of_date"], dtype={"cik": str})


def build_universe(panel: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(rows, firms)``: listed revenue-positive quarterly rows, and one row per CIK.

    The ticker filter drops the 268 tickers that map to more than one CIK
    anywhere in the export, matching ``analysis.december_snapshots`` so the
    counts here sit next to the ghost-cohort study's on the same basis.
    """
    p = load_panel() if panel is None else panel
    multi = p.groupby("ticker").cik.nunique()
    collided = set(multi[multi > 1].index)
    u = p[p.is_listed_equity & (p.revenue > 0) & ~p.ticker.isin(collided)].copy()
    u["qi"] = quarter_index(u.as_of_date)
    u = u.sort_values(["cik", "qi"]).reset_index(drop=True)

    last = u.groupby("cik").qi.max()
    first = u.groupby("cik").qi.min()
    final_fy = u.groupby("cik").fiscal_year.transform("last")
    fresh = u[u.fiscal_year == final_fy].groupby("cik").qi.min()
    firms = pd.DataFrame({"first_qi": first, "last_qi": last, "fresh_qi": fresh})
    firms["exit"] = firms.last_qi <= FINAL_QI - EXIT_HORIZON
    firms["stale_tail"] = firms.last_qi - firms.fresh_qi
    firms["hist_q"] = firms.fresh_qi - firms.first_qi
    firms["ticker"] = u.groupby("cik").ticker.last()
    firms["sector"] = u.groupby("cik").sector.last()
    return u, firms
