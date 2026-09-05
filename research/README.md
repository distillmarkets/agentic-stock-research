# Research

One worked example, kept whole so the loop a study goes through is copyable: a
study, the adversarial review that broke two of its claims, and the
pre-registered re-run that reports the corrected range.

| folder | what a reader gets from it |
|---|---|
| [`pre-exit-signature/`](pre-exit-signature/) | the study: exit base rates per distress state, the eight-quarter signature, and the placebo it first published |
| [`review-pre-exit/`](review-pre-exit/) | the review: what reproduced, what was right only because two errors cancelled, and two defects in a shared null helper |
| [`pre-exit-signature-v2/`](pre-exit-signature-v2/) | the re-run, specified before it ran: the base rate as a range over exit definitions, every placebo under the repaired helper |

Inputs are `cache/panel.csv` from
[`examples/fetch_panel.py`](../examples/fetch_panel.py) on a Pro key, the Stooq
daily bundle unpacked where `STOOQ_DIR` points, and
`pre-exit-signature/probe_delisted.py` for the 150 cached probe responses. Run
each folder's `study.py` from the repository root in that order, the re-run
under `DISTILL_OFFLINE=1`. A script a findings document cites and this checkout
no longer carries is held by the publisher and available on request (open an issue at
https://github.com/distillmarkets/agentic-stock-research/issues).
Start a new study from [`../templates/study/`](../templates/study/) and follow
[`../AGENTS.md`](../AGENTS.md).

General information from public SEC filings, not financial product advice. See
the [disclosure](../README.md#disclosure).
