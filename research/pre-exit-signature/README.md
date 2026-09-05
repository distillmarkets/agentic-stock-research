# The pre-exit signature, price-free

**Superseded in part.** The review in [`../review-pre-exit/`](../review-pre-exit/)
broke the placebo claims in section 4, and
[`../pre-exit-signature-v2/`](../pre-exit-signature-v2/) reports the corrected
range (`CORRECTIONS.md` entries 16, 18 and 19). This document is kept as the
first draft so the loop can be read end to end; where it and v2 disagree, v2
stands.

What the point-in-time filing record shows in the eight quarters before a filer
leaves it, measured on every CIK in the panel with no price data at any step.

Reproduce every number below with:

```
./.venv/bin/python research/pre-exit-signature/study.py
```

The full printed output is kept at `cache/research/pre-exit-signature/output.txt`.
`research/pre-exit-signature/probe_delisted.py` regenerates the 150 cached API
responses the study reads; it is not needed to reproduce the tables.

---

## Question

[findings/ghost-cohort.md](../../findings/ghost-cohort.md) established that a
third of SEC December firm-years carry no price series because the firm later
stopped trading, that those firms were smaller and weaker on the day they
entered, and that they left the filing universe about thirteen times as often as
priced firms. It stopped at the boundary of the price file.

This study stays inside the filings. Three questions:

1. How many CIKs stop appearing in the panel, when, and what date does the last
   panel row actually mark.
2. Over the eight quarters before the record goes stale, which of eleven filed
   metrics move, how far ahead, and by how much, against survivors matched on
   calendar quarter and revenue tercile.
3. For simple observable states at a quarter (Altman Z below 1.8, interest
   coverage below 1, negative FCF margin with falling revenue, Piotroski at or
   below 2, two or more of those), what share of firm-quarters in that state
   stop filing within eight quarters, on the whole universe against the priced
   subset.

## Data vintage

| source | vintage | used for |
|---|---|---|
| `cache/panel.csv` | `screen/export`, panel vintage 2026-09-03, final quarter 2026-06-30, 206,957 rows | everything |
| `cache/stooq_us/` | Stooq US daily bundle through 2026-08-14 | marking a ticker priced or not, nothing else |
| `/sec/fundamentals/{t}/as-of/2026-09-03?period=annual` | 150 responses cached 2026-09-04 | `delistedAt` for a sample of exited CIKs |

**No return is computed anywhere in this study**, so there is nothing to
market-adjust. The only price-derived quantity is the match rate.

**API budget: 150 calls, 150 spent, none in a loop over the universe.** The
sample is pinned to `cache/research/pre-exit-signature/probe_sample.csv` on the
first run so the denominator cannot move underneath the study.

## Method

**Universe.** Panel rows with `is_listed_equity`, `revenue > 0`, and a ticker
that maps to exactly one CIK anywhere in the export (the filter
`analysis.december_snapshots` applies, so the counts sit next to the ghost
cohort's on the same basis). **n = 190,586 firm-quarters over 6,103 CIKs**,
2009Q2 to 2026Q2.

**Exit.** A CIK exits when its last panel row is at least eight quarters before
the panel's final quarter, that is `last_qi <= 2024Q2`. Because a panel row
exists for every quarter the export carries a filer, "never reappears" is
automatic: the test is on the maximum. **n = 2,555 exits (41.9% of CIKs)**,
3,548 CIKs still present.

**The anchor, and why it is not the last panel row.** The export keeps serving a
filer whose newest full fiscal year is up to two years old. For exits, the
median gap between the last quarter at which a new annual filing refreshed the
row and the last row itself is **5 quarters** (mean 4.57, IQR 4 to 5), against
**1 quarter** for CIKs still present; 74% of exits carry a last row whose
`as_of` year is two years past its `fiscal_year`, and 72.8% of drops fall in a
June quarter. The last panel row is a **drop date produced by a staleness rule**,
not a filing date. Every trajectory here is therefore anchored on `fresh_qi`,
the first quarter carrying the CIK's final fiscal year, and **t-1 is that
quarter** with t-8 seven quarters earlier.

**Matching.** Each exit with eight quarters of history before its anchor
(**n = 1,688 CIKs**, 66.1% of exits; the other 33.9% have a shorter record) is
matched to **three** survivor firm-quarters drawn without replacement from the
same calendar quarter and the same revenue tercile within that quarter. A
survivor anchor is any quarter of a still-present CIK with seven quarters of
history behind it and eight quarters of panel rows ahead of it. **n = 5,064
control anchors over 1,936 distinct CIKs**; 0 exits went unmatched. Anchor years
run 2012 to 2023. Intervals are `analysis.cluster_boot_diff` over CIK, 300
draws, and a survivor CIK used at more than one anchor moves all of its rows
together inside a draw.

**Base rates.** Anchors run to `2026Q2 - 8 - h` for a horizon of `h` quarters, so
the outcome is censored by the panel edge in neither direction: a flagged firm's
last row is at or before 2024Q2 and so is a confirmed exit under this study's own
definition, and an unflagged firm demonstrably has a panel row after `qi + h`.
Anchoring instead at `2026Q2 - h` labels every firm still filing at the last
usable quarter an exit, because the panel simply stops there, and it adds about
two points to the whole-universe rate and about **3.5 points to the priced rate**,
which is the larger error in relative terms. A state is only true where the
metric is on file; a null never counts as a state, so every state count is a
lower bound.

### Stooq match rate, on the honest denominator

| denominator | n | with a Stooq series |
|---|---|---|
| firm-quarters | 190,586 | **66.34%** |
| distinct CIKs | 6,103 | **53.22%** |
| exited CIKs | 2,555 | **11.43%** |
| unpriced CIKs that exited | 2,855 | **79.26%** |

88.57% of exited CIKs carry no price series at all, so every rate on the priced
subset below is a floor and nothing in this data bounds by how much.

## Result

### 1. 2,555 exits, roughly 200 a year, and the last panel row lags the delisting by three quarters

| panel-drop year | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| exits | 230 | 224 | 183 | 213 | 219 | 190 | 196 | 214 | 190 | 192 | 226 | 224 |

2011 (8) and 2012 (46) sit inside the panel's coverage ramp and are not
comparable. **Every count in this document mixes acquisition, going private,
deregistration, exchange deficiency and bankruptcy into one event.** The panel
carries nothing that separates them, and neither does the probe.

Against the ghost cohort: that study found 2,833 of 5,960 December CIKs with no
price series, and a two-year panel-exit rate of 31.83% for ghost firm-years
against 2.37% for priced. This study's unconditional eight-quarter rate is
**29.97% for unpriced firm-quarters against 2.33% for priced** (n = 54,205 and
83,582), which reproduces the published pair on a quarterly panel and a different
exit definition.

**The probe (150 calls, at most one per CIK).** Of 150 sampled exited CIKs,
**141 (94.0%)** resolve to the panel's own CIK and 9 (6.0%) resolve to another,
which is ticker recycling on a symbol whose issuer stopped trading. Of those 141:

- **130 (92.2%) carry a `delistedAt`.**
- The panel's last row **follows** `delistedAt` for **93.1%** of them, median
  **+2.92 quarters** (IQR +2.00 to +4.22).
- The last record refresh **precedes** `delistedAt` for **93.8%** of them, median
  **1.83 quarters** (IQR +0.71 to +3.00).
- 11 carry no `delistedAt` at all, and **8 of those hold an annual filing dated
  2026-02-27 or later**, so they still file and left the export for some other
  reason. On this sample that is 7.8% of exits, and it is the rate at which
  "left the panel" is not "stopped existing".

So "exit within eight quarters of the panel drop" is, on this sample,
approximately "delisted within five quarters", and the anchor used for the
signature sits a median 1.83 quarters before the served delisting date.

### 2. The signature is a level, not a slope

Medians at t-8 and at t-1, exits minus matched survivors, with a firm-clustered
95% interval. The last column is the share of the t-1 gap that is already there
at t-8.

| metric | exit t-8 | survivor t-8 | gap at t-8 | gap at t-1 | already at t-8 |
|---|---|---|---|---|---|
| operating margin | 2.3% | 6.4% | **-4.0pp** [-4.7, -3.1] | -4.7pp [-5.9, -3.9] | 87% |
| Altman Z | 1.73 | 3.54 | **-1.81** [-2.23, -1.40] | -1.95 [-2.31, -1.49] | 93% |
| interest coverage | 1.20 | 3.32 | **-2.12** [-2.55, -1.60] | -2.40 [-3.11, -1.87] | 88% |
| FCF margin | 1.3% | 4.1% | -2.7pp [-3.5, -1.7] | -2.7pp [-3.5, -1.9] | 103% |
| revenue growth | 3.5% | 5.9% | -2.4pp [-3.5, -1.2] | -3.0pp [-4.1, -2.1] | 82% |
| Piotroski F | 4.01 | 4.31 | -0.30 [-0.41, -0.18] | -0.34 [-0.47, -0.23] | 87% |
| accruals ratio | -6.7% | -4.9% | -1.8pp [-2.4, -1.1] | -2.0pp [-2.8, -1.4] | 87% |
| asset growth | 3.4% | 5.4% | -2.0pp [-3.0, -1.0] | **-4.9pp** [-6.0, -4.0] | 41% |
| M-Score (5 var) | -2.961 | -2.944 | -0.017 [-0.052, +0.009] | -0.053 [-0.081, -0.019] | 32% |
| net dilution | 0.8% | 0.6% | +0.2pp [+0.0, +0.4] | +0.1pp [-0.1, +0.3] | n/a |
| DSO | 48.9 | 48.4 | +0.5 [-2.3, +2.9] | -1.7 [-4.6, +0.7] | n/a |

n per cell at t-8 and t-1 is the metric's non-null count inside 1,688 exit and
5,064 control anchors; across the eight-quarter windows the non-null shares are
asset growth 97.5%, operating margin 95.2%, revenue growth 91.3%, DSO 84.6%,
M-Score 83.5%, Piotroski 83.0%, net dilution 68.4%, interest coverage 67.3%,
accruals 65.3%, FCF margin 61.2%, **Altman Z 56.5%**.

Now the trajectory, which is each anchor's change from its own t-8 value, exits
minus survivors, at each quarter:

| metric | first quarter the difference excludes zero | exit move t-8 to t-1 | difference at t-1 |
|---|---|---|---|
| revenue growth | **t-5** | -2.8pp | -2.2pp [-3.8, -0.9] |
| Altman Z | **t-4** | -0.33 | -0.27 [-0.43, -0.14] |
| asset growth | **t-4** | -4.5pp | -3.8pp [-5.3, -2.5] |
| M-Score (5 var) | **t-3** | -0.038 | -0.057 [-0.084, -0.029] |
| operating margin | t-1 | -0.7pp | -0.8pp [-1.3, -0.4] |
| DSO | t-1 | -0.19 | -0.63 [-1.15, -0.04] |
| FCF margin | never | -0.4pp | -0.5pp [-1.3, +0.1] |
| interest coverage | never | +0.02 | -0.12 [-0.35, +0.15] |
| Piotroski F | never | -0.05 | -0.04 [-0.18, +0.09] |
| accruals ratio | never | +0.1pp | -0.001 [-0.007, +0.004] |
| net dilution | never | 0.0pp | +0.000 [-0.001, +0.001] |

n at t-1 runs from 781 exits / 2,607 controls (Altman Z) to 1,589 / 4,925 (asset
growth); every row's pair is in `cache/research/pre-exit-signature/signature_did.csv`.

Read together: **between 82% and 103% of the eventual gap on eight of the eleven
metrics is already on file two years before the record goes stale.** The two
metrics that genuinely move are **asset growth**, which gives up 4.5pp against
0.7pp for controls and reaches a median of exactly 0.0% at t-1, and **Altman Z**,
down 0.33 points against 0.05. Interest coverage, FCF margin, Piotroski, accruals
and net dilution do not separate from matched survivors at any quarter in the
window, and they are the metrics whose level gap was largest to begin with.

Because the panel's annual metrics refresh once a fiscal year, an eight-quarter
window holds two refreshes for most firms, so "how many quarters before" resolves
at annual granularity: t-4 and t-5 both mean "one annual filing before the last
one on file".

### 3. The deliverable: what a state carries, whole panel against priced subset

Share of firm-quarters in each state whose CIK stops filing within eight quarters.
Anchors 2009 to 2022Q2; **n = 137,787 firm-quarters over 5,499 CIKs**, of which
2,509 CIKs contribute at least one exit. Intervals are a firm-clustered bootstrap,
300 draws.

| state at a quarter | n | CIKs | whole panel | priced subset | n priced | understated by |
|---|---|---|---|---|---|---|
| Altman Z < 1.8 | 27,919 | 2,246 | **18.49%** [17.34, 19.60] | **3.55%** [2.79, 4.50] | 13,371 | **5.20x** |
| interest coverage < 1 | 31,604 | 2,819 | **19.59%** [18.46, 20.65] | **4.65%** [3.83, 5.63] | 15,296 | 4.21x |
| FCF margin < 0 and revenue falling | 8,293 | 1,273 | **17.87%** [16.37, 19.82] | **3.16%** [2.14, 4.29] | 4,183 | 5.66x |
| Piotroski <= 2 | 17,472 | 2,431 | **18.59%** [17.38, 19.74] | **3.93%** [3.02, 5.08] | 8,314 | 4.73x |
| two or more of the four | 22,156 | 2,379 | **20.48%** [18.95, 21.97] | **4.53%** [3.53, 5.57] | 10,044 | 4.52x |
| none of the four | 81,292 | 4,082 | 10.00% [9.45, 10.57] | 1.62% [1.38, 1.90] | 55,358 | 6.16x |
| any firm-quarter | 137,787 | 5,499 | 13.21% [12.71, 13.69] | 2.33% [2.07, 2.68] | 83,582 | 5.66x |

The ghost-cohort study said a priced-only sample understates this rate about
four-fold. Measured per state it is **4.2x to 6.2x**, and the largest ratio is on
the healthiest state rather than the sickest.

Two things survive the truncation and one does not. The **ordering** survives:
every distress state is above the no-state cell in both columns. The **relative
lift** roughly survives: 18.49 / 10.00 = 1.85x on the whole panel against
3.55 / 1.62 = 2.19x on the priced subset. The **level** does not: a priced-only
sample reports that one firm-quarter in twenty-eight with an Altman Z below 1.8
stops filing inside two years, where the panel says one in five.

Horizon sweep, whole panel against priced subset, for the same states:

| horizon | anchors to | Altman Z < 1.8 | two or more | any firm-quarter |
|---|---|---|---|---|
| 4 quarters | 2023Q2 | 10.40% / 2.09% | 11.68% / 2.57% | 7.68% / 1.40% |
| 8 quarters | 2022Q2 | 18.49% / 3.55% | 20.48% / 4.53% | 13.21% / 2.33% |
| 12 quarters | 2021Q2 | 25.94% / 5.05% | 28.76% / 6.73% | 18.24% / 3.16% |

### 4. Placebo, and an out-of-sample split

*The between-firm null below is withdrawn: the helper that produced it dropped
rows and held every shuffled label constant within a firm-year.
[`../pre-exit-signature-v2/`](../pre-exit-signature-v2/) section 4 reports the
same lifts under the repaired null. The within-firm null and the out-of-sample
split are unchanged.*

The statistic tested is the **lift**: a state's exit rate minus the exit rate over
all firm-quarters (13.21%). Two nulls, 200 draws each.

- **Between firms.** `analysis.clustered_shuffle` permutes the exit label between
  firms with each firm carrying its whole label series, aligned within calendar
  year. The null lift is at or below **+0.24pp +/- 0.96** on every state, and the
  observed lifts sit at **z = 4.6 to 12.2 in absolute value** (Altman 8.8,
  coverage 11.6, FCF and falling revenue 4.6, Piotroski 8.0, two or more 10.5,
  none of the four -12.2). Every observed lift is more than **2.4 times** the 95th
  percentile of the absolute shuffled lift; the six ratios are 6.2, 5.7, 5.2, 4.3,
  4.0 and 2.4, and the smallest is the FCF-and-falling-revenue state.
- **Within firms.** `analysis.within_firm_shuffle` permutes each firm's own state
  flag across its own quarters, which keeps every firm-level property and destroys
  all timing. This null is far stronger, because most of a state's information is
  about *which firm* rather than *which quarter*: it reproduces **4.10pp of the
  5.28pp** Altman lift, **5.02 of 6.38** for coverage, and **5.07 of 5.38** for
  Piotroski. Against that null the observed lift is z = 14.3 for Altman, 16.4 for
  coverage and **z = 2.0 for Piotroski <= 2**, which is the one state whose timing
  inside a firm's own history adds almost nothing over knowing which firm it is.
- **Out of sample.** Splitting the anchors at the median year: 2009-2015
  (n = 55,726) gives 12.79% whole against 2.24% priced, ratio 5.72; 2016-2022
  (n = 82,061) gives 13.49% against 2.39%, ratio 5.65. Every state keeps its sign
  and its order in both halves.

### 5. Altman Z trend over the last four quarters, which is a proxy and not a reason code

**This split is a proxy.** Nothing in the panel or the API response says whether a
firm was acquired, went private, deregistered or failed. All this measures is
whether the last reading of Altman Z was above or below the one four quarters
earlier.

Altman Z is null on 43.9% of universe rows and has **no coverage in Financials or
Real Estate**, so the classified set is a different universe from the exit set.
**1,016 of 2,555 exits (39.8%) are classifiable**: 590 with a falling Z, 426 with
a rising Z, median change -1.13 and +0.76.

| at the last refreshed quarter | Z falling (n = 590) | Z rising (n = 426) |
|---|---|---|
| median revenue at the last panel row | $341m | $391m |
| median Altman Z | 0.45 | 2.71 |
| median operating margin | -3.8% | 5.5% |
| priced in the Stooq bundle | 9.3% | 10.1% |
| quarters from last refresh to panel drop | 5 | 5 |

The two groups leave the panel on the same mechanical schedule and are equally
absent from the price file, and they differ by 2.26 points of Altman Z and 9.3pp
of operating margin.

Splitting the base-rate table the same way (shares are of all firm-quarters in the
state, so the three columns sum to the total):

| state | exits within 8q | Z falling | Z rising | no Z on file | Z-falling share of classified |
|---|---|---|---|---|---|
| Altman Z < 1.8 | 18.49% | 9.14% | 5.31% | 4.04% | 63.3% |
| interest coverage < 1 | 19.59% | 5.99% | 2.29% | 11.31% | 72.4% |
| FCF < 0 and revenue falling | 17.87% | 5.96% | 2.83% | 9.08% | 67.8% |
| Piotroski <= 2 | 18.59% | 6.66% | 2.00% | 9.93% | 76.9% |
| two or more of the four | 20.48% | 9.19% | 3.23% | 8.05% | 74.0% |
| none of the four | 10.00% | 1.63% | 1.96% | 6.41% | 45.4% |
| any firm-quarter | 13.21% | 3.34% | 2.48% | 7.39% | 57.3% |

The base rates do differ by proxy type. Among classified exits out of a distress
state, 63% to 77% left with a falling Z, while out of the **none of the four**
state the majority (54.6%) left with a rising one. Measured against the healthy
state as the denominator, the **Z-falling** exit rate is 3.6x to 5.6x higher in
the five distress states, while the **Z-rising** exit rate is only 1.0x to 2.7x
higher. Almost all of the exit lift a distress state carries is a lift in exits
that were preceded by a falling Z, and the part of it that looks like a firm
leaving in good order barely moves with the state at all.

## What would break it

1. **The exit date is a staleness rule, not an event.** 72.8% of drops land in a
   June quarter and 74% of last rows carry a fiscal year two years old. The probe
   measures the consequence directly: the drop lags the served `delistedAt` by a
   median 2.92 quarters. Every "within 8 quarters" here is "within about 5
   quarters of the delisting" on the probe sample, and if the export's retention
   rule changed at any point in the panel's history, the exit-year series would
   move with it and this study would read that as a change in the world.
2. **7.8% of sampled exits are not exits.** 11 of 141 CIKs carry no `delistedAt`
   and 8 of them still file. The base rates are therefore a mixture of leaving the
   corpus and leaving existence, and the probe is 150 CIKs, so that share carries
   a binomial interval of roughly +/- 4.4pp.
3. **Panel exit is not distress.** Acquisition, going private, deregistration and
   bankruptcy produce the identical footprint. Section 5 does not resolve this and
   says so.
4. **Altman Z is present on 56.5% of the trajectory-window rows and has zero
   coverage in Financials and Real Estate.** The two headline movers are Altman Z and asset
   growth, and one of them is measured on a sector-truncated universe.
5. **The matched control set is drawn with a fixed seed and each survivor CIK can
   serve several anchors.** 5,064 anchors come from 1,936 CIKs, 2.6 apiece. The
   cluster bootstrap resamples the union of both frames' CIKs, so that reuse is
   inside the intervals, but a different seed moves the third decimal.
6. **The state definitions treat a null as not-in-state.** Altman Z is null on
   43.9% of universe rows and interest coverage on 30.0%. Every state count is a lower bound, and the
   states are not competing on equal coverage: `interest_coverage < 1` reaches
   31,604 firm-quarters where `FCF < 0 and revenue falling` reaches 8,293.
7. **The revenue tercile is the only size control**, because the panel row carries
   no market capitalisation and no share count. Revenue conflates scale with
   business model, and a distributor and a software firm at the same revenue are
   not the same size.
8. **A third of exits are excluded from the signature.** 867 exits (33.9%) have
   fewer than eight quarters of panel history before their anchor, and their
   median history is **0 quarters**: their first and last record refresh are the
   same quarter, so the panel holds one annual filing for them. Short-lived filers
   are the part of the exit population section 2 cannot see, and there is no
   reason to think they look like the ones it can.
9. **The priced flag is measured in August 2026 and applied back to 2009.** It
   embeds the future relative to every anchor date. Nothing here is a signal that
   could have been formed at the time; it is a description of what a join
   discards.
10. **6% of sampled tickers resolve to a different CIK at the API.** The panel's
    ticker is current and not point-in-time, so a delisted issuer's symbol that
    has since been reissued resolves to the new holder. The study joins on CIK
    internally and only the probe touches a ticker, but the same defect would
    corrupt any per-ticker follow-up.

## What I needed that did not exist

Written inside this study.

- **`panel_base.build_universe(panel)`**, which returns the quarterly universe
  and a one-row-per-CIK frame with `first_qi`, `last_qi`, `fresh_qi`, `exit`,
  `stale_tail` and `hist_q`. Every panel study rebuilds some subset of this by
  hand. `analysis.december_snapshots` is the December-only version and there is no
  quarterly equivalent.
- **A quarter index and a last-refresh anchor.** `fresh_qi`, the first quarter
  carrying a CIK's final fiscal year, is the difference between a trajectory and a
  flat line: anchored on the last panel row instead, seven of the eight quarters
  in the window are a repeat of one annual filing and every metric is a two-level
  step function. Any study that indexes panel rows by time needs this, and nothing
  in the toolkit exposes it.
- **`tercile(s)`**, a rank-based tercile that does not raise on a group of four,
  which `pd.qcut` does on the panel's thin early quarters.
- **`rate_ci(flags, groups)`**, a firm-clustered interval on a share.
  `analysis.cluster_bootstrap` does it with `stat=np.mean` but every study writes
  the same three-line wrapper, and a share is the most common statistic in this
  repository.
- **A matched-control sampler.** "For each event row, draw k controls from the
  same cell without replacement, report the unmatched count and the distinct
  control-cluster count" is the shape of at least three studies here and there is
  no shared implementation.
- **A degeneracy guard on median differences.** `cluster_boot_diff` on an
  integer-valued column returns exactly 0.000 [0.000, 0.000] for the Piotroski
  score, which reads as a very precise null rather than as a statistic that cannot
  resolve. This study switches to the mean for that column; a helper that flagged
  the degeneracy would have saved a wrong reading.
- **`clustered_shuffle(..., within=year)` dropped 44% of rows to NaN** on this
  frame at the time of this draft (fixed in the shipped helper, CORRECTIONS.md entries 16 and 18), because a firm's permuted partner often has no row in that calendar year.
  The lift statistic is computed on the surviving rows for both the state and the
  overall rate so the drop mostly cancels, but the helper gives no count of what it
  dropped and a caller who reads the raw shuffled mean gets a biased null.

## Limits of the data as published

The record dates a delisting but never says why, so acquisition, going private,
deregistration, exchange deficiency and bankruptcy sit inside one number in
every table above. Panel exit is inferred from the absence of a later row
rather than from a filing date, and the export keeps serving a filer whose
newest full fiscal year is up to two years old, so the exit date measured here
is a retention artefact whose rule had to be reverse-engineered before anything
else could be measured. The panel's metrics refresh once a fiscal year, so an
eight-quarter window holds two observations and "how many quarters before"
can only resolve in multiples of four. Altman Z, the strongest metric in this
study, has no coverage at all in Financials and Real Estate, and the price file
carries no series for 88.57% of exited CIKs, which is the survivorship problem
in one number. The panel's ticker is current rather than as-of, so a delisted
issuer's reissued symbol resolves to whoever holds it now.

## Charts

| file | what it states |
|---|---|
| `charts/exits.png` | exits by panel-drop year, and how far the drop falls after the served delisting date |
| `charts/signature.png` | median change from t-8 for six metrics, exits against matched survivors |
| `charts/base_rates.png` | exit-within-8-quarters rate per state, whole panel against priced subset |
| `charts/placebo.png` | observed lift against the 95th percentile of a firm-clustered shuffle |
| `charts/exit_type.png` | the same base rates split by the exiting firm's Altman Z trend |

## Files

| file | what |
|---|---|
| `study.py` | reproduces every number above; no API call |
| `panel_base.py` | universe, exit definition, quarter indexing, shared with the probe |
| `probe_delisted.py` | the 150-call probe; writes `probe_sample.csv` and `probe_delisted.csv` |
| `cache/research/pre-exit-signature/output.txt` | full printed output |
| `cache/research/pre-exit-signature/trajectories.parquet` | 54,016 anchor-quarter rows |
| `cache/research/pre-exit-signature/signature_levels.csv`, `signature_did.csv` | section 2 |
| `cache/research/pre-exit-signature/base_rates_h{4,8,12}.csv`, `base_rates_h8_{2009_2015,2016_2022}.csv` | section 3 |
| `cache/research/pre-exit-signature/placebo.csv`, `exit_type.csv` | sections 4 and 5 |

## Disclosure

Companies are not named anywhere in this document.

Distill Markets Pty Ltd, the publisher of this repository, operates the paid
data service this study uses. Authors and the publisher may hold positions in
securities of the kind described. Everything above is general information derived from
public SEC filings and from a price file the author holds. It is not financial
product advice, does not consider your objectives, financial situation or
needs, and past patterns do not guarantee future results. See
[NOTICE](../../NOTICE).
