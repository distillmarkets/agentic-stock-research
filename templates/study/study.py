"""<Question>. Reproduces every number in README.md from files on disk.

Run from the repository root:

    DISTILL_OFFLINE=1 python research/<name>/study.py

Uncached API calls: 0 in reproduction. Budget for the first run: <n>.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from distill_toolkit import analysis, client, joins, stooq

HERE = Path(__file__).parent
OUT = HERE / "tables"


def snapshot() -> list[list]:
    """The cache manifest as JSON rows: a file that changes between the two
    snapshots is an input the study did not have at its first number."""
    return [[str(path), size, mtime] for path, size, mtime in client.manifest()]


def load_panel() -> pd.DataFrame:
    """The point-in-time panel, from examples/fetch_panel.py."""
    return pd.read_csv(client.panel_path(), parse_dates=["as_of_date"])


def pin_events(panel: pd.DataFrame) -> pd.DataFrame:
    """Write the event set to disk before any per-ticker call is made."""
    path = HERE / "events.parquet"
    if path.exists():
        return pd.read_parquet(path)
    events = panel  # select the rows the study is about
    events.to_parquet(path)
    return events


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (HERE / "manifest-start.json").write_text(json.dumps(snapshot(), indent=1))

    panel = load_panel()
    events = pin_events(panel)

    # 1. the statistic on the observed labels
    # 2. the same statistic under analysis.clustered_shuffle, clustered by cik
    # 3. the interval from analysis.cluster_boot_diff
    # each table written to OUT as csv, each number in README traceable here

    (HERE / "manifest-end.json").write_text(json.dumps(snapshot(), indent=1))


if __name__ == "__main__":
    main()
