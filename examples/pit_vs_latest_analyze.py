"""Analyze cache/pit_vs_latest.parquet: divergence stats + screen-flip rates."""

from distill_toolkit import client

import numpy as np
import pandas as pd

df = pd.read_parquet(client.CACHE_DIR / "pit_vs_latest.parquet")

df = df.dropna(subset=["rev_pit", "rev_latest"])
df["rev_delta"] = (df.rev_latest - df.rev_pit).abs() / df.rev_pit
m = df.dropna(subset=["netm_pit", "netm_latest"]).copy()
m["netm_delta_pp"] = (m.netm_latest - m.netm_pit).abs() * 100

print(f"firm-years compared: {len(df)} (firms: {df.cik.nunique()})")
print(f"revenue differs >=1%: {100*(df.rev_delta>=0.01).mean():.1f}%")
print(f"revenue differs >=5%: {100*(df.rev_delta>=0.05).mean():.1f}%")
print(f"revenue differs >=10%: {100*(df.rev_delta>=0.10).mean():.1f}%")
print(f"net margin differs >=1pp: {100*(m.netm_delta_pp>=1).mean():.1f}%")
print(f"net margin differs >=5pp: {100*(m.netm_delta_pp>=5).mean():.1f}%")

# Screen flips: quintile firms on net margin per fiscal year under each vintage
flips, top_churn = [], []
for fy, g in m.groupby("fiscal_year"):
    if len(g) < 50:
        continue
    g = g.copy()
    g["q_pit"] = pd.qcut(g.netm_pit, 5, labels=False, duplicates="drop")
    g["q_lat"] = pd.qcut(g.netm_latest, 5, labels=False, duplicates="drop")
    flips.append((g.q_pit != g.q_lat).mean())
    tp, tl = set(g[g.q_pit == 4].cik), set(g[g.q_lat == 4].cik)
    if tp:
        top_churn.append(1 - len(tp & tl) / len(tp | tl))

print(f"\nnet-margin quintile flip rate (mean across years): {100*np.mean(flips):.1f}%")
print(f"top-quintile membership churn (Jaccard distance): {100*np.mean(top_churn):.1f}%")

worst = m.nlargest(10, "netm_delta_pp")[
    ["ticker", "fiscal_year", "netm_pit", "netm_latest", "netm_delta_pp"]
]
print("\nlargest net-margin rewrites (first-print vs today):")
print(worst.round(3).to_string(index=False))
