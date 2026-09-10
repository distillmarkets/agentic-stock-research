"""Whether a filer in the point-in-time panel can be named, and whether the
answer depends on its listing having ended.

Two halves. The keyless half joins the panel to the SEC's free
``company_tickers.json``, which the user holds on disk, and needs no API key at
all: tables 1, 2, 3 and 7. The API half reads the ``/sec/profile/{ticker}``
responses already in ``cache/`` as files and reports what the endpoint returned
for the same firms, including where it named a different company: tables 4, 5
and 6. The API half is skipped, with a printed note, when those responses are
not on disk.

Every number in README.md comes out of this script; the tables it prints are
also written under ``cache/research/naming-the-dead/``.

Run from the repository root:

    SEC_TICKERS=cache/sec/company_tickers.json \\
    DISTILL_OFFLINE=1 ./.venv/bin/python research/naming-the-dead/study.py

Uncached API calls: 0. The client's request functions are replaced by a raiser
before anything else is imported, so a run that reaches its last line made none.
The SEC file is never downloaded by anything here; docs/data-sources.md carries
the one-line fetch and the terms.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DISTILL_OFFLINE", "1")

import distill_toolkit.client as _client  # noqa: E402


def _no_call(*_a, **_k):
    raise RuntimeError("naming-the-dead makes no API call; every input is on disk")


_client.get = _client.post = _client.request = _client.download = _no_call

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from distill_toolkit import charts, client, sec_tickers  # noqa: E402

HERE = Path(__file__).parent
OUT = client.CACHE_DIR / "research" / "naming-the-dead"
CHARTS = HERE / "charts"
SOURCES = ("form25", "form15", "crawl", "migration")
QS = [0.1, 0.25, 0.5, 0.75, 0.9]
HEALTHCARE_FLOOR = 10_000_000

# The three situations behind a mismatch, hand-classified against what the
# filings say and named here so a reader can check each one. The geometry in
# ``where_it_lands`` cannot separate them; this list is not computed.
HAND_CLASSIFIED = {
    "GOOG": "successor after a reorganisation (Google Inc reorganised under Alphabet)",
    "ETN": "successor after a reorganisation (Eaton Corp reincorporated as Eaton Corp plc)",
    "DIS": "successor after a reorganisation (the old Walt Disney Co under the new one)",
    "DOW": "successor after a reorganisation (Dow Chemical, then DowDuPont, then Dow Inc)",
    "DELL": "successor after a reorganisation (Dell Inc taken private, back as Dell Technologies)",
    "BEAM": "unrelated company that took the symbol later (a spirits maker, then a biotech)",
    "APC": "unrelated company that took the symbol later (Anadarko Petroleum, then ARKO Petroleum)",
    "DTV": "predecessor (DirecTV resolving backwards to DIRECTV GROUP INC)",
}


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def snapshot() -> list[list]:
    return [[str(p), s, m] for p, s, m in client.manifest()]


def load_panel() -> tuple[pd.DataFrame, str]:
    """The panel with the listing columns: the full export if it carries them,
    else the published sample."""
    path = client.panel_path()
    df = pd.read_csv(path, low_memory=False)
    if "listed_until" not in df.columns:
        alt = client.CACHE_DIR / "pit-sample.csv.gz"
        if path.name != alt.name and alt.exists():
            print(f"note: {path.name} carries no listed_until column (an export older than "
                  f"2026-09-07); running on {alt.name}")
            path, df = alt, pd.read_csv(alt, low_memory=False)
        else:
            raise KeyError("the panel on disk has no listed_until column; fetch an export "
                           "from 2026-09-07 or later, or the published sample")
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    df["listed_until"] = pd.to_datetime(df["listed_until"])
    return df.sort_values(["cik", "as_of_date"]).reset_index(drop=True), path.name


def firms(df: pd.DataFrame) -> pd.DataFrame:
    """One row per CIK, its last panel row, with the listing status on it."""
    last = df.groupby("cik").tail(1).set_index("cik").copy()
    last["ended"] = last["listed_until"].notna()
    last["status"] = np.where(last["ended"], "with a listing end", "still listed")
    return last


def free_file() -> tuple[dict, str]:
    """The SEC identity file the user holds, and its own date."""
    path = sec_tickers.default_path()
    if not path.exists():
        raise FileNotFoundError(
            f"the SEC identity file is not at {path}. Point SEC_TICKERS at your copy, or "
            "fetch one: docs/data-sources.md carries the command and the terms. This study "
            "does not download it.")
    return sec_tickers.index(path), str(sec_tickers.vintage(path))


def profiles(last: pd.DataFrame) -> pd.DataFrame | None:
    """What ``/sec/profile/{ticker}`` returned for every ended firm, read off disk.

    ``None`` when the responses are not cached, which is what a checkout without
    a key sees; the keyless tables run either way.
    """
    ended = last[last["ended"]]
    rows = []
    for cik, r in ended.iterrows():
        body = client.cached(f"/api/v1/sec/profile/{r['ticker']}")
        if body is None:
            rows.append({"cik": cik, "ticker": r["ticker"], "cached": False,
                         "name": None, "cik_returned": np.nan, "resolver": None})
            continue
        ret = body.get("cikNumber")
        rows.append({"cik": cik, "ticker": r["ticker"], "cached": True,
                     "name": body.get("name") or None,
                     "cik_returned": int(ret) if ret else np.nan,
                     "resolver": body.get("source")})
    out = pd.DataFrame(rows).set_index("cik")
    if not out["cached"].any():
        return None
    if not out["cached"].all():
        print(f"note: {int((~out['cached']).sum())} of {len(out)} profile responses are not "
              "cached; the API tables cover the rest and say so")
    out = out[out["cached"]].copy()
    out["named"] = out["name"].notna()
    out["agrees"] = out["cik_returned"].eq(pd.Series(out.index, index=out.index))
    out["source"] = ended.loc[out.index, "listing_end_source"]
    return out


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------
def t1_universe(df, last, free, free_date, panel_name) -> dict:
    return {
        "panel": panel_name,
        "first_snapshot": str(df["as_of_date"].min().date()),
        "final_snapshot": str(df["as_of_date"].max().date()),
        "rows": int(len(df)), "firms": int(len(last)),
        "still_listed": int((~last["ended"]).sum()),
        "with_a_listing_end": int(last["ended"].sum()),
        "by_source": {s: int((last["listing_end_source"] == s).sum()) for s in SOURCES},
        "free_file_date": free_date,
        "free_file_ciks": len(free),
        "free_file_ticker_rows": sum(len(r["tickers"]) for r in free.values()),
    }


def t2_nameable(last, free) -> pd.DataFrame:
    """The share of each cohort the free file can put a name to, keyed on CIK."""
    last = last.copy()
    last["nameable"] = last.index.isin(free)
    rows = []
    for cut, frame in [("still listed", last[~last["ended"]]),
                       ("with a listing end", last[last["ended"]])]:
        rows.append({"cut": cut, "n": len(frame), "nameable": int(frame["nameable"].sum())})
    for s in SOURCES:
        frame = last[last["listing_end_source"].eq(s)]
        rows.append({"cut": f"  {s}", "n": len(frame), "nameable": int(frame["nameable"].sum())})
    tab = pd.DataFrame(rows)
    tab["share"] = (100 * tab["nameable"] / tab["n"]).round(1)
    return tab


def t3_ticker_key(last, free) -> pd.DataFrame:
    """The same file reached by its other key: is the panel's ticker in the file,
    and does it point at the firm that held it."""
    by_ticker: dict[str, set[int]] = {}
    for rec in free.values():
        for t in rec["tickers"]:
            by_ticker.setdefault(t, set()).add(int(rec["cik"]))
    rows = []
    for cut, frame in [("still listed", last[~last["ended"]]),
                       ("with a listing end", last[last["ended"]])]:
        present = right = 0
        for cik, r in frame.iterrows():
            holders = by_ticker.get(str(r["ticker"]).upper())
            if holders is None:
                continue
            present += 1
            right += int(cik in holders)
        rows.append({"cut": cut, "n": len(frame), "ticker_in_file": present,
                     "points_at_this_firm": right, "points_elsewhere": present - right})
    tab = pd.DataFrame(rows)
    tab["wrong_share_of_n"] = (100 * tab["points_elsewhere"] / tab["n"]).round(1)
    return tab


def t4_api_coverage(prof) -> dict:
    return {
        "asked": int(len(prof)),
        "named": int(prof["named"].sum()),
        "not_named": int((~prof["named"]).sum()),
        "by_resolver": {k: int(v) for k, v in prof["resolver"].value_counts(dropna=False).items()},
    }


def t5_defect(prof) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    def tab(col):
        g = prof.groupby(col)["agrees"].agg(["sum", "count"])
        g = g.rename(columns={"sum": "cik_agrees", "count": "n"})
        g["cik_differs"] = g["n"] - g["cik_agrees"]
        g["share_differs"] = (100 * g["cik_differs"] / g["n"]).round(1)
        return g.reset_index()

    total = {"n": int(len(prof)), "cik_agrees": int(prof["agrees"].sum()),
             "cik_differs": int((~prof["agrees"]).sum()),
             "share_differs": round(100 * float((~prof["agrees"]).mean()), 1)}
    return tab("source"), tab("resolver"), total


def where_it_lands(df, last, prof) -> pd.DataFrame:
    """For every mismatch, the returned CIK's span of panel rows under the SAME
    ticker, against the asked firm's last row. A geometry, not a corporate fact."""
    span = df.groupby(["ticker", "cik"])["as_of_date"].agg(["min", "max"])
    rows = []
    for cik, r in prof[~prof["agrees"]].iterrows():
        key = (r["ticker"], r["cik_returned"])
        asked_last = last.loc[cik, "as_of_date"]
        listed_until = last.loc[cik, "listed_until"]
        if key not in span.index:
            lands, gap = "absent from the panel under this ticker", np.nan
        else:
            start = span.loc[key, "min"]
            lands = "later holder" if start >= asked_last else "earlier or overlapping holder"
            gap = (start - listed_until).days if lands == "later holder" else np.nan
        ret = int(r["cik_returned"])
        rows.append({"cik": cik, "ticker": r["ticker"], "source": r["source"],
                     "resolver": r["resolver"], "listed_until": listed_until,
                     "name_returned": r["name"], "cik_returned": ret,
                     "returned_is_still_listed": bool(
                         ret in last.index and not last.loc[ret, "ended"]),
                     "lands": lands, "gap_days": gap})
    return pd.DataFrame(rows).set_index("cik")


def t6_mismatches(mis) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    cross = pd.crosstab(mis["source"], mis["lands"])
    gaps = mis.loc[mis["lands"].eq("later holder"), "gap_days"].astype(float)
    q = gaps.quantile(QS)
    summary = {
        "mismatches": int(len(mis)),
        "by_landing": {k: int(v) for k, v in mis["lands"].value_counts().items()},
        "returns_a_still_listed_company": int(mis["returned_is_still_listed"].sum()),
        "later_holder_gap_days": {"n": int(len(gaps)), "p10": q[0.1], "p25": q[0.25],
                                  "median": q[0.5], "p75": q[0.75], "p90": q[0.9],
                                  "within_1y": int((gaps <= 365).sum()),
                                  "over_5y": int((gaps > 1826).sum())},
    }
    named = mis[mis["ticker"].isin(HAND_CLASSIFIED)].copy()
    named["hand_classification"] = named["ticker"].map(HAND_CLASSIFIED)
    named = named[["ticker", "source", "listed_until", "name_returned", "cik_returned",
                   "lands", "gap_days", "hand_classification"]]
    return cross, summary, named.sort_values("ticker")


def post_hoc_former_names(last) -> dict:
    """Not preregistered. Noticed while reading the responses, printed rather
    than folded into a table so the pre-registration still describes the tables.

    ``formerNamesJson`` is populated on some responses and not others; this
    counts which, split by whether the CIK agreed.
    """
    out = {"populated_where_cik_agrees": 0, "populated_where_cik_differs": 0,
           "agrees": 0, "differs": 0, "example": None}
    for cik, r in last[last["ended"]].iterrows():
        body = client.cached(f"/api/v1/sec/profile/{r['ticker']}")
        if body is None:
            continue
        ret = body.get("cikNumber")
        agrees = bool(ret) and int(ret) == cik
        out["agrees" if agrees else "differs"] += 1
        if body.get("formerNamesJson"):
            out["populated_where_cik_agrees" if agrees else "populated_where_cik_differs"] += 1
            if not agrees and r["ticker"] == "DIS":
                out["example"] = {"ticker": "DIS", "former_names": body["formerNamesJson"]}
    return out


def t7_healthcare(df, free) -> pd.DataFrame:
    """One sector on the honest denominator: the last Healthcare row per ticker
    above a revenue floor, by listing status and revenue tercile."""
    hc = df[df["sector"].eq("Healthcare")].sort_values(["ticker", "as_of_date"])
    pool = hc.groupby("ticker").tail(1)
    pool = pool[pool["revenue"] >= HEALTHCARE_FLOOR].copy()
    pool["ended"] = pool["listed_until"].notna()
    pool["nameable"] = pool["cik"].isin(free)
    rows = []
    for ended, g in pool.groupby("ended"):
        cut = "with a listing end" if ended else "still listed"
        g = g.copy()
        g["tercile"] = pd.qcut(g["revenue"].rank(method="first"), 3,
                               labels=["small", "mid", "large"])
        rows.append({"cut": cut, "tercile": "all", "n": len(g),
                     "nameable": int(g["nameable"].sum())})
        for terc, cell in g.groupby("tercile", observed=True):
            rows.append({"cut": cut, "tercile": str(terc), "n": len(cell),
                         "nameable": int(cell["nameable"].sum())})
    tab = pd.DataFrame(rows)
    tab["share"] = (100 * tab["nameable"] / tab["n"]).round(1)
    return tab


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
def chart_nameable(t2, source_text: str) -> None:
    fig, (ax,) = charts.figure(
        "The free identity file names nine in ten listed filers and one filer in three thousand whose listing has ended",
        "Share of each cohort whose CIK is a key in the SEC's company_tickers.json. The file is a list of current registrants, so a company that has left it cannot be named from it at all.")
    rows = t2[t2["cut"].isin(["still listed", "with a listing end"])
              | t2["cut"].str.strip().isin(SOURCES)]
    labels = [f"{c.strip()}\n(n={n:,})" for c, n in zip(rows["cut"], rows["n"])]
    colors = [charts.BRAND if c.strip() == "still listed" else charts.INK2
              for c in rows["cut"]]
    charts.bars(ax, labels, rows["share"], color=colors, fmt="{:.1f}%")
    charts.finish(ax, pct=True)
    charts.save(fig, CHARTS / "nameable.png", source_text)


def chart_mismatch(t5_src, mis, source_text: str) -> None:
    fig, axes = charts.figure(
        "One ticker-keyed name in eight is another company's, and a migration is wrong seven times in eight",
        "Left: share of ended filers whose profile response carried a different CIK from the one asked about, by how the listing ended. Right: where the 386 land, as the returned CIK's own panel rows under the same ticker.",
        panels=2, widths=[1.15, 1])
    order = [s for s in SOURCES if s in set(t5_src["source"])]
    t = t5_src.set_index("source").loc[order]
    charts.bars(axes[0], [f"{s}\n(n={n:,})" for s, n in zip(t.index, t["n"])],
                t["share_differs"], fmt="{:.1f}%")
    charts.finish(axes[0], pct=True)
    counts = mis["lands"].value_counts()
    wrap = {"later holder": "a later holder\nof the ticker",
            "earlier or overlapping holder": "an earlier or\noverlapping holder",
            "absent from the panel under this ticker": "absent from the panel\nunder this ticker"}
    charts.bars(axes[1], [wrap.get(k, k) for k in counts.index], counts.values,
                color=charts.INK2, fmt="{:.0f}")
    charts.finish(axes[1], "firms")
    charts.save(fig, CHARTS / "mismatch.png", source_text)


# ---------------------------------------------------------------------------
def fmt(df: pd.DataFrame) -> str:
    return df.to_string(index=False, float_format=lambda v: f"{v:,.1f}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    (OUT / "manifest-start.json").write_text(json.dumps(snapshot()))

    df, panel_name = load_panel()
    last = firms(df)
    free, free_date = free_file()

    t1 = t1_universe(df, last, free, free_date, panel_name)
    print("T1 universe and vintage"); print(json.dumps(t1, indent=1))
    (OUT / "t1_universe.json").write_text(json.dumps(t1, indent=1))

    t2 = t2_nameable(last, free)
    print("\nT2 nameable from the free file, by listing status"); print(fmt(t2))
    t2.to_csv(OUT / "t2_nameable.csv", index=False)

    t3 = t3_ticker_key(last, free)
    print("\nT3 the same file reached by its other key"); print(fmt(t3))
    t3.to_csv(OUT / "t3_ticker_key.csv", index=False)

    t7 = t7_healthcare(df, free)
    print("\nT7 one sector, on the honest denominator"); print(fmt(t7))
    t7.to_csv(OUT / "t7_healthcare.csv", index=False)

    src = (f"Distill Markets point-in-time export, {panel_name}, snapshots "
           f"{t1['first_snapshot']} to {t1['final_snapshot']}; SEC company_tickers.json as "
           f"held on {free_date}.")
    chart_nameable(t2, src)

    prof = profiles(last)
    if prof is None:
        print("\nT4 to T6 skipped: no /sec/profile responses in the cache. Tables 1, 2, 3 "
              "and 7 above are the keyless half and are complete.")
    else:
        t4 = t4_api_coverage(prof)
        print("\nT4 what the API lookup returns for the ended firms"); print(json.dumps(t4, indent=1))
        (OUT / "t4_api_coverage.json").write_text(json.dumps(t4, indent=1))

        t5_src, t5_res, t5_tot = t5_defect(prof)
        print("\nT5 the identity defect, by how the listing ended"); print(fmt(t5_src))
        print("\nT5 the identity defect, by the response's own resolver source"); print(fmt(t5_res))
        print(json.dumps(t5_tot, indent=1))
        t5_src.to_csv(OUT / "t5_by_listing_end_source.csv", index=False)
        t5_res.to_csv(OUT / "t5_by_resolver.csv", index=False)
        (OUT / "t5_total.json").write_text(json.dumps(t5_tot, indent=1))

        mis = where_it_lands(df, last, prof)
        cross, t6, named = t6_mismatches(mis)
        print("\nT6 where the mismatches land"); print(cross.to_string())
        print(json.dumps(t6, indent=1, default=float))
        print("\nT6 the three situations, hand-classified and named")
        print(named.to_string())
        mis.to_csv(OUT / "t6_mismatches.csv")
        cross.to_csv(OUT / "t6_landing_by_source.csv")
        (OUT / "t6_summary.json").write_text(json.dumps(t6, indent=1, default=float))
        chart_mismatch(t5_src, mis, src)

        fn = post_hoc_former_names(last)
        print("\nNot preregistered, printed rather than folded into a table: "
              "formerNamesJson by whether the CIK agreed")
        print(json.dumps(fn, indent=1))
        (OUT / "post_hoc_former_names.json").write_text(json.dumps(fn, indent=1))

    (OUT / "manifest-end.json").write_text(json.dumps(snapshot()))
    start = json.loads((OUT / "manifest-start.json").read_text())
    end = json.loads((OUT / "manifest-end.json").read_text())
    changed = [e for e in end if e not in start and not e[0].startswith(str(OUT))]
    print(f"\ncache entries that changed during the run, outside this study's folder: {len(changed)}")


if __name__ == "__main__":
    main()
