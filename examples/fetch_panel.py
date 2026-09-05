"""Fetch the full point-in-time fundamentals panel to cache/panel.csv.

One call to GET /api/v1/sec/screen/export returns the as-of grid as CSV: every
ticker x every quarterly snapshot date since 2009 on a Pro key, or the current
snapshot on a free key. The file lands in the cache directory, which is
gitignored: it is licensed data for your own use.

Usage: python examples/fetch_panel.py
"""

import time

from distill_toolkit import client

OUT = client.CACHE_DIR / "panel.csv"


def main():
    t0 = time.perf_counter()
    path = client.download("/api/v1/sec/screen/export", OUT, timeout=300)
    secs = time.perf_counter() - t0
    size_mb = path.stat().st_size / 1e6
    rows = sum(1 for _ in path.open()) - 1
    print(f"{size_mb:.1f}MB {rows} rows in {secs:.1f}s -> {path}")


if __name__ == "__main__":
    main()
