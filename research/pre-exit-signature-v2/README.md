# The pre-exit signature, corrected: the base rate is a range, not a point

Version 2 of [`../pre-exit-signature/`](../pre-exit-signature/). It applies the
verdicts in [`../review-pre-exit/README.md`](../review-pre-exit/README.md) unless
a number here shows a verdict wrong, publishes the base-rate deliverable as a
range over exit definitions rather than as a point, adds sector to the
signature's matching cell, and
recomputes every placebo under the repaired `clustered_shuffle`
(`CORRECTIONS.md` entries 16, 18 and 19).

Every table below is specified in `PREREGISTRATION.md`, written before
`study.py` was run. No table was added afterwards.

Reproduce with:

```
./.venv/bin/python research/pre-exit-signature-v2/study.py
```

**Uncached API calls: 0.** `distill_toolkit.client.get` is replaced by a raiser
before any other import, so a run that reaches its last line made none.

**Leaving the panel is leaving the corpus, not failing: acquisition, going
private, deregistration, exchange deficiency and bankruptcy arrive as one event.
That sentence belongs on every table in this document, and it is repeated under
each one.**

---

## Question

Three questions, all inside the filing record and with no return computed anywhere.

1. What is a firm-quarter in an observable distress state worth as a base rate for
   leaving the SEC filing record within eight quarters, **once the exit anchor is
   treated as a choice rather than as a fact**, and how far apart do defensible
   choices put it.
2. Over the eight quarters before the record goes stale, which of eleven filed
   metrics separate from survivors matched on calendar quarter, revenue tercile
   **and sector**, and from which quarter.
3. Do those base rates clear a placebo once the between-firm null is the repaired
   one, and which state is the weakest.

The v1 study answered all three; the adversarial review found the deliverable was
right by cancellation, the "eight of eleven" count was seven, one "never
separates" metric separates under sector matching, and the between-firm null was
computed by a defective helper. This study is the rerun.

## Data vintage

| source | vintage | used for |
|---|---|---|
| `cache/panel.csv` | `screen/export`, panel vintage 2026-09-03, final quarter 2026-06-30, 206,957 rows | everything |
| `cache/stooq_us/` | Stooq US daily bundle through 2026-08-14 | marking a ticker priced or not, nothing else |
| `cache/research/pre-exit-signature/probe_delisted.csv` | 150 `/sec/fundamentals/{t}/as-of/2026-09-03` responses cached 2026-09-04 by v1 | `delistedAt` for a sample of exited CIKs |

**No return is computed anywhere in this study, so there is nothing to
market-adjust.** The only price-derived quantity is the match rate, which is
reported on the full universe denominator.

## Method

**Universe.** Panel rows with `is_listed_equity`, `revenue > 0`, and a ticker that
maps to exactly one CIK anywhere in the export. **n = 190,586 firm-quarters over
6,103 CIKs**, 2009Q2 to 2026Q2. Constructors are imported from v1
(`load_frames`, `states`, `build_anchors`, `build_trajectories`, `section_exits`,
`section_probe`) and from the review (`base_table`, `build_anchors_keyed`,
`level_table`, `did_table`, `first_sig`, `cell_mean_shuffle`), never copied, so a
reproduction failure here would be a real one.

**Exit.** A CIK exits when its last panel row is at least eight quarters before
the panel's final quarter. **n = 2,555 exits (41.86% of CIKs)**, 3,548 still
present.

**The anchor is the study's main variable.** `fresh_qi` is the first quarter
carrying a CIK's final fiscal year, that is the last quarter at which a new annual
filing refreshed the row. `last_qi` is the last panel row, which is a drop date
produced by a staleness rule. Six exit definitions are run side by side (A to F,
below); the deliverable is the range across them.

**Matching.** Each exit with eight quarters of history before its anchor
(**n = 1,688 CIKs**) is matched to three survivor firm-quarters from the same
calendar quarter, the same revenue tercile **and the same sector**.
**n = 5,064 control anchors over 1,914 CIKs**, 0 exits unmatched. Intervals are a
firm-clustered bootstrap, 300 draws; placebos are 200 draws.

### Stooq match rate, on the honest denominator

| denominator | n | with a Stooq series |
|---|---|---|
| firm-quarters | 190,586 | **66.34%** |
| distinct CIKs | 6,103 | **53.22%** |
| **exited CIKs** | **2,555** | **11.43%** |
| unpriced CIKs that exited | 2,855 | 79.26% |

**88.57% of exited CIKs carry no price series at all.** Every priced-subset number
below is a floor computed on a nine-in-ten-missing denominator, and nothing in
this data bounds by how much. This reproduces v1 and the review exactly.

---

## Result

### 1. The universe, the exits and the probe reproduce v1 exactly

2,555 exits, 41.86% of CIKs, roughly 200 a year from 2013 on: 230, 224, 183, 213,
219, 190, 196, 214, 190, 192, 226, 224 for panel-drop years 2013 to 2024. 2011 (8)
and 2012 (46) sit inside the panel's coverage ramp. **72.8% of drops fall in a
June quarter** (Q1 195, Q2 1,860, Q3 137, Q4 363), and the gap between the last
record refresh and the drop is a median 5 quarters for exits (mean 4.57, IQR 4 to
5) against a median 1 for CIKs still present. 74% of exits carry a last row whose
`as_of` year is two years past its `fiscal_year`. The last panel row is a drop
date, not a filing date.

Probe, 150 sampled exited CIKs, at most one call per CIK, all cached:

- 141 of 150 (94.0%) resolve to the panel's own CIK; 9 (6.0%) resolve to another,
  which is ticker recycling.
- 130 of 141 (92.2%) carry a `delistedAt`.
- The panel's last row **follows** `delistedAt` for 93.1% of the 130, median
  **+2.92 quarters** (IQR +2.00 to +4.22).
- The last record refresh **precedes** `delistedAt` for 93.8% of the 130, median
  **1.83 quarters** (IQR +0.71 to +3.00).
- 11 of 141 (**7.8%**) carry no `delistedAt`; **8 of 141 (5.7%)** of those hold an
  annual filing dated 2026-02-27 or later and so still file. Both counts travel
  together, and the binomial 95% interval on 11 of 141 is roughly +/- 4.4pp.

The probe reads a date and never a reason. *Leaving the panel is leaving the
corpus, not failing.*

### 2. The deliverable is a range: the exit anchor moves it by a factor of 2.7

Base frame: **137,787 firm-quarters over 5,499 CIKs**, anchors 2009 to 2022Q2.
**9,664 of those rows (7.01%) fall after their CIK's last record refresh; all
9,664 belong to an exiting CIK and none to a survivor.** In the Altman Z < 1.8
cell those repeats are 9.6% of 27,919 rows and **51.9% of the 5,161 rows labelled
as exiting under the v1 anchor, and 100.0% of them are positive by construction.**

| tag | anchor | rows after `fresh_qi` | n |
|---|---|---|---|
| A | last panel row (v1) | kept | 137,787 over 5,499 CIKs |
| B | last record refresh | kept | 137,787 over 5,499 CIKs |
| **C** | **last record refresh** | **dropped** | **128,123 over 5,499 CIKs** |
| D | last panel row | dropped | 128,123 over 5,499 CIKs |
| E | C minus the 11 probe CIKs with no `delistedAt` | dropped | 128,010 over 5,488 CIKs |
| F | last refresh + 2 quarters (probe-calibrated) | dropped | 128,123 over 5,499 CIKs |

Share of firm-quarters in each state whose CIK stops filing within eight quarters,
**whole panel**:

| state | n (A, B) | n (C, D, F) | A | B | **C** | D | E | F |
|---|---|---|---|---|---|---|---|---|
| Altman Z < 1.8 | 27,919 | 25,240 | 18.49% | 26.60% | **18.81%** | 9.83% | 18.74% | 15.21% |
| interest coverage < 1 | 31,604 | 28,422 | 19.59% | 27.60% | **19.50%** | 10.58% | 19.38% | 15.77% |
| FCF margin < 0 and revenue falling | 8,293 | 7,623 | 17.87% | 26.14% | **19.65%** | 10.65% | 19.66% | 15.77% |
| Piotroski <= 2 | 17,472 | 15,824 | 18.59% | 26.10% | **18.40%** | 10.11% | 18.38% | 14.89% |
| two or more of the four | 22,156 | 19,880 | 20.48% | 29.20% | **21.09%** | 11.37% | 21.01% | 17.03% |
| none of the four | 81,292 | 76,820 | 10.00% | 14.40% | **9.42%** | 4.76% | 9.40% | 7.52% |
| any firm-quarter | 137,787 | 128,123 | 13.21% | 18.90% | **12.79%** | 6.66% | 12.75% | 10.27% |

**Priced subset only**, same cells, same n on the priced denominator (13,122 of
25,240 in the Altman cell under C; 82,610 of 128,123 overall):

| state | A | B | **C** | D | E | F |
|---|---|---|---|---|---|---|
| Altman Z < 1.8 | 3.55% | 4.91% | **3.10%** | 1.72% | 3.00% | 2.51% |
| interest coverage < 1 | 4.65% | 6.63% | **4.59%** | 2.57% | 4.38% | 3.68% |
| FCF margin < 0 and revenue falling | 3.16% | 5.47% | **4.17%** | 1.82% | 4.08% | 2.96% |
| Piotroski <= 2 | 3.93% | 5.20% | **3.44%** | 2.16% | 3.38% | 2.89% |
| two or more of the four | 4.53% | 6.55% | **4.54%** | 2.47% | 4.36% | 3.60% |
| none of the four | 1.62% | 2.20% | **1.36%** | 0.79% | 1.36% | 1.11% |
| any firm-quarter | 2.33% | 3.22% | **2.08%** | 1.18% | 2.04% | 1.68% |

*Leaving the panel is leaving the corpus, not failing.*

Firm-clustered 95% intervals under C: Altman Z < 1.8 whole panel
18.81% [17.63, 20.11] and priced 3.10% [2.33, 3.74]; any firm-quarter
12.79% [12.28, 13.31] and 2.08% [1.82, 2.36]. Every cell's interval is in
`base_variant_{A..F}.csv`.

**The headline.** Per `PREREGISTRATION.md`, **C is the corrected reference and F
is the probe-calibrated point**. The honest statement is:

> A firm-quarter with an Altman Z below 1.8 stops filing within eight quarters
> **between 9.83% and 26.60% of the time across four defensible exit definitions
> (A to D), 18.81% under the corrected definition C, and 15.21% under the
> probe-calibrated definition F**, on n = 25,240 to 27,919 firm-quarters. The
> priced subset reports 1.72% to 4.91% for the same cell.

**v1 published 18.49%, and it was right by cancellation, not by method.**
Re-anchoring on the last record refresh alone moves the cell **+8.12pp**; dropping
the stale repeats alone moves it **-8.65pp**; doing both moves it **+0.33pp**. A
study that fixed only one of the two would have published a number 8pp wrong while
looking like it had improved the method.

### What survives the anchor change

- **Ordering** holds in all six definitions: every distress state sits above the
  healthy state, whole panel and priced subset.
- **Lift over the healthy state** for the Altman cell: 1.85x (A), 1.85x (B),
  2.00x (C), 2.07x (D), 1.99x (E), 2.02x (F).
- **Whole-panel over priced ratio** for the Altman cell: 5.20x, 5.42x, 6.06x,
  5.71x, 6.25x, 6.07x; for any firm-quarter: 5.66x, 5.88x, 6.15x, 5.62x, 6.26x,
  6.11x. Across the states under C the ratio runs **4.25x to 6.90x**, and the
  largest ratio is still on the healthiest state.
- **Horizon sweep**, v1 anchor against corrected C, whole panel / priced subset.
  *Leaving the panel is leaving the corpus, not failing.*

| h | state | n (C) | v1 anchor A | corrected C |
|---|---|---|---|---|
| 4 | Altman Z < 1.8 | 28,371 | 10.40% / 2.09% | 11.05% / 1.75% |
| 4 | two or more of the four | 22,137 | 11.68% / 2.57% | 12.69% / 2.55% |
| 4 | any firm-quarter | 140,780 | 7.68% / 1.40% | 7.52% / 1.24% |
| 8 | Altman Z < 1.8 | 25,240 | 18.49% / 3.55% | 18.81% / 3.10% |
| 8 | two or more of the four | 19,880 | 20.48% / 4.53% | 21.09% / 4.54% |
| 8 | any firm-quarter | 128,123 | 13.21% / 2.33% | 12.79% / 2.08% |
| 12 | Altman Z < 1.8 | 22,284 | 25.94% / 5.05% | 26.11% / 4.38% |
| 12 | two or more of the four | 17,602 | 28.76% / 6.73% | 28.75% / 6.36% |
| 12 | any firm-quarter | 115,800 | 18.24% / 3.16% | 17.54% / 2.80% |

- **Out of sample**, splitting anchors at the median year, h = 8, whole / priced.
  *Leaving the panel is leaving the corpus, not failing.*

| split | state | n (C) | v1 anchor A | corrected C |
|---|---|---|---|---|
| 2009-2015 | Altman Z < 1.8 | 8,657 | 17.91% / 3.97% | 19.08% / 3.76% |
| 2009-2015 | two or more of the four | 6,625 | 21.54% / 4.09% | 23.03% / 4.95% |
| 2009-2015 | any firm-quarter | 52,021 | 12.79% / 2.24% | 13.04% / 2.20% |
| 2016-2022 | Altman Z < 1.8 | 16,583 | 18.78% / 3.38% | 18.67% / 2.84% |
| 2016-2022 | two or more of the four | 13,255 | 19.95% / 4.69% | 20.12% / 4.38% |
| 2016-2022 | any firm-quarter | 76,102 | 13.49% / 2.39% | 12.61% / 2.01% |

Every state keeps its sign and its order in both halves under both anchors.

### The still-filing bound

The probe says 7.8% of sampled exits carry no served `delistedAt` and 5.7% still
file. Applied two ways, on the corrected frame C (n = 128,123). *Leaving the panel
is leaving the corpus, not failing.*

| application | Altman Z < 1.8 | two or more | none of the four | any firm-quarter |
|---|---|---|---|---|
| C, as published | 18.81% | 21.09% | 9.42% | 12.79% |
| minus the 11 named probe CIKs (definition E) | 18.74% (**-0.070pp**) | 21.01% | 9.40% | 12.75% (-0.035pp) |
| minus 7.8% of exit CIKs at random, 200 draws | **17.36% +/- 0.161** | 19.46% +/- 0.187 | 8.68% +/- 0.061 | **11.79% +/- 0.036** |

Eleven CIKs are 0.4% of the 2,555 exits, so a named-CIK drop cannot carry the
probe's rate; the rate has to be applied as a bound. **The bound costs the Altman
cell about 1.45pp and the unconditional rate about 1.00pp**, which is small next
to the 2.7-fold anchor range and is not the study's main uncertainty.

### 3. The sector-matched signature: a level, not a slope, on seven of eleven

Adding the panel's own sector at the anchor row to the matching cell costs
nothing: **1,688 exits, 0 unmatched, 5,064 controls over 1,914 CIKs** (1,936 under
the tercile-only cell), and the sector total-variation distance between the two
cohorts falls from **0.107 to 0.000**. The keyed sampler reproduces v1's
`build_anchors` exactly.

**Levels.** Median gap at t-8 and t-1, exits minus matched survivors, firm-clustered
95% interval, sector in the cell. `at t-8` is the share of the t-1 gap already on
file two years out. *Leaving the panel is leaving the corpus, not failing.*

| metric | gap at t-8 | gap at t-1 | at t-8 | n exit / control at t-1 |
|---|---|---|---|---|
| revenue growth | -0.025 [-0.035, -0.011] | -0.031 [-0.042, -0.023] | 83% | 1,631 / 4,992 |
| operating margin | -0.037 [-0.044, -0.028] | -0.048 [-0.058, -0.039] | 77% | 1,615 / 4,936 |
| FCF margin | -0.029 [-0.037, -0.021] | -0.025 [-0.035, -0.017] | 115% | 1,050 / 3,239 |
| interest coverage | -1.707 [-2.146, -1.202] | -2.340 [-3.053, -1.817] | 73% | 1,169 / 3,439 |
| Altman Z | -1.661 [-2.171, -1.272] | -1.919 [-2.329, -1.449] | 87% | 909 / 3,075 |
| Piotroski F | -0.258 [-0.384, -0.150] | -0.356 [-0.480, -0.234] | 72% | 1,467 / 4,402 |
| M-Score (5 var) | +0.001 [-0.033, +0.031] | -0.040 [-0.070, -0.004] | -2% | 1,476 / 4,428 |
| accruals ratio | -0.012 [-0.018, -0.005] | -0.016 [-0.025, -0.009] | 75% | 1,154 / 3,463 |
| asset growth | -0.024 [-0.033, -0.013] | -0.045 [-0.056, -0.036] | 53% | 1,673 / 5,034 |
| net dilution | +0.001 [-0.000, +0.003] | +0.001 [-0.000, +0.003] | 105% | 1,186 / 3,611 |
| DSO | +0.589 [-1.886, +3.118] | -2.135 [-5.084, +0.444] | -28% | 1,442 / 4,467 |

**"Level not slope" is seven of eleven at 72% to 115%, not eight at 82% to 103%.**
Counting v1's own tercile-only column the metrics inside 80% to 105% are **seven**
(revenue growth 82%, operating margin 87%, FCF margin 103%, interest coverage 88%,
Altman Z 93%, Piotroski 87%, accruals 87%). With sector in the cell **those same
seven run 72% to 115%**, and only **2 of 11** metrics remain inside 80% to 105%.
The direction survives; the count and the band do not. v1's claim is withdrawn and
replaced by this sentence.

**Difference in differences.** Each anchor's change from its own t-8, exits minus
controls, sector in the cell. A star means the 95% interval excludes zero.
*Leaving the panel is leaving the corpus, not failing.*

| metric | first separating quarter | t-4 | t-1 | n exit / control at t-1 |
|---|---|---|---|---|
| revenue growth | **t-5** | -0.011* | -0.024* | 1,278 / 4,120 |
| Altman Z | **t-4** | -0.148* | **-0.352** [-0.511, -0.177] | 781 / 2,672 |
| asset growth | **t-4** | -0.017* | **-0.036** [-0.053, -0.023] | 1,589 / 4,911 |
| M-Score (5 var) | **t-4** | -0.022* | -0.047* | 1,418 / 4,353 |
| interest coverage | **t-4 (unstable)** | -0.181* | -0.237 [-0.490, +0.015] | 1,035 / 3,141 |
| operating margin | t-3 | -0.002 | -0.010* | 1,536 / 4,794 |
| DSO | t-1 | +0.055 | -0.513* | 1,370 / 4,348 |
| FCF margin | never | -0.002 | -0.006 | 855 / 2,733 |
| Piotroski F | never | -0.086 | -0.091 | 1,405 / 4,308 |
| accruals ratio | never | +0.000 | +0.001 | 956 / 2,968 |
| net dilution | never | +0.000 | +0.001 | 1,008 / 3,231 |

Under the tercile-only cell the same table gives Altman Z first at t-4 with a t-1
value of -0.274, asset growth first at t-4 at -0.038, operating margin first at
t-1, M-Score first at t-3, and interest coverage **never**. So sector matching
moves **interest coverage from never to t-4**, **operating margin from t-1 to
t-3** and **M-Score from t-3 to t-4**, and leaves FCF margin, Piotroski, accruals
and net dilution never separating under either cell.

**Interest coverage is reported as unstable, not as a finding.** Over five
control-draw seeds (7, 11, 13, 17, 23) its first separating quarter is t-4, t-2,
never, t-4, never, so **3 of 5**, with t-1 values -0.237, -0.262, -0.148, -0.239,
-0.201. Altman Z separates in **5 of 5 seeds, always at t-4** (t-1 values -0.352,
-0.300, -0.234, -0.309, -0.317), and asset growth in **5 of 5, always at t-4**
(-0.036, -0.032, -0.036, -0.036, -0.033). One seed puts Altman Z's first
separation at t-3 rather than t-4 in the printed seed line for seed 17; the count
of seeds in which it separates is 5 of 5 either way.

**t-4 is close to the earliest quarter this design can answer.** The statistic is
each anchor's change from its own t-8 value, and the panel's metrics refresh once
a fiscal year, so that change is exactly zero for most rows early in the window:

| share of rows whose change from t-8 is exactly zero | t-7 | t-6 | t-5 | t-4 |
|---|---|---|---|---|
| Altman Z | 90.2% | 75.3% | 12.8% | 0.8% |
| asset growth | 90.8% | 76.8% | 11.8% | 0.4% |
| operating margin | 90.6% | 76.5% | 11.9% | 0.7% |
| revenue growth | 90.4% | 75.9% | 9.3% | 0.0% |
| Piotroski F | 90.7% | 78.7% | 28.6% | 19.0% |

**Ten of the eleven metrics have a difference in differences of exactly
0.000 [0.000, 0.000] at t-7, and ten of eleven again at t-6.** The early part of
the trajectory is a structural zero produced by annual refresh, not a measured
null, and the helper now raises a `RuntimeWarning` on that tied statistic
(`CORRECTIONS.md` entry 17). "Separates at t-4" therefore means "one annual filing
before the last one on file", and the design cannot resolve finer.

### 4. Placebos: the null is construction-dependent, and one state does not clear

The statistic is the **lift**: a state's exit rate minus the exit rate over all
firm-quarters in the same frame. Three constructions of the same null, 200 draws
each. *Leaving the panel is leaving the corpus, not failing.*

- **shuffle**: `analysis.clustered_shuffle(within=year)` as shipped after
  `CORRECTIONS.md` entries 16 and 18. The exit label moves between firms, each
  firm carries its whole label path, the partner's cell is walked in order, and a
  row whose partner has no cell at its key takes the partner's label at its
  nearest key. **No row is dropped**, so the shuffled and observed rates share a
  denominator.
- **cell mean**: the review's `cell_mean_shuffle`. Also drops nothing; smooths the
  label's within-firm persistence rather than keeping it.
- **within firm**: `analysis.within_firm_shuffle` on the state flag. Keeps every
  firm-level property and destroys only the timing inside a firm's own history.

**On v1's frame and anchor (definition A), n = 137,787 firm-quarters over 5,499
CIKs, overall rate 13.21%.** These are the repaired-shuffle numbers recorded in
`CORRECTIONS.md` entries 18 and 19, reproduced here state by state and null by
null.

| state | n | observed lift | nearest-key shuffle null | z | x p95 | cell-mean null | z | within-firm null | z |
|---|---|---|---|---|---|---|---|---|---|
| Altman Z < 1.8 | 27,919 | +5.28pp | +1.66 +/- 1.01 | **3.6** | 1.6 | +0.63 +/- 0.91 | 5.1 | +4.10 +/- 0.08 | 14.3 |
| interest coverage < 1 | 31,604 | +6.38pp | +1.46 +/- 0.81 | 6.1 | 2.3 | +0.49 +/- 0.74 | 8.0 | +5.02 +/- 0.08 | 16.4 |
| FCF margin < 0 and revenue falling | 8,293 | +4.67pp | +2.50 +/- 1.34 | **1.6** | **1.0** | +0.88 +/- 1.17 | 3.2 | +1.28 +/- 0.25 | 13.3 |
| Piotroski <= 2 | 17,472 | +5.38pp | -0.20 +/- 0.80 | 6.9 | 3.5 | +0.05 +/- 0.75 | 7.1 | +5.07 +/- 0.16 | **2.0** |
| two or more of the four | 22,156 | +7.27pp | +1.65 +/- 0.99 | 5.7 | 2.2 | +0.61 +/- 0.89 | 7.5 | +5.40 +/- 0.13 | 14.8 |
| none of the four | 81,292 | -3.20pp | -0.70 +/- 0.40 | -6.2 | 2.4 | -0.26 +/- 0.36 | -8.1 | -2.65 +/- 0.04 | -14.7 |

**What v1 published is withdrawn.** The null lift bound moves from "at or below
+0.24pp +/- 0.96 on every state" to **at or below +2.50pp +/- 1.34**; the observed
lifts move from **z = 4.6 to 12.2** to **z = 1.6 to 6.9**; and "every observed lift
is more than 2.4 times the 95th percentile of the absolute shuffled lift" becomes
**1.0 to 3.5 times**. **The state "FCF margin below zero and revenue falling",
+4.67pp on 137,787 firm-quarters over 5,499 CIKs, no longer clears its between-firm
null**: 1.0 times the 95th percentile of the absolute shuffled lift, z = 1.6. The
other five clear at 1.6x to 3.5x. This is `CORRECTIONS.md` entry 19.

**The null is construction-dependent.** Four constructions of the same Altman null
on the same +5.28pp lift, recorded in `CORRECTIONS.md` entry 19:

| construction | null | z |
|---|---|---|
| nearest-key shuffle, shipped | +1.66 +/- 1.01pp | **3.6** |
| the review's cell mean | +0.63 +/- 0.91pp | **5.1** |
| published helper, dropping 42% of rows (withdrawn) | +0.06 +/- 0.59pp | **8.8** |
| the first repair, pool draw (withdrawn) | +0.24 +/- 0.42pp | **12.0** |

The first two are reproduced in this study's own frame-A table above; the 8.8 and
the 12.0 are the two withdrawn constructions recorded in `CORRECTIONS.md` entries
18 and 19. The width of a between-firm null is decided by how it treats the rows
an unbalanced panel cannot pair, and a z from this family is a statement about a
construction as much as about the data.

**On the corrected frame and anchor (definition C), n = 128,123 firm-quarters over
5,499 CIKs, overall rate 12.79%.** These rows are in `placebo.csv`. *Leaving the panel is leaving the corpus, not failing.*

| state | n | observed lift | nearest-key shuffle null | z | x p95 | cell-mean z | within-firm z | within x p95 |
|---|---|---|---|---|---|---|---|---|
| Altman Z < 1.8 | 25,240 | +6.02pp | +1.43 +/- 1.19 | 3.9 | 1.8 | 4.9 | 16.0 | 1.24 |
| interest coverage < 1 | 28,422 | +6.71pp | +1.36 +/- 0.95 | 5.7 | 2.4 | 7.1 | 15.4 | 1.23 |
| FCF margin < 0 and revenue falling | 7,623 | +6.86pp | +2.30 +/- 1.47 | 3.1 | 1.5 | 4.4 | 17.7 | 2.22 |
| Piotroski <= 2 | 15,824 | +5.61pp | -0.15 +/- 0.93 | 6.2 | 3.4 | 6.2 | **0.5** | **0.97** |
| two or more of the four | 19,880 | +8.30pp | +1.52 +/- 1.11 | 6.1 | 2.5 | 7.4 | 15.1 | 1.28 |
| none of the four | 76,820 | -3.37pp | -0.61 +/- 0.45 | -6.2 | 2.6 | -7.5 | -17.5 | 1.20 |

Two things change when the frame is corrected. **The FCF-and-falling-revenue state
clears on frame C** (z = 3.1, 1.5 times the 95th percentile) where it fails on
frame A (z = 1.6, 1.0 times), because dropping the stale repeats raises its
observed lift from +4.67pp to +6.86pp. **Piotroski <= 2 stops clearing the
within-firm null on frame C**: z = 0.5 and 0.97 times the 95th percentile, against
z = 2.0 on frame A. The state that fails is therefore anchor-dependent too, and the
honest summary is that **one of the six states fails one of the three nulls under
each frame, and it is a different state in each case.**

**The within-firm null is the stronger test and it is the one to read.** It permutes
each firm's own state flag across its own quarters, so it keeps every firm-level
property and destroys only the timing. It is far harder to clear because most of a
state's information is about *which firm* rather than *which quarter*: on frame A it
reproduces **+4.10pp of the +5.28pp** Altman lift, **+5.02 of +6.38** for interest
coverage and **+5.07 of +5.38** for Piotroski, and on frame C **+4.70 of +6.02**,
**+5.30 of +6.71** and **+5.54 of +5.61**. It does not call `clustered_shuffle` and
so is untouched by `CORRECTIONS.md` entries 16 and 18. Against it, Altman Z,
interest coverage, the two-or-more state and the healthy state clear at z of 15 to
18 in absolute value on frame C, and **Piotroski <= 2 does not clear at all**
(z = 0.5): knowing which firm you are looking at reproduces essentially the whole
Piotroski lift, and the quarter adds nothing.

### 5. Did not survive: the Altman-Z-trend split is not an exit-type proxy

v1 split its exits on whether the last reading of Altman Z was above or below the
one four quarters earlier and read the falling group as distressed exits and the
rising group as orderly ones. **That reading is withdrawn.** *Leaving the panel is
leaving the corpus, not failing.*

| cohort | n classified | four-quarter Z rising |
|---|---|---|
| all exits, at the last refresh | 1,016 | **41.93%** |
| matched exits, at the anchor | 829 | 43.55% |
| matched survivors, at the anchor | 2,782 | **43.17%** |

A rising four-quarter Altman Z is **the survivor base rate**. It appears at
essentially the same share of matched survivor anchors as of exiting filers' last
refreshes, so the split carries no information about whether a firm left in good
order, and it is withdrawn as a finding. The review measured 42.00% on n = 2,736
survivor anchors and 41.93% on n = 1,016 exits, and `PREREGISTRATION.md` predicted
42.0% against 41.9%; the survivor figure here is **43.17% on n = 2,782**, the same
reading on a slightly different anchor set. `charts/ztrend_null.png` carries the
review's 42.0% in its headline rather than the 43.17% in the table on disk, a
difference of 1.2pp.

The split is also a **level** split rather than a trend split: the review measured
a median Altman Z of 0.45 at the anchor for the falling group against 2.71 for the
rising one, with 63.1% against 39.4% sitting below 1.8, so splitting the base-rate
table by Z trend and reading the result is close to reading the Altman Z state
variable twice. No table on disk holds those medians for v2, so the numbers quoted
in this paragraph are the review's.

### 6. Coverage: the strongest metric is missing from two whole sectors

Measured on the 190,586 universe rows, **Altman Z is null on 43.93%** and
**interest coverage on 30.01%**. v1's `study.py` line 473 printed "46%" where v1's
own README said 43.9%; the panel value is 43.93% and the printed 46% has no source
in the frame.

| sector | rows | Altman Z on file | interest coverage on file |
|---|---|---|---|
| Financials | 17,248 | **0.0%** | 74.0% |
| Real Estate | 11,546 | **0.0%** | 71.3% |
| Utilities | 3,843 | 43.7% | 91.9% |
| Energy | 9,504 | 50.4% | 76.6% |
| Materials | 15,259 | 58.8% | 77.1% |
| Consumer Discretionary | 21,110 | 62.8% | 66.4% |
| Industrials | 36,585 | 66.0% | 72.6% |
| Healthcare | 25,905 | 68.6% | 65.0% |
| Communication Services | 9,106 | 68.6% | 74.5% |
| Consumer Staples | 6,894 | 70.0% | 75.0% |
| Technology | 33,586 | 74.9% | 60.8% |

**Altman Z coverage is exactly zero in Financials and Real Estate, which is 28,794
rows, 15.1% of the universe.** The strongest single metric in this study is
unusable for those filers. A state is only true where the metric is on file and a
null never counts as a state, so **every state count in this document is a lower
bound**.

---

## What would break it

1. **The exit date is a staleness rule, not an event, and it is the study's
   largest uncertainty.** 72.8% of drops land in a June quarter, 74% of last rows
   carry a two-year-old fiscal year, and the drop lags the served `delistedAt` by
   a median +2.92 quarters. The deliverable moves by a factor of 2.7 across four
   defensible anchors (9.83% to 26.60%). Publishing a single number requires
   picking one, and this document picks C and states F alongside it.
2. **If the export's retention rule ever changed, the exit-year series would move
   with it** and every study on this panel would read that as a change in the
   world. The rule is reverse-engineered from the shape of the data.
3. **7.8% of sampled exits carry no served `delistedAt` and 5.7% still file**, on
   a 150-CIK sample with a binomial interval of roughly +/- 4.4pp. Applied as a
   bound it costs the Altman cell 1.45pp.
4. **Panel exit is not distress.** Acquisition, going private, deregistration,
   exchange deficiency and bankruptcy produce an identical footprint. Section 5
   tried a proxy for this and the proxy failed.
5. **The between-firm placebo z depends on the construction of the null**, from
   3.6 to 12.0 on the same Altman cell. Any z in section 4 should be read with the
   construction attached, and the within-firm null is the one that binds.
6. **One state fails a null under each frame, and it is a different state.**
   FCF-below-zero-and-revenue-falling fails the between-firm null on frame A;
   Piotroski <= 2 fails the within-firm null on frame C.
7. **Multiplicity.** The trajectory table is 77 intervals at 95% per matching cell,
   so about four spurious exclusions of zero are expected and no correction is
   applied. The interest-coverage separation at t-4 is exactly the size of finding
   that produces, and it appears in 3 of 5 control-draw seeds.
8. **The trajectory cannot resolve below annual granularity.** Ten of eleven
   metrics have a structurally zero difference in differences at t-7 and again at
   t-6, so "t-4" means "one annual filing earlier" and nothing finer.
9. **A third of exits are excluded from the signature.** 33.9% of exits have fewer
   than eight quarters of history before their anchor, and there is no reason to
   think short-lived filers look like the ones the signature can see.
10. **Altman Z is null on 43.93% of universe rows and on two whole sectors.** One
    of the two stable movers is measured on a sector-truncated universe.
11. **The revenue tercile plus sector is the only size control**, because the panel
    row carries no market capitalisation and no share count.
12. **The priced flag is measured in August 2026 and applied back to 2009.** It
    embeds the future relative to every anchor date. Nothing here is a signal that
    could have been formed at the time; it is a description of what a join
    discards. 88.57% of exited CIKs carry no series, so every priced cell is a
    floor.
13. **The re-anchored definition is stricter on exits than on survivors.** The
    review found 218 of 3,548 still-present CIKs (6.1%) have not refreshed since
    2024Q2 and are still counted as non-exits.
14. **6% of probe tickers resolve to a different CIK at the API.** The study joins
    on CIK internally and only the probe touches a ticker, but the same defect
    would corrupt any per-ticker follow-up.

## What changed from v1, one bullet per reviewer verdict

- **"Base rate table: Altman Z < 1.8 to 18.49% whole, 3.55% priced" was survives
  as arithmetic, broken as a measurement.** Accepted. The deliverable is now a
  range across six exit definitions, with C (18.81%) as the corrected reference
  and F (15.21%) as the probe-calibrated point, and the cancellation is stated
  (+8.12pp and -8.65pp netting to +0.33pp).
- **"Between 82% and 103% of the gap on eight of eleven metrics is already there
  at t-8" was broken as stated.** Accepted. It is seven of eleven, and those seven
  run 72% to 115% once sector is in the matching cell; only 2 of 11 stay inside
  80% to 105%.
- **"Interest coverage, FCF margin, Piotroski, accruals and net dilution never
  separate" was broken for interest coverage.** Accepted with the review's own
  caveat: interest coverage first separates at t-4 under sector matching in 3 of 5
  control-draw seeds and is reported as unstable rather than as a finding. The
  other four still never separate.
- **"Altman Z and asset growth separate from t-4" survived with caveats.**
  Accepted. Both separate in 5 of 5 seeds at t-4, and the caveat is now a table:
  90% of rows have a zero change at t-7 and 75% at t-6, so t-4 is close to the
  earliest quarter the design can answer.
- **"Between-firm shuffle null, z = 4.6 to 12.2" survived with caveats.**
  Accepted and superseded. Under the shipped nearest-key shuffle the range is
  z = 1.6 to 6.9 on frame A, the null bound moves from +0.24 to +2.50pp, and the
  "2.4 times the 95th percentile" sentence is withdrawn in favour of 1.0 to 3.5
  times (`CORRECTIONS.md` entry 19).
- **`clustered_shuffle(within=year)` NaNs 42% of rows, plus a second unreported
  defect in the same helper.** Accepted. Both are fixed in the package
  (`CORRECTIONS.md` entries 16 and 18) and every placebo here runs on the shipped
  version, which drops no row; the study asserts that at run time.
- **`cluster_boot_diff` returns 0.000 [0.000, 0.000] on a tied statistic, not on
  an integer dtype.** Accepted. The helper now warns
  (`CORRECTIONS.md` entry 17), the warnings appear in the run log, and the count
  of degenerate cells is published (10 of 11 metrics at t-7 and at t-6).
- **"Almost all of the exit lift a distress state carries is a lift in exits
  preceded by a falling Z" was broken as a reading about exit type.** Accepted.
  The whole Z-trend section is demoted to a did-not-survive paragraph: a rising
  four-quarter Z is the survivor base rate.
- **The matching cell should gain sector.** Accepted. Sector total-variation
  distance falls from 0.107 to 0.000 at no cost in unmatched exits.
- **"Every table carries the left-the-corpus caveat" was broken, three of four
  tables did not.** Accepted. The caveat is printed under every table in the run
  log, appears under every table here, and is in every chart subtitle.
- **The universe, exit count, Stooq rates, probe statistics, matched-control
  construction, ordering, relative lift, horizon sweep and out-of-sample split
  all survived.** Kept unchanged and reproduced exactly.
- **"7.8% of sampled exits are not exits" survived with caveats.** Accepted: 7.8%
  is the no-`delistedAt` share and 5.7% is the still-filing evidence, and both
  counts now travel together in the text.
- **`study.py:473`'s "46%" was wrong.** Accepted: the panel value is 43.93%.

## What I needed that did not exist

Most of what v1 and the review asked for was written in their folders and is
imported here rather than rewritten. What this study had to add:

- **`placebo_table(frame, states, draws)`**, a single table that runs three
  constructions of the same null (nearest-key between-firm shuffle, cell-mean
  shuffle, within-firm shuffle) on one frame and reports the observed lift, each
  null's mean, sd, z and the ratio to the 95th percentile of the absolute null.
  The lesson of `CORRECTIONS.md` entries 16, 18 and 19 is that a single z is not
  reportable on its own, so the shared helper should return a family of nulls, not
  one.
- **A base-rate table parameterised on the exit anchor.** The review wrote
  `base_table(u, horizon, anchor, drop_stale, drop_ciks)` because v1 hard-coded
  one anchor inside `section_base_rates`. It is imported here and it should be in
  the toolkit: any panel study with an exit or a censoring rule needs to publish
  the range across anchors rather than one cell.
- **A matched-control sampler with the matching cell as a parameter**
  (`build_anchors_keyed`). This is again a study that needs
  "draw k controls per event from the same cell without replacement, report the
  unmatched count and the distinct control-cluster count".
- **`level_table` and `did_table`**, the level gap and the difference in
  differences at every quarter with a clustered interval, extracted so two
  matching cells can be compared row by row.
- **A structural-zero share alongside every difference-in-differences table.**
  "First quarter the interval excludes zero" is uninterpretable without the share
  of rows whose change is exactly zero at that quarter; this study prints it and
  it should travel with the statistic.
- **A quarterly `build_universe(panel)`** returning one row per CIK with
  `first_qi`, `last_qi`, `fresh_qi`, `exit`, `stale_tail` and `hist_q`.
  `analysis.december_snapshots` is the December-only version and there is no
  quarterly equivalent; v1 wrote `panel_base.py` and this study imports it.
- **`rate_ci(flags, groups)`**, a firm-clustered interval on a share, and
  **`tercile(s)`**, a rank-based tercile that does not raise on a thin group.
  Both were written in v1 and both are the most common statistics in this
  repository.

## Limits of the data as published

The panel row carries no date for the last new filing and no filing status, so
the exit date has to be reconstructed from `fiscal_year` transitions, and the
9.83%-to-26.60% range that is this document's deliverable exists because of that
reconstruction. The delisting date is served per ticker rather than on the panel
row, so a 150-CIK probe stands in for all 2,555 exits and the no-delisting-date
share carries a binomial interval of roughly +/- 4.4pp. No delisting reason is
served at all: acquisition, going private, deregistration, exchange deficiency
and bankruptcy are one number in every table above; section 5 tried to proxy
that distinction and failed. Altman Z, one of the two metrics that stably separates,
has exactly zero coverage in Financials and Real Estate, 28,794 rows and 15.1% of
the universe, and every metric except Piotroski refreshes once a fiscal year, so
"how many quarters before the record goes stale" can only answer in multiples of
four. The price file carries no series for 88.57% of exited CIKs and the panel's
ticker is current rather than as-of, which is why 6% of probe tickers resolve to
a different CIK than the panel gives.

## Charts

All five go through `distill_toolkit.charts`, and every subtitle carries the
"leaving the corpus, not failing" caveat.

| file | what it states |
|---|---|
| `charts/exit_anchor_range.png` | the Altman cell under all six exit definitions, whole panel against priced subset: 9.8% to 26.6% depending on which date is called the exit |
| `charts/base_rates_corrected.png` | every state under the corrected definition C, whole panel against priced subset, n = 128,123 over 5,499 CIKs |
| `charts/signature_sector.png` | median change from t-8 for six metrics, exits against sector-matched survivors; Altman Z and asset growth separate at t-4 in 5 of 5 draws, interest coverage in 3 of 5 |
| `charts/placebo_constructions.png` | absolute z of each state's lift under three constructions of the same null on frame C: 3.1 to 6.2 between firms, 0.5 to 17.7 within firms |
| `charts/ztrend_null.png` | the rising-Z share at exits against matched survivor anchors; the headline states the review's 42.0% rather than the 43.17% in the table on disk, as section 5 says |

## Where each number comes from

| section | numbers | file |
|---|---|---|
| Universe, exits, drop-year series, drop-quarter shares, stale tail, Stooq match rates, probe | all | `cache/research/pre-exit-signature-v2/output.txt` lines 1 to 55 |
| Base rate under six definitions, whole panel and priced, with intervals and CIK counts | all | `cache/research/pre-exit-signature-v2/base_variant_A.csv` through `base_variant_F.csv`; also printed in `output.txt` there |
| Ordering, lift over healthy, whole-over-priced ratios | all | `output.txt` (the "what survives the anchor change" block) |
| Horizon sweep and out-of-sample split | all | `horizons.csv`; also printed in `output.txt` |
| Still-filing bound, named drop and random 7.8% removal | all | `output.txt` (the "still-filing share" block) |
| Signature levels, gaps at t-8 and t-1, share at t-8, n per cell, both matching cells | all | `signature_levels.csv`; sector cell also printed in `output.txt` |
| Difference in differences at every quarter, first separating quarter, n per cell | all | `signature_did.csv`; both cells also printed in `output.txt` |
| Structural-zero shares at t-7 to t-1 | all | `zero_change_shares.csv`; also printed in `output.txt` |
| Seed sensitivity, 5 control-draw seeds | all | `seed_sensitivity.csv`; also printed in `output.txt` |
| Placebo, frame A, three constructions | all | `placebo.csv` |
| Placebo, frame C, three constructions | all | `placebo.csv` |
| Four constructions of the Altman null (3.6 / 5.1 / 8.8 / 12.0) | 3.6 and 5.1 | `placebo.csv` and `output.txt`, frame A |
| | 8.8 and 12.0 | `CORRECTIONS.md` entries 18 and 19, as withdrawn constructions |
| Z-trend cohorts and rising shares | all | `ztrend_placebo.csv` |
| Z-trend median levels (0.45 against 2.71) and below-1.8 shares | not on disk for v2 | [`../review-pre-exit/README.md`](../review-pre-exit/README.md) section 5 |
| Coverage: 43.93% Altman null, 30.01% coverage null, per-sector shares, 28,794 zero-coverage rows | all | `coverage.csv` (the two universe-wide shares are the row-weighted aggregate of that table) |
| Trajectory anchor frame, 1,688 exits and 5,064 sector-matched controls | all | `trajectories_sector.parquet` |

## Files

| file | what |
|---|---|
| `PREREGISTRATION.md` | every table specified before the run |
| `study.py` | reproduces every number above from cached files; no API call |
| `cache/research/pre-exit-signature-v2/output.txt` | run log |
| `cache/research/pre-exit-signature-v2/base_variant_{A..F}.csv` | section 2 |
| `cache/research/pre-exit-signature-v2/horizons.csv` | horizon sweep and out-of-sample split |
| `cache/research/pre-exit-signature-v2/signature_levels.csv`, `signature_did.csv`, `zero_change_shares.csv`, `seed_sensitivity.csv` | section 3 |
| `cache/research/pre-exit-signature-v2/trajectories_sector.parquet` | the sector-matched anchor-quarter frame |
| `cache/research/pre-exit-signature-v2/placebo.csv` | section 4, frames A and C |
| `cache/research/pre-exit-signature-v2/ztrend_placebo.csv` | section 5 |
| `cache/research/pre-exit-signature-v2/coverage.csv` | section 6 |

## Disclosure

Companies are not named anywhere in this document. Leaving the panel means
leaving the corpus, not failing: acquisition, going private, deregistration,
exchange deficiency and bankruptcy arrive as one event in every table above.

Distill Markets Pty Ltd, the publisher of this repository, operates the paid
data service this study uses. Authors and the publisher may hold positions in
securities of the kind described. Everything above is general information derived from
public SEC filings and from a price file the author holds. It is not financial
product advice, does not consider your objectives, financial situation or
needs, and past patterns do not guarantee future results. See
[NOTICE](../../NOTICE).
