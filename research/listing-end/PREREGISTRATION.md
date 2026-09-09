# Pre-registration: `listing-end`

Written before `study.py` was run. Every table below is specified here first;
the study fills the cells and nothing else. A design pass over the sample
produced the predictions marked as such; a prediction is not a result.

Vintage: `cache/pit-sample.csv.gz`, the published 200-firm cut of the
`screen/export` panel rebuilt 2026-09-07, final quarter 2026-06-30, release
`pit-sample-2026-09-07`. Prices: `cache/stooq_us/` through 2026-08-14, read
only to mark a ticker as having a series in the bundle. API: **zero uncached
calls**. `distill_toolkit.client.get`, `post`, `request` and `download` are
replaced by a raiser before any other import.

If a full Pro export with the `listed_until` column is at `cache/panel.csv`
the script runs on it instead and says so; every number in the README is from
the sample unless the README says otherwise.

## Question

For a firm whose listing ended with a Form 25 (exchange delisting) or a Form 15
(Section 12 deregistration) on file, how many days after its last point-in-time
panel row, and after its last record refresh, does the listing end; and how
does the final row on file for a Form 25 firm compare with a Form 15 firm and
with survivors observed on the same snapshot in the same revenue tercile.

Unit resampled: the firm. Window: leavers whose last row precedes the final
snapshot, 2009-12-31 to 2026-06-30. Descriptive only: nothing here is about a
price.

## Definitions

- **Leaver**: a CIK whose last row's `as_of_date` precedes the panel's final
  snapshot. **Dated** when `listed_until` is set; **source** is
  `listing_end_source`. `migration` and `crawl` are reported by count and
  excluded from every comparison.
- **Last row**: the leaver's last `as_of_date`.
- **Last record refresh**: the first `as_of_date` at which the leaver's final
  `fiscal_year` appears (trap 16).
- **Gap**: `listed_until` minus each anchor, in days.
- **Revenue tercile**: within each snapshot over rows with `is_listed_equity`
  and `revenue > 0`.
- **Matched survivor rows**: for each dated leaver, three rows drawn with a
  fixed seed from firms still present at the final snapshot, on the leaver's
  last snapshot and in its revenue tercile. A cell with fewer than three
  survivor rows contributes what it has.
- **Metrics on the final row**: revenue, operating margin, net margin, asset
  growth, FCF margin, Altman Z, Piotroski, net dilution. Each reported with its
  non-null count per cohort.

## Tables to be filled

### T1. Universe and coverage
Firms, rows, survivors, leavers, dated leavers by source, undated leavers. The
Stooq bundle: share of survivors with a series; dated leavers with a series,
split into series that begin after the listing end (a reused symbol) and series
that span it; undated leavers with a series through the bundle's edge.
Prediction from the design pass: 102 leavers, 87 dated (70 / 15 / 1 / 1),
15 undated; 8 dated leavers with a series, 5 beginning after the listing end;
7 undated leavers with a live series.

### T2. Gap from each anchor to the listing end, by source
Rows: Form 25, Form 15. Columns: n, 10th, 25th, median, 75th, 90th, mean, for
the gap from the last row and from the last refresh; quarters between refresh
and last row. Difference of medians Form 25 minus Form 15 with a firm bootstrap
95% interval (`analysis.cluster_boot_diff`, 1,000 draws).
Prediction from the design pass: medians about 53 and 45 days from the last row,
about 200 and 185 days from the last refresh; the interval on the difference
includes zero.

### T3. The Form 25 gap by sector and by exit-year half
Sectors with at least five Form 25 leavers; exit years 2011 to 2018 against
2019 to 2026. Median and IQR only; n is too small for an interval per cell and
none is reported.

### T4. The final row on file, by cohort
Cohorts: Form 25, Form 15, undated leavers, matched survivors. Median of each
metric with its n. Differences Form 25 minus survivors, Form 15 minus survivors
and Form 25 minus Form 15 with firm bootstrap 95% intervals.
Prediction: Form 25 and Form 15 both below survivors on operating margin, net
margin and Altman Z; no prediction on the Form 25 minus Form 15 sign.

### T5. Placebo, between-firm label shuffle
`analysis.clustered_shuffle` of the source label across the Form 25 and Form 15
firms, 200 draws, for the median gap difference and each metric difference in
T4; and of the leaver label across leaver and matched-survivor firms, 200
draws, for each Form 25 minus survivors difference. Reported: observed,
placebo mean and standard deviation, z, share of draws at least as far from
zero. A difference inside the placebo band is a null and is written up as one.

### T6. Undated leavers
Each of the undated leavers: last snapshot, rows on file, whether a series runs
through the bundle's edge. Count with a last row within four quarters of the
final snapshot. This table is a coverage statement, not a result.

## Charts

- `charts/listing-end-gap.png`: the gap distributions in T2 as range marks.
- `charts/final-row.png`: the T4 margin, growth and Altman Z medians by cohort
  with their intervals.

## What would break it

n = 15 on Form 15 and 200 firms overall; every interval will be wide and the
README says so in the first paragraph. The full export re-runs the same script.
