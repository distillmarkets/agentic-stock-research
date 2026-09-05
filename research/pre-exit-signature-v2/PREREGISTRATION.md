# Pre-registration: `pre-exit-signature-v2`

Written before `study.py` was run. Every table below is specified here first;
the study fills the cells and nothing else. Where a reviewer verdict is accepted
it is named as accepted; where it is contested the contest is named with the
number that would settle it.

Vintage: `cache/panel.csv`, `screen/export` 2026-09-03, final quarter 2026-06-30.
Prices: `cache/stooq_us/` through 2026-08-14, used only to mark a ticker priced.
API: **zero uncached calls**. `distill_toolkit.client.get` is replaced by a
raiser before any import that could reach it; the 150 probe responses are read
from `cache/research/pre-exit-signature/probe_delisted.csv`.

## Accepted from the review without contest

1. The base-rate deliverable is anchor-dependent and must be published as a
   range, not a point.
2. The signature's matching cell gains sector.
3. "Eight of eleven metrics at 82% to 103%" is wrong; the count is seven and the
   band moves once sector is matched.
4. `clustered_shuffle` was defective; every z is recomputed under the shipped
   fix (CORRECTIONS 16 and 18) and the null is construction-dependent.
5. The Altman-Z-trend split is not an exit-type finding.
6. The mixed-cause caveat belongs on every table.
7. `study.py:473`'s "46%" is wrong; the panel value is 43.93%.

## Tables to be filled

### T1. Universe, exit definition, Stooq match rate
Rows: firm-quarters, distinct CIKs, exited CIKs, unpriced CIKs that exited.
Prediction: reproduces v1 exactly (190,586 / 6,103 / 2,555 / 11.43% / 79.26%).

### T2. Probe
150 sampled exited CIKs; same-CIK share, `delistedAt` share, drop-minus-delisted
lag, refresh-minus-delisted lag, the count with no `delistedAt` and the count
that still file. Prediction: reproduces v1 exactly.

### T3. Base rate under six exit definitions (the headline range)
Columns: Altman Z < 1.8, interest coverage < 1, FCF < 0 and revenue falling,
Piotroski <= 2, two or more, none of the four, any firm-quarter; whole panel and
priced subset for each. Definitions:

| tag | anchor | stale rows after `fresh_qi` |
|---|---|---|
| A | last panel row (v1) | kept |
| B | last record refresh | kept |
| C | last record refresh | dropped |
| D | last panel row | dropped |
| E | C minus the 11 probe CIKs with no `delistedAt` | dropped |
| F | last record refresh + 2 quarters (probe-calibrated) | dropped |

Headline stated as a range with C as the corrected reference and F as the
probe-calibrated point. Prediction (from the review, to be confirmed):
9.83% to 26.60%, C = 18.81%, F = 15.21%, and A = 18.49% right by cancellation.

### T4. What survives the anchor change
Ordering (every distress state above the healthy state in all six definitions),
lift over the healthy state, whole-over-priced ratio, horizon sweep at h = 4, 8,
12, and the out-of-sample split at the median anchor year, all under C.

### T5. The 7.8% still-filing bound
(a) the exact move from dropping the 11 named probe CIKs; (b) removing 7.8% of
exit CIKs at random, 200 draws, mean and sd of the corrected Altman cell and of
the unconditional rate.

### T6. Signature, sector in the matching cell
Level gap at t-8 and t-1 with a firm-clustered 95% interval, the share of the
t-1 gap present at t-8, and the difference in differences at each of t-7..t-1,
for eleven metrics, under `keys=(anchor, terc, sector)`. Reported next to the
tercile-only cell. Seed stability of every "first significant quarter" over five
control-draw seeds. The share of rows whose change from t-8 is exactly zero at
t-7, t-6, t-5 and t-4, and the count of metrics whose DiD is exactly
0.000 [0.000, 0.000] at t-7 and t-6.

Pre-registered readings to be confirmed or refuted:
Altman Z DiD at t-1 about -0.35 [-0.51, -0.18]; asset growth about -0.036; both
first separate at t-4; interest coverage separates in 3 of 5 seeds and is
reported as unstable; FCF margin, Piotroski, accruals and net dilution never
separate; "level not slope" is seven of eleven at 72% to 115%.

### T7. Placebos
On the corrected (C) frame and on the v1 (A) frame, 200 draws each:
(a) `analysis.clustered_shuffle(within=year)` as shipped after CORRECTIONS 18;
(b) the reviewer's `cell_mean_shuffle`, no-drop, cell-mean construction;
(c) `analysis.within_firm_shuffle` on the state flag.
Report observed lift, null mean and sd, z and the ratio to the null's 95th
percentile for every state under every construction, and state plainly that the
null is construction-dependent. The reviewer's cell-mean z of 5.1 on the Altman
cell of the A frame is quoted beside ours.

### T8. Did not survive
The Altman-Z-trend split, with the survivor placebo: the share of matched
survivor anchors whose four-quarter Z change is positive against the same share
at exits. Kept to one paragraph. Prediction: 42.0% against 41.9%.

### T9. Coverage
Altman Z null share on the universe (predicted 43.93%), interest coverage null
share (predicted 30.01%), and the per-sector Altman coverage table showing zero
in Financials and Real Estate.

## Stopping rules

- No table is added after the first run. If a number refutes a pre-registered
  reading, the reading is rewritten and the refutation is stated.
- Every table carries "leaving the panel is leaving the corpus, not failing".
- No return is computed anywhere, so there is nothing to market-adjust; the
  price file is used only to mark a ticker priced, and the match rate is
  reported on the full universe denominator.

## Disclosure

Distill Markets Pty Ltd, the publisher of this repository, operates the paid data service this study uses. Authors and the publisher may hold positions in securities of the kind described. Everything above is general information derived from public SEC filings and from a price file the author holds. It is not financial product advice, does not consider your objectives, financial situation or needs, and past patterns do not guarantee future results. See [NOTICE](../../NOTICE).
