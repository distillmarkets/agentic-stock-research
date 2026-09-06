"""Study: does a high M-Score (earnings-manipulation flag) at time T predict
subsequent revisions of the history that was on file at T?

Design: take the 2022-12-31 as-of snapshot, rank listed equities by m_score_5,
fetch /sec/revisions for the top and bottom 150 (detail rows need an Analyst key or above). Outcome = a restated annual
fact whose period had already ended at T but whose latest (revised) filing came
after T. That is exactly "the past you were shown at T later changed".
"""

import json

import httpx
import pandas as pd

from distill_toolkit import client

SNAP = "2022-12-31"
N = 150
OUT = client.CACHE_DIR / "mscore_revisions.json"


def main():
    df = pd.read_csv(client.panel_path(), parse_dates=["as_of_date"])
    snap = df[
        (df.as_of_date == SNAP)
        & df.is_listed_equity
        & (df.revenue > 1e8)
        & df.m_score_5.notna()
    ]
    ranked = snap.sort_values("m_score_5")
    lo = ranked.head(N)  # least manipulation-like
    hi = ranked.tail(N)  # most manipulation-like

    rows = []
    for group, part in (("low_m", lo), ("high_m", hi)):
        for _, r in part.iterrows():
            try:
                resp = client.get(f"/api/v1/sec/revisions/{r.ticker}")
            except httpx.HTTPStatusError as e:
                rows.append(
                    {"ticker": r.ticker, "group": group, "m": r.m_score_5,
                     "error": e.response.status_code}
                )
                continue
            future_revisions = [
                x
                for x in resp["revisions"]
                if x["periodEnd"] <= SNAP and (x["latestFiled"] or "") > SNAP
            ]
            rows.append(
                {
                    "ticker": r.ticker,
                    "group": group,
                    "m": r.m_score_5,
                    "annualFactKeys": resp["annualFactKeys"],
                    "revisedTotal": resp["revisedFactKeys"],
                    "futureRevisions": len(future_revisions),
                    "maxRelDelta": max((x["relDelta"] for x in future_revisions), default=0),
                }
            )
            print(f"{group} {r.ticker}: futureRev={len(future_revisions)}", flush=True)

    OUT.write_text(json.dumps(rows, indent=1))
    print(f"wrote {len(rows)} rows -> {OUT}")

    ok = pd.DataFrame([r for r in rows if "error" not in r])
    summary = ok.groupby("group").agg(
        n=("ticker", "size"),
        any_future_revision=("futureRevisions", lambda x: 100 * (x > 0).mean()),
        revision_ge_10pct=("maxRelDelta", lambda x: 100 * (x >= 0.10).mean()),
    ).round(1)
    print("\n% of firms with a future revision of on-file history, by M-Score group:")
    print(summary.to_string())


if __name__ == "__main__":
    main()
