# Examples

Run them from anywhere inside the repository. The cache directory resolves next
to your `.env`, or wherever `DISTILL_CACHE_DIR` points.

| script | needs | what it does |
|---|---|---|
| `sweep_endpoints.py` | free key | hits every documented endpoint across a spread of response shapes, logs latency and shapes |
| `fetch_panel.py` | free key (current snapshot) or Pro (full history, about 78 MB CSV) | one call for the screener panel as CSV |
| `passport.py` | key + Stooq bundle | `python examples/passport.py NVDA` draws one company's filings, revisions, share count and Form 4 activity against its price on a shared timeline |
| `panel_studies.py` | panel | accruals, capital cycle, boom-cell membership, score persistence |
| `return_tests.py` | panel + Stooq bundle | do the fundamentals findings show up in forward price returns? |
| `valuation_decomposition.py` | key + Stooq bundle | revenue-per-share versus multiple for a cohort, with the split check; you name the baseline date and the cohort |
| `pit_vs_latest.py` | panel | first-print versus latest-filing vintages for 300 sampled firms |
| `pit_vs_latest_analyze.py` | pit_vs_latest output | divergence stats and screen-flip rates between vintages |
| `mscore_revisions.py` | panel + Analyst key | does the M-Score at a date predict later revisions of on-file history? |
