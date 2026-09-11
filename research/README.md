# Research

Worked examples, kept whole so the loop a study goes through is copyable.

**The loop:** a study, the adversarial review that broke two of its claims, and
the pre-registered re-run that reports the corrected range.

| folder | what a reader gets from it |
|---|---|
| [`pre-exit-signature/`](pre-exit-signature/) | the study: exit base rates per distress state, the eight-quarter signature, and the placebo it first published |
| [`review-pre-exit/`](review-pre-exit/) | the review: what reproduced, what was right only because two errors cancelled, and two defects in a shared null helper |
| [`pre-exit-signature-v2/`](pre-exit-signature-v2/) | the re-run, specified before it ran: the base rate as a range over exit definitions, every placebo under the repaired helper |

**What the record carries, and what it does not:** two studies about the data
itself rather than about a return, each with its review.

| folder | what a reader gets from it |
|---|---|
| [`listing-end/`](listing-end/) | how long after a firm's last point-in-time row its listing ends, and what its final row looks like against survivors |
| [`review-listing-end/`](review-listing-end/) | the review of it: which timing claims held, which final-row claim was trimmed, and the match rate the first draft left out |
| [`naming-the-dead/`](naming-the-dead/) | whether a filer can be named at all: 88.7% of listed filers against 1 of 3,104 whose listing has ended, and the 12.4% of ticker-keyed name lookups that return a different company |
| [`review-naming-the-dead/`](review-naming-the-dead/) | the review of it: the cohort the headline was measured on was not what its label said, and SEC's own per-CIK file answers a question the free bulk file cannot |

Inputs are `cache/panel.csv` from
[`examples/fetch_panel.py`](../examples/fetch_panel.py) on a Pro key or the
published 200-firm sample (README, Install), the Stooq daily bundle unpacked
where `STOOQ_DIR` points, the SEC's `company_tickers.json` where `SEC_TICKERS`
points ([docs/data-sources.md](../docs/data-sources.md) has the fetch), and
`pre-exit-signature/probe_delisted.py` for the 150 cached probe responses. Run
each folder's `study.py` from the repository root, the re-runs under
`DISTILL_OFFLINE=1`. A script a findings document cites and this checkout
no longer carries is held by the publisher and available on request (open an issue at
https://github.com/distillmarkets/agentic-stock-research/issues).
Start a new study from [`../templates/study/`](../templates/study/) and follow
[`../AGENTS.md`](../AGENTS.md).

General information from public SEC filings, not financial product advice. See
the [disclosure](../README.md#disclosure).
