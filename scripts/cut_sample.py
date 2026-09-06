"""Cut the published point-in-time sample from a full panel export.

Reads the Pro export at ``cache/panel.csv`` (``examples/fetch_panel.py``
writes it) and keeps every row for 200 CIKs drawn at random with a fixed seed,
so the sample keeps the panel's base rates: the share of firms that leave the
panel, the sector mix, the null rates. It is not a curated set. The publisher
attaches the result to a GitHub release so the longitudinal examples run
without a key; README says where.

Usage: python scripts/cut_sample.py [panel.csv] [out.csv.gz]
"""

from __future__ import annotations

import gzip
import sys

import numpy as np
import pandas as pd

from distill_toolkit import client

SEED = 20260630
FIRMS = 200


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else client.CACHE_DIR / "panel.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else client.CACHE_DIR / "pit-sample.csv.gz"
    panel = pd.read_csv(src, dtype=str, keep_default_na=False)
    if panel.as_of_date.nunique() < 2:
        sys.exit("the file is a single snapshot; the sample is cut from the Pro export")
    ciks = sorted(panel.cik.unique())
    keep = set(np.random.default_rng(SEED).choice(ciks, FIRMS, replace=False))
    sample = panel[panel.cik.isin(keep)].sort_values(["cik", "as_of_date"])
    with gzip.open(out, "wt", newline="") as fh:
        sample.to_csv(fh, index=False)
    last = sample.groupby("cik").as_of_date.max()
    print(f"{len(sample)} rows, {sample.cik.nunique()} firms, "
          f"{sample.as_of_date.min()} to {sample.as_of_date.max()}, "
          f"{(last < sample.as_of_date.max()).sum()} firms leave before the last snapshot, "
          f"{sample[sample.listed_until != ''].cik.nunique()} carry listed_until -> {out}")


if __name__ == "__main__":
    main()
