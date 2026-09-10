# A current-listings price file discards close to a third of the filer-years: 13,429 of 43,474 December firm-years 2010-2025, 2,663 CIKs, against a Stooq bundle of August 2026

Distill's point-in-time panel holds every listed filer at every December
snapshot, including the ones that later stopped existing. A Stooq daily bundle
holds prices for names that still traded in August 2026. Firm-years with no
series in the price file are the **ghost cohort**. This document is about how
large it is, who is in it, what happens to those firms in the filings alone, and
how far two already-published results move when the ghosts are dropped.

Data vintage: Distill `screen/export` panel of 2026-09-07, Stooq US daily bundle
through 2026-08-14. Reproduce with
`./.venv/bin/python research/ghost-cohort/study.py` from the repository root. The script is held by the publisher and available on request.
Claims that did not survive an adversarial re-run are recorded in
[CORRECTIONS.md](../CORRECTIONS.md) and are not restated here.

**Every number below was re-run on 2026-09-10.** The first published version of
this document ran on the 2026-09-03 panel and read a Stooq index that included
the bundle's fund folders. Two things changed, and
[CORRECTIONS.md](../CORRECTIONS.md) entry 21 keeps them apart: the fund files
left the index, which moves the ghost count by +192 firm-years on this panel,
and the panel vintage moved, which takes the December universe from 45,428
firm-years to 43,474. Nothing here is a restatement of the earlier vintage; it
is the same study on one named panel.

## Size and shape

**69.11%** of the panel's 43,474 December firm-years 2010-2025 (5,726 CIKs) have
a series under the panel's ticker. Only **66.23%** also have a close within 14
days of the snapshot date, which is the test the forward-paths builder applies,
so the coverage a price study actually gets is 2.9pp below the coverage the file
listing promises. The ghost cohort is **13,429 firm-years (30.89%) over 2,663
CIKs**. The flag is effectively a firm attribute: only 4 of 5,726 CIKs change
status across their years.

Ghost share by entry year:

| entry year | 2012 | 2015 | 2018 | 2021 | 2023 | 2025 |
|---|---|---|---|---|---|---|
| ghost share | 49.2% | 42.2% | 33.1% | 23.6% | 18.1% | 8.3% |

Within 2025 the residual is a size gradient: the bottom revenue decile matches
72.2% and the top matches 98.3%, n = 302 per decile. The five top-decile misses
in 2025 are `ACF`, `BK`, `DISH`, `FMCC` and `FNMA`. They are not a random sample
of large caps, and the panel carries nothing that says why any of them is
absent: `BK` is the one the price file files under another name, `BNY`
([CORRECTIONS.md](../CORRECTIONS.md) entry 8), and the other four are firms with
a December 2025 panel row and no series in a file current eight months later.
**A delisting, a move off the three exchanges the bundle carries and a failed
key arrive here as the same absence, which is the point.** In 2012 the smallest
revenue tercile was 64.0% ghost against 29.8% for the largest.

Ghost share by health score at entry runs monotonically from 44.2% at 0-30
(n = 4,865) down to 24.4% at 85-100 (n = 6,599). By sector it runs from Energy
42.5% (n = 2,078) and Communication Services 39.7% (n = 2,046) to Utilities
14.8% (n = 903).

![Ghost share by entry year and by health at entry](charts/ghost-share.png)

## Why a firm is a ghost

**87.8% of ghost firm-years (11,792) belong to a CIK absent from the panel's
final snapshot: it stopped filing.** 12.2% (1,637 firm-years, 208 CIKs) still
file. A bounded probe of 300 profile calls, 150 for each group, reads SEC's own
exchange record. The probe's sample was drawn on the earlier panel vintage and
its responses are cached, so the two rates below are pinned to that draw and are
not re-sampled here:

| sampled ghost CIKs | n | SEC still names a NYSE or Nasdaq listing | SEC names no exchange |
|---|---|---|---|
| stopped filing | 150 | 0.7% | 99.3% |
| still filing | 150 | 18.7% | 80.0% |

**That 18.7% is an upper bound on join failure, not a measurement of it.** SEC's
`exchanges` field carries no date, and 27 of the 28 firms behind it have a
December 2025 panel row, all 28 are present at the panel's final snapshot, and
none has a series in a price file current to 2026-08-14, which is the shape of a
2026 delisting whose SEC record has not been cleared as much as it is the shape
of a bad key. The mechanism a join failure would need, a panel ticker that is
not the traded common, can be measured directly: **none of the 300 sampled ghost
CIKs has any SEC-named ticker present in the Stooq bundle**, which bounds that
mechanism below 2% of still-filing ghosts and below 0.3% of ghost firm-years.

298 of the 300 tickers resolve to the same CIK the panel gave them. The two that
do not are ticker collisions: `FMCC` resolves to CIK 0000038009 while the panel
gives 0001026214, and `ME` resolves to 0001022345 against the panel's
0001804591. Ticker recycling is small but not zero.

A panel ticker can resolve to a security that is not the firm's common stock.
Two such rows were found by hand, and neither is in the 300-CIK sample, so the
probe does not measure how often it happens:

| CIK | panel ticker | SEC `tickers` | Stooq carries | what the panel row is keyed to |
|---|---|---|---|---|
| 0000936340 DTE Energy | `DTB` | `DTE, DTW, DTB, DTG, DTK` | `DTE`, 14,274 bars from 1970 | a baby bond, not the common |
| 0001137774 Prudential Financial | `PFH` | `PRU, PFH, PRH, PRS` | `PRU`, 6,204 bars from 2001 | a preferred, not the common |

Both are firm-years that cannot be priced because the key names a security other
than the common stock. Nothing served on the panel row states a security type,
so a study on this data can only find such rows by hand and count them as ghosts
alongside the genuine ones.

## Ghosts already look different on the day they enter

Medians at the December snapshot, before any outcome, n = 30,045 priced and
13,429 ghost:

| at entry | priced | ghost |
|---|---|---|
| revenue | $1,085m | $293m |
| Altman Z (n = 22,697 / 9,508) | 3.10 | 2.06 |
| health score (n = 26,759 / 12,245) | 65 | 60 |
| operating margin | 7.9% | 3.1% |
| net margin | 5.0% | 1.0% |
| Piotroski F | 5 | 4 |
| accruals ratio | -4.8% | -6.2% |
| asset growth | 5.0% | 3.3% |
| **capex intensity** | **2.92%** | **2.80%** |

Revenue at the 10th, 50th and 90th percentile is $49m / $1,085m / $14,098m
priced against $23m / $293m / $3,490m ghost. **Capex intensity is the one metric
on this list that does not separate the cohorts**, which is what decides the
first of the two consequences below.

![Health score and Altman Z at entry, ghost against priced](charts/ghost-entry-profile.png)

The gap widens over the sample: median Altman Z at entry was 4.02 priced against
3.14 ghost in 2012 and 2.36 against -0.26 in 2025, and the median ghost
operating margin turns negative from 2021 onward.

## Followed forward in the filings, with no prices at all

| next fiscal year, or 2-year exit | priced | ghost |
|---|---|---|
| panel exit within 2 years | **1.98%** (n = 22,024) | **34.37%** (n = 10,776) |
| median operating-margin change | +0.16pp | -0.23pp |
| share with a 5pp or larger operating-margin drop | 18.21% | 24.78% |
| median revenue growth | +6.05% | +4.36% |
| share with declining revenue | 29.97% | 37.56% |
| share with a health-score drop of 10 or more | 26.18% (n = 22,266) | 32.84% (n = 8,822) |

The base is **24,917 priced and 9,673 ghost one-year transitions**; the two
margin rows are measured on the **24,818 / 9,623** of those with a next-year
operating margin on file. Ghost firm-years leave the filing universe **17.4x**
more often, and **89.5% of all 4,140 panel exits in the base are ghost
firm-years**. The margin, revenue and health rows are measured only on firms
that filed again, so they describe the survivors of the ghost cohort and the
true ghost distribution is worse than the table shows.

![Forward fundamentals outcomes, ghost against priced](charts/ghost-forward-outcomes.png)

**Placebo.** 200 random 50/50 splits of the priced cohort. The mean placebo gap
is 0.06pp or smaller on every metric, and the observed ghost-minus-priced gaps
are 8 to 171 times the placebo standard deviation: exit 170.6x, revenue decline
14.8x, margin drop 13.7x, health drop 10.7x, median revenue growth 10.2x, median
margin change 8.5x. Every observed gap is **more than 4.8 times** the 95th
percentile of the absolute placebo gap; the smallest ratio, on the median margin
change, is 4.83x.

![Observed gaps against 200 random splits of the priced cohort](charts/ghost-placebo.png)

**Out of sample.** Entry-year halves agree. 2010-2017 (n = 16,702 transitions):
ghost exit 28.2% against priced 1.7%, margin drop 22.4% against 14.5%.
2018-2025 (n = 17,888): 42.6% against 2.1%, and 29.5% against 20.9%.

**Strict ghosts.** Dropping the 12% of ghost firm-years whose CIK still files
(n = 8,406 remaining ghost transitions) changes nothing qualitative: exit 38.5%
against 2.0%, margin drop 25.0% against 18.2%, median margin change -0.27pp
against +0.16pp.

**Size and sector.** The median ghost is just over a quarter the size of the
median priced firm, so the gaps were re-averaged inside year by revenue-quintile
cells (and year by size by sector, 763 cells, n = 33,283) that hold both
cohorts. The margin-drop gap falls from 6.57pp raw to 4.99pp and then 4.40pp;
the revenue-decline gap rises from 7.59pp to 9.90pp and then 9.21pp; the exit
gap is 34.61pp against 32.39pp raw. About a third of the margin gap is size and
sector composition and the rest is not.

## Two consequences, failing in opposite directions

![Boom cell and health-bucket exit, full universe against priced only](charts/ghost-consequence.png)

### The capital-cycle boom cell survives pricing, with a caveat

Top-quintile capex intensity and top-quintile asset growth, two fiscal years
forward:

| | n | median change in operating margin | share with a 5pp or larger drop |
|---|---|---|---|
| full universe | 1,147 | -1.83pp | 37.4% |
| priced only, re-ranked | 830 | -1.12pp | 34.6% |
| priced only, full-universe cuts | 784 | -1.10pp | 34.8% |
| ghost only, re-ranked | 314 | -3.23pp | 43.6% |

Dropping the ghosts moves the median by +0.70pp and the 5pp-drop frequency by
-2.8pp. The boom-versus-quiet gap in that frequency goes from **+16.6pp to
+14.6pp**, a 12% attenuation.

**That attenuation is not clearly a survivorship effect.** Dropping 200 random
subsets of the same size and recomputing the gap the same way gives
**16.55pp ± 1.17**, a 95% range of 14.5 to 18.8pp. The observed priced-only gap
of 14.58pp sits at **z = -1.69**, and 4% of random drops land at or below it. At
this n the capital-cycle base rate is **not measurably damaged by
survivorship**, which is a weaker statement than saying it is robust to it.
Ghosts are 31.6% of the boom cell against **25.9% of the two-year transition
pool the cell is cut from**, so they are over-represented in it by 5.7pp, and
the cell is not reweighted enough to reverse.

![The boom cell against 200 random drops of the same size](charts/ghost-boom-random-drop.png)

### The low-health exit rate collapses, and that is close to arithmetic

| health at entry | full universe | priced only | ghost only |
|---|---|---|---|
| 0-30 | 21.8% (n = 3,697) | 4.1% (n = 1,895) | 40.5% |
| 30-50 | 15.2% | 2.5% | 34.4% |
| 50-70 | 12.1% | 2.1% | 33.5% |
| 70-85 | 9.0% | 0.9% | 31.8% |
| 85-100 | 8.1% | 0.9% | 30.4% |

The low-health two-year exit rate falls from **21.8% to 4.1%, a factor of
0.19**. The relative gradient survives and steepens (bottom over top goes from
2.7x to 4.3x), but the level is unrecoverable: a priced-only sample reports that
one in twenty-four distressed filers disappears where the panel says one in five
does.

**This one is close to arithmetic and is not an independent test.** A firm that
leaves the panel almost always leaves the price file, so the ghost definition
and the exit outcome share most of their information, and 89.5% of exits are
ghosts. The genuinely independent parts of this document are the entry profile,
the margin and revenue outcomes among survivors, and the boom cell.

The two results fail in opposite ways for the same reason: survivorship
attenuates a result exactly to the degree the outcome correlates with the ghost
flag. Capex intensity does not correlate with it, so the capital-cycle base rate
survives. Disappearance is what the ghost flag is, so the exit rate does not.

## What would break it

1. **The ghost flag is measured in August 2026 and applied to snapshots back to
   2010.** It embeds the future relative to every entry date. Nothing here is
   predictive and none of it is a screen: this is a description of what a join
   discards.
2. **Panel exit is not distress.** An acquisition produces the identical
   footprint, and closings between the last snapshot and the file edge are
   visibly in the cohort. Nothing here resolves that.
3. **Forward outcomes are conditional on filing again.** For the ghost cohort
   that condition removes about a third of the group within two years, and it
   removes the worst of it.
4. **The join key is the panel's ticker**, and it is neither point-in-time nor
   always the common stock. The two rows named above are the shape of that, and
   the probe cannot measure how common they are because neither is in its sample.
5. **Nothing here separates delisting from the price bundle's own composition.**
   The bundle carries nasdaq, nyse and nysemkt only, so a filer that moved to
   OTC while continuing to file is a ghost for a reason that has nothing to do
   with the panel.
6. **Coverage ramps before 2012** (416 firm-years in 2010, 1,188 in 2011 against
   about 3,000 a year afterwards), so the 2010-11 shares rest on small n and a
   different filer mix.
7. **The health score used here is a July 2026 export joined onto a September
   panel** on (as_of_date, CIK), covering 89.1% of priced and 91.2% of ghost
   firm-years. The near-identical coverage means the join does not itself sort
   the cohorts. The score is dated per snapshot rather than broadcast from one
   date; see [survival-clock.md](survival-clock.md) for what its vintage can and
   cannot contaminate.

## Limits of the data as published

Every price join in this repository runs through the panel's ticker, and that
ticker is neither dated nor marked with a security type, so a study on this data
cannot separate a firm that stopped trading from one whose key names a preferred
or a baby bond without going to SEC's own exchange record ticker by ticker.

The export's `listed_until` column closes part of that gap. It dates 3,104 of
the 3,672 firms that leave the panel from a Form 25 or Form 15, and it reaches
**84.8% of ghost firm-years and 96.6% of stopped-filing ghost firm-years**
(form25 9,747 firm-years against form15 1,624), so "stopped filing" above is in
nearly every case a dated delisting. The column also finds what the probe could
only bound: **120 dated firms have a ticker with a live series in the bundle,
544 firm-years counted as priced above**, of which **114 firm-years over 25
firms** pass the 14-day close test at a snapshot that precedes the listing end
and then read a successor's prices past it. That is 0.4% of usable firm-years,
and `forward_paths` now stops at the date. Every one of those 25 is a symbol
whose series spans the listing end rather than one reissued after it: a reissued
symbol has no close before the end date, so it never passes the entry test at
all, and its exposure is entirely in the forward window.

What the column still does not do is say why the listing ended. A Form 25
follows an acquisition, a going-private and a deregistration after a deficiency
notice alike, and that difference is the entire economic content of the distress
result. The price file holds no series for a delisted issuer, not even a final
close or a cumulative return stub to the delisting date, so the survivorship gap
can be described from the filings but never closed from inside this data. For
the 568 firms that leave with no form on file, "panel exit" remains an inference
from a CIK's last row.

## Disclosure

Companies are named only as facts they exhibit in this data.

Distill Markets Pty Ltd, the publisher of this repository, operates the paid data
service this study uses. Authors and the publisher may hold positions in
securities named here. Everything above is general information derived from
public SEC filings and from a price file the author holds. It is not financial
product advice, does not consider your objectives, financial situation or needs,
and past patterns do not guarantee future results. See [NOTICE](../NOTICE).
