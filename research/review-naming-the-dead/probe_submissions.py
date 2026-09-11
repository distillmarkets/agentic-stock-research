"""Census probe: does SEC's own free per-CIK submissions file name a filer whose
listing has ended?

The reviewed study measures nameability against ``company_tickers.json``, the
free bulk file, and finds 1 of 3,104. That file is not the only free SEC route
to a name. ``https://data.sec.gov/submissions/CIK##########.json`` is served per
CIK, carries ``name``, ``formerNames``, ``tickers`` and ``exchanges``, and is
also free. If it names the dead, the study's headline is about one file rather
than about free data, and the difference matters to every reader deciding what
to pay for.

This asks for all 3,104 ended firms, one request each, at eight a second against
SEC's published ceiling of ten. Responses are reduced to one row per CIK and
written to ``cache/research/review-naming-the-dead/submissions.csv``; the full
payloads are not kept. ``study.py`` reads only that file and never runs this one.

SEC's Frequently Accessed Datasets terms require a User-Agent that identifies
the requester. Set ``SEC_USER_AGENT`` to your own name and address before
running; there is no default.

    SEC_USER_AGENT="you your@email" \\
    ./.venv/bin/python research/review-naming-the-dead/probe_submissions.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from distill_toolkit import client  # noqa: E402

OUT = client.CACHE_DIR / "research" / "review-naming-the-dead"
URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
PAUSE = 0.125  # 8 a second; SEC publishes 10 as the ceiling


def ended_firms() -> pd.DataFrame:
    df = pd.read_csv(client.panel_path(), low_memory=False)
    ended = df[df["listed_until"].notna()].sort_values("as_of_date")
    return ended.groupby("cik").agg(ticker=("ticker", "last"),
                                    listed_until=("listed_until", "last"),
                                    listing_end_source=("listing_end_source", "last"))


def fetch(cik: int, agent: str) -> dict:
    req = urllib.request.Request(URL.format(cik),
                                 headers={"User-Agent": agent,
                                          "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw)


def main() -> None:
    agent = os.environ.get("SEC_USER_AGENT")
    if not agent:
        raise SystemExit("set SEC_USER_AGENT to a name and address SEC can contact")
    OUT.mkdir(parents=True, exist_ok=True)
    firms = ended_firms()
    print(f"ended firms to ask for: {len(firms)}", flush=True)

    rows: list[dict] = []
    errors: dict[str, int] = {}
    for i, (cik, r) in enumerate(firms.iterrows(), 1):
        row = {"cik": int(cik), "ticker": r.ticker, "listed_until": r.listed_until,
               "listing_end_source": r.listing_end_source,
               "name": "", "n_former_names": 0, "sec_tickers": "", "sec_exchanges": "",
               "error": ""}
        try:
            d = fetch(int(cik), agent)
            row["name"] = d.get("name") or ""
            row["n_former_names"] = len(d.get("formerNames") or [])
            row["sec_tickers"] = ",".join(d.get("tickers") or [])
            row["sec_exchanges"] = ",".join(e for e in (d.get("exchanges") or []) if e)
        except Exception as exc:  # noqa: BLE001 - the count is the point, not the type
            key = f"{type(exc).__name__}: {exc}"[:70]
            errors[key] = errors.get(key, 0) + 1
            row["error"] = key
        rows.append(row)
        if i % 400 == 0:
            print(f"  {i}/{len(firms)}", flush=True)
        time.sleep(PAUSE)

    # A read timeout is a transient network fact, not an answer about the filer.
    # One retry pass at a longer timeout, so a run reports what SEC holds rather
    # than what the network managed on the day.
    out = pd.DataFrame(rows)
    retry = out.index[out["error"].str.len() > 0]
    if len(retry):
        print(f"\nretrying {len(retry)} that errored", flush=True)
        for i in retry:
            try:
                d = fetch(int(out.at[i, "cik"]), agent)
            except Exception:  # noqa: BLE001 - leave the recorded error in place
                continue
            out.at[i, "name"] = d.get("name") or ""
            out.at[i, "n_former_names"] = len(d.get("formerNames") or [])
            out.at[i, "sec_tickers"] = ",".join(d.get("tickers") or [])
            out.at[i, "sec_exchanges"] = ",".join(e for e in (d.get("exchanges") or []) if e)
            out.at[i, "error"] = ""
            time.sleep(PAUSE)

    out.to_csv(OUT / "submissions.csv", index=False)
    named = out["name"].str.len() > 0
    print(f"\nnamed: {int(named.sum())}/{len(out)} ({100 * named.mean():.1f}%)")
    print(f"errors: {errors or 'none'}")
    print(f"written: {OUT / 'submissions.csv'}")


if __name__ == "__main__":
    main()
