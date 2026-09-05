# Traps in joining fundamentals to prices

Every trap here was hit for real while building the studies in `findings/`.
Several would have produced a published wrong number. Read this before
computing anything that divides a price by a filed figure.

## Trap 1: split-basis mismatch

Stooq prices are split-adjusted across all history. The filer restates
`weightedAverageSharesDiluted` only two fiscal years back from the first annual
filing after a split, and no further. On any window crossing an older split,
price and share count silently disagree by the split factor.

Seen in practice: one issuer's diluted count went from 203.5M to 1,028M in one
year, a 5x step that was a split, not dilution. Using the earlier year as filed
put its baseline market cap at one fifth of truth and inverted the whole
decomposition. The price file confirmed it independently: the pre-split close
times five was where the stock actually traded.

Protocol: run `joins.split_basis_flags` on the share series for every name.
Any year-over-year ratio near an integer or its reciprocal is a candidate
split, and only a candidate: trap 14 measured 37% of these flags as
contradicted on one pool. Pass the flags through `joins.corroborate_flags` against the
never-restated `sharesOutstanding`, then give `joins.rebase_shares` the
corroborated ones only. In a 19-name cohort one name was affected inside the
window, and three more had splits just outside it that break on a longer one.

## Trap 2: `sharesOutstanding` is never restated

Use `weightedAverageSharesDiluted` for anything multi-year. `sharesOutstanding`
is a period-end count on the basis in force when filed and steps at every
split. The API's field note says this explicitly. Believe it.

## Trap 3: the price file is survivorship-biased and the fundamentals are not

Stooq's file set is current listings. Every delisted issuer is absent
entirely. Distill resolves delisted issuers by design and returns
`delistedAt`. A joined backtest therefore inherits survivorship bias from the
price side only, while the fundamentals look complete. That is the more
dangerous configuration. Any cohort study using these prices is biased toward
survivors and must say so. `examples/return_tests.py` reports its match rate
for exactly this reason.

## Trap 4: lookahead in fiscal-year-anchored ratios

A price-to-sales at a fiscal year-end using that year's revenue uses a number
not filed until weeks later. Correcting one cohort to use only the most recent
annual actually on file at the anchor date moved a multiple-expansion figure by
65 percent and flipped one name from expansion to compression. Direction held;
magnitudes were materially wrong.

For true no-lookahead work use
`GET /api/v1/sec/fundamentals/{ticker}/as-of/{date}` rather than approximating
with the prior fiscal year.

## Trap 5: foreign private issuers return unflagged native currency

A 20-F filer can come back with `revenue`, `netIncome`, `stockholdersEquity`
and `sharesOutstanding` all null and `grossProfit` populated in its home
currency, in the same field that holds USD for every other company.
`reportingCurrency` is the only field that says which currency the numbers are
in, so read it on every single-ticker response and exclude foreign private
issuers from any cross-sectional ratio. `screen` omits them already; single
ticker lookups do not.

## Trap 6: endpoints disagree about coverage

`/sec/fundamentals/{ticker}` can succeed where
`/sec/fundamentals/{ticker}/history` returns 404 for the same ticker, and the
404 for an uncovered issuer is byte-identical to the 404 for a typo. Maintain
your own coverage list, and use `/sec/profile/{ticker}` to tell "not a ticker"
from "outside coverage".

## Trap 7: pre-2009 EPS cannot be combined with modern prices

`/sec/pre2009/{ticker}` serves EPS as filed, on the then-current share basis.
Prices are adjusted to today. Across 25 years of splits, any price divided by
that EPS is invalid. Only split-invariant quantities cross that boundary:
revenue, net income, assets, and the price return itself. Build long
comparisons from those, and never state a multiple level across the boundary.

## Trap 8: pre-2009 coverage gaps are real

The pre-2009 corpus withholds concept-years pending verification rather than
guessing. A peak-to-trough window may not contain the year you want. Check
`factCount` and the returned years before assuming, and quote the verification
tier with its sample size and interval when citing.

## Trap 9: a pool selected on being priced has a 100% match rate by construction

The moment you build a working set by keeping the tickers that have a price
series, the match rate you can compute inside that set is 100% and it measures
nothing. It is a definition. Four separate studies reported it, and in each of
them the survivorship exposure sat upstream, in how the pool was built, not in
the join being reported.

Report the honest denominator instead: the match rate over the **full** universe
the pool was drawn from, and the count of distinct issuers that carry no price
at all. On a 2026-08 current-listings bundle against a point-in-time SEC panel
that is 66.8% of December firm-years and 2,904 of 6,038 distinct tickers with no
price at all. Every drawdown rate, tail share and fall count computed on the
priced subset is then a floor, and nothing inside the data bounds by how much.
See `findings/ghost-cohort.md` for what the missing third looks like in the
filings.

## Trap 10: count revisions per filing, never per fact

`/sec/revisions/{ticker}` returns **one row per revised fact**. A single annual
report can recast dozens of facts across several period ends, and the endpoint
has no per-filing view. Counting rows counts one filing many times over.

Measured over 707 tickers with a cached response: 10,878 revised facts arrive in
**2,552 revising filings**, so counting facts inflates the event count by
**4.26x** (mean 4.26 facts per filing, median 2, maximum 44). It is not a few
outliers: removing the five tickers with the most facts leaves 4.16x. It is also
not evenly spread, so it is not a uniform scaling you can divide out: 33% of
revising filings revise exactly one fact.

Dedupe on `changedAccession`, falling back to `changedFiled` when it is absent.
Both keys give the same count. And read the two fields carefully: `relDelta` is
the original-to-latest step while `changedFiled` names the **first** filing that
changed the value, so on a fact revised more than once the magnitude and the
date describe different steps.

## Trap 11: a Form 4 row carries the transaction date, not the filing date

`/sec/insider/{ticker}` returns `transactionDate` and `accessionNumber` and no
filing timestamp. Form 4 is due within two business days of the transaction, so
an event study anchored on `transactionDate` puts days that precede publication
inside its forward window and attributes them to the event.

Measured on 234 open-market purchase clusters at 121 firms in 2024-2026, the
purchase-minus-placebo spread over **trading days 0 to 2 alone** is
+1.41pp [+0.97, +2.21], which is **38%** of the +3.75pp twenty-day spread.
Shifting every event forward two trading days leaves +3.00pp at +20 days, and
takes +250 days from +5.32pp to +0.00pp.

The response carries no filing date, so report all three: the unshifted number,
the days-0-to-2 component, and the number under a two-trading-day shift.
Anything measured entirely **before** the event needs no such correction.

Two coverage facts from the same endpoint. `fromDate` echoes the requested
window and says nothing about coverage: it is returned as a 2016 date for
issuers whose oldest actual transaction is in 2024. And `parsedFilings` can
exceed `form4FilingsInWindow` (25 of 235 tickers), so the pair does not read as
a parsed-of-total ratio.

## Trap 12: a 13F concentration change is a lagged restatement of the quarter behind it

A quarter-end 13F aggregate describes positions as at the quarter-end, filed up
to 45 days later. Sorting firm-quarters on the quarter-over-quarter change in
institutional shares per institution, the **63 trading days ending at the
quarter-end** run +8.10% to -12.38% across the five quintiles, a 20.5pp
[+18.79, +22.06] monotone spread, strictly monotone in 400 of 400 clustered
draws. The 63 trading days starting at the filing deadline span 1.0pp and do not
order at all.

The mechanism is arithmetic: Spearman between the concentration change and the
holder-count change is -0.71. When a price falls, institutions leave the
register, the count drops, and the shares that remain are divided among fewer
holders, so measured concentration rises.

Two consequences. Any 13F-derived variable is a coarse description of the
quarter already past, so a study that finds it "predicts" a drawdown needs to
check the backward window first. And a cross-sectional cut on the **size** of a
13F move measures firm volatility: a firm's own standard deviation of that
change, one number per firm with no timing content, sorts the 20%-fall share by
+20pp on its own, and a within-firm shuffle reproduces 88% of the raw tail gap.
Rank within firm from the start.

## Trap 13: the diluted share count can arrive in the wrong unit

Trap 2 says to use `weightedAverageSharesDiluted` and never `sharesOutstanding`
for multi-year work. That is still right, and the recommended field still needs
a check at the point of use. Over 424 tickers with both fields on file, the
ratio between them **for the same fiscal year** is 10x or more apart on
**1.07%** of filer-years and 2x or more apart on 2.37%. That rate is measured
on one priced pool of 3,634 filer-years, not a universe rate.

The shape of the worst cases is a unit switch inside one response: several
consecutive years served in **millions** while every other year of the same
response is served in raw shares. Fourteen filer-years over seven tickers report
a diluted count below 100,000 against more than a million shares outstanding.

It is machine-detectable at the point of use, because `netIncome / epsDiluted`
reconstructs the count the response should have carried.
`joins.share_series_sanity` flags any fiscal year where
`sharesOutstanding / weightedAverageSharesDiluted` leaves [0.5, 2.0]; run it
before feeding the series to `joins.rebase_shares` or `joins.decompose`, which
consume it unchecked. A weighted-average diluted count and a year-end
outstanding count for the same fiscal year cannot differ by a split factor, so
a ratio of 5x, 10x or 102x is a unit break and not an issuance. It is behind
three of the fifteen "contradicted" verdicts in the split-flag base rate below.

## Trap 14: a split-basis flag is a candidate, not a split

The base rate behind trap 1. `joins.split_basis_flags` finds a **step** in the filed diluted-share series,
and a step is not proof of a split; `joins.corroborate_flags` is the test. Over 473 tickers, 32 (7%) raise at least one
flag, 41 flags in total: **46% corroborated** against the never-restated
`sharesOutstanding`, **37% contradicted**, **17% untestable** (computed
before the `corroborate_flags` NaN fix in CORRECTIONS entry 20; the market-cap
study's rate on the fixed helper is 95 corroborated, 82 contradicted and 47
untestable over its own pool). Most of the
contradicted ones are real share-count growth at an IPO or a conversion, where
rebasing would be wrong.

Confirm each flag before `joins.rebase_shares`. The confirmation compares the
flagged factor against `sharesOutstanding` in the two to three fiscal years
after the flag year, because the filer restates the diluted series about two
fiscal years back while the outstanding count steps at the split's own year. The
tolerance band, not the window length, is the fragile part of that test:
corroborated ranges 44% to 54% across reasonable bands while the window makes no
difference from two to four years.

## Trap 15: a "next" fiscal year is usually the one the price already ran through

A December snapshot carries the fiscal year on file at that date, which for
three quarters of filers is the year that ended the previous December. Sort
firm-years on the trailing twelve-month return and read the "next" filed year,
and on 72% of rows that year overlaps the price window completely; 1.5% are
clean. The spreads that result (revenue growth 16 points, margin 6 points,
health score 14 points between the bottom and top return deciles) are the
market and the filings describing the same year. Stepping one filed year at a
time, four of six of them reverse sign by the third step, and the one that
keeps its sign is 95% reproduced by a within-firm shuffle. Date every fiscal
period from `periodEnd` in the history endpoint and require the period to end
before the price window starts, or the direction of causality is an artefact
of the calendar.

## Trap 16: a December panel row's annual figures are a median 275 days old

A fiscal year enters the panel at 74% of March quarter-ends and 8% of December
ones, so the annual block on a December row was filed the previous spring. A
study that treats the December row as "this year's report" measures a change
that is three quarters stale, and a forward window from that date starts long
after the market read the filing. The record-refresh anchor (the first
quarter-end at which a fiscal year appears) puts the change at most one
quarter old and sits a median of 37 days after the 10-K's publication, 99% of
the time after it.

## Trap 17: cumulative paths do not difference into segment returns

`x_6 - x_3` is not the return over months three to six, and differencing
`analysis.abnormal_path` day by day is not the daily abnormal return: each
cumulative value is measured from the base close, so the difference of two of
them is a difference of levels, not a compounded segment. Compound each
segment from its own start (`(1 + x_6) / (1 + x_3) - 1`) or compute daily
abnormal returns bar to bar. Three studies wrote a segment helper before this
was written down.

## Verification protocol

Every load-bearing figure in `findings/` was checked at least two ways.

1. Cross-endpoint: `/fundamentals/{t}/history` against `/fundamentals/{t}` on
   overlapping years.
2. Against the API's own valuation lane: feed your price to
   `/sec/valuation/{t}` and compare its market cap to your `price x shares`.
   A small, explainable gap (diluted versus period-end count) is expected.
3. Price sanity: `stooq.split_scan` on every name before trusting a long
   return. Resolve every hit to a real event or treat the series as suspect.
4. Point-in-time: the as-of endpoint at a past date should equal
   latest-filing-wins unless a revision intervened.

The largest error found while building these studies was in the analysis
code, not the data: indexing net income as a share count produced a market cap
in the tens of trillions and a spurious correlation that survived until the
magnitude looked absurd. Sanity-check magnitudes against something you know.

## Cost notes

- `/fundamentals/{t}/history` is a few thousand tokens per call when read by an
  agent, most of it a methodology note repeated verbatim. Cross-sectional work
  means fanning out one call per ticker.
- `/sec/insider/{t}`: the summary covers the whole window regardless of
  `limit`, and `totalTransactions` is the number to trust. Several names report
  partial parse coverage and are explicitly a lower bound.
- `/sec/revisions/{t}`: use `minDelta=0.05` to stay under the detail cap. The
  free tier gives counts only.
- `screen`: `piotroskiF` is the latest quarterly score while every other
  metric is the last full fiscal year. Two vintages on one row.
- Provenance fields (`revenueConceptUsed`, `totalLiabilitiesSource`,
  `ebitdaBasis`, `capExConceptUsed`, `depreciationConceptUsed`) change what a
  number means. Read them.
