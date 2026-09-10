# Doing research on this data

The short form of this document is [AGENTS.md](../AGENTS.md) at the repository
root, which is what an agent reads first. This is the long form.

Onboarding for anyone, human or agent, about to run a study against the Distill
Markets API and a price file you hold. It states what the two sources are for,
what shapes they come in, the places a join between them goes wrong, what a
finished study has to contain, and how to spend an API budget.

Read [docs/traps.md](traps.md) alongside this. Every trap there was hit for real
and several of them would have produced a published wrong number.
[CORRECTIONS.md](../CORRECTIONS.md) is the log of the ones that did, and it is
worth reading once before you start: most of its entries are a researcher
trusting a helper, a field, or a null that looked fine.

## What the two sources are for

Distill serves **what companies filed, as it was knowable on a date**: SEC
fundamentals point-in-time, for every filer including ones that later delisted,
with the revision history of every fact. A daily price file serves **prices for
names that still trade**.

The interesting seam is where those differ. What the market paid against what
was on file at the time, and what a current-listings price file cannot see at
all. A pattern any free dataset could show is less interesting than a smaller
one only this pairing can show.

Two structural consequences follow from that sentence, and they shape every
study:

- **The fundamentals are complete and the prices are not.** A delisted issuer
  is fully present on the filings side and entirely absent on the price side.
  That configuration is harder to catch than the reverse, because the
  fundamentals look complete while the joined result is a survivor's result.
- **The point-in-time side is the part that is hard to get elsewhere.** A study
  that reaches for the latest-filing-wins value when a dated one exists has
  thrown away the thing that made the question answerable.

## Data shapes

### The panel

One call to `GET /api/v1/sec/screen/export` returns the whole point-in-time
grid: one row per (CIK, quarter-end) from 2009, roughly 28 metrics per row, on
the order of 200k rows and 6,000 tickers. Columns:

```
as_of_date, ticker, cik, sector, fiscal_year, revenue, net_margin, gross_margin,
operating_margin, debt_to_ebitda, net_debt_to_ebitda, rnd_intensity, dso, dio,
capex_intensity, buyback_intensity, net_dilution, piotroski, interest_coverage,
dpo, ccc, altman_z, fcf_margin, fcf_conversion, asset_growth, accruals_ratio,
m_score_5, gp_to_assets, is_listed_equity, listed_until, listing_end_source
```

A Free key gets the latest snapshot without `piotroski`, `altman_z`,
`accruals_ratio` and `m_score_5`; Analyst adds them; Pro gets the grid. The
200-firm sample on the release page (README, Install) is the grid's shape
with the grid's base rates, and `client.panel_path()` finds whichever is on
disk.

Facts about it that change how a study is written:

- Each row is what the API would have reported **on that date**. Filings and
  revisions that arrived later are excluded by construction, which makes naive
  backtest designs honest by default.
- Coverage ramps from 2009 to 2012 (tens of rows in 2009, thousands a year from
  2012), so studies over the panel start at 2012 unless they say why not.
- Null rates are structural and vary widely: `ccc` about 70%, `rnd_intensity`
  69%, `debt_to_ebitda` 65%, `altman_z` 46%, `net_margin` 2%. Financials and
  REITs legitimately lack inventory- and EBITDA-shaped metrics, and Altman Z has
  **0% coverage** in Financials and Real Estate, so any Altman cohort is a
  different universe from a health-score cohort.
- `piotroskiF` in screen results is the latest quarterly score while every other
  metric is the last full fiscal year. Two vintages on one row. `POST /sec/screen`
  takes a `fields` array to project row columns, and returns the four scored
  metrics null on a Free key with a note saying so.
- `listed_until` and `listing_end_source` (`form25` exchange delisting,
  `form15` Section 12 deregistration, `migration`, `crawl`) are set on every
  row of a firm whose listing has ended and empty otherwise. On the export of
  2026-09-07, 3,104 of the 3,672 firms whose last row precedes the final
  snapshot carry one (form25 2,469, form15 515); the 568 without stopped filing
  with neither form on file, are small (median last revenue $27m against
  $303m), and their exit stays an inference from the last row (trap 3). The
  date runs a median 50 days after the firm's last panel row. An acquisition
  and a failure both end in a Form 25, so the source does not separate them.
- **A ticker is reused.** 303 of those 3,104 ended firms still answer to a live
  series under their last panel ticker, and for 202 the series begins after the
  listing end, so it is another company's. On the December universe of the ghost
  study that is 120 firms and 544 firm-years counted as priced, of which 114
  firm-years over 25 firms also pass the 14-day fresh-close test at a snapshot
  preceding the listing end. Every one of those 25 is a series that spans the
  listing end rather than a reissue: a reissued symbol has no close before the
  end date, so it never passes an entry test and its exposure is entirely in the
  forward window. Keep `listed_until` on the frame you pass to `forward_paths`:
  it reads no return past that date and sets `delisted_in_window` from it.
- There is no market capitalisation and no share count on the panel row, so a
  size control has to use revenue, which conflates scale with business model.
- The `ticker` is current, is not point-in-time, and is sometimes not the common
  stock. See "the join key" below.

### Per-ticker responses

- **`/sec/fundamentals/{t}/history`** returns `years` newest first, ten fiscal
  years by default and at least 20 on request, each with `periodEnd`, `revenue`,
  `operatingIncome`, `netIncome`, `operatingCashFlow`, `capEx`, `freeCashFlow`,
  `totalAssets`, `sharesOutstanding`, `epsDiluted`,
  `weightedAverageSharesDiluted` and provenance fields, plus
  `earningsReleaseDate` and `earningsReleaseSource` (8-K Item 2.02) per year,
  null before the summary's `earningsReleaseCoverageFrom` (2023-11-14). The
  single-ticker `/sec/fundamentals/{t}` carries `nextEarningsDateEstimate` and
  `nextEarningsDateConfidence`. Use
  `weightedAverageSharesDiluted` for anything multi-year, subject to trap 13.
  A long methodology `note` is repeated verbatim in every response and is most
  of the payload by token count.
- **`/sec/fundamentals/{t}/as-of/{date}?period=annual`** returns `values`, a
  list of `{conceptGroup, periodEnd, value, filedAt, accessionNumber}`. Filter
  on `conceptGroup`. This is the no-lookahead lane; approximating it with "the
  prior fiscal year" moves multiples materially (trap 4). A Free key gets ten
  of these per UTC day, a 404 counts, and the eleventh is a 429
  `subquota_exceeded` carrying `retryAfter`; Analyst lifts the cap.
- **`/sec/revisions/{t}`** returns `revisions` rows with `originalValue`,
  `latestValue`, `relDelta`, `originalFiled`, `changedFiled`,
  `changedAccession`, `originalBasis` and `changeType` (`multi-period-recast`,
  `entity-change`, `amendment`, `unclassified`). One row per **fact**; see trap
  10. There is no form type on `changedAccession`, so a report filed to correct
  is indistinguishable from one that re-presents a prior year in its
  comparatives.
- **`/sec/insider/{t}`** takes `limit`, `offset` and `windowDays` only, caps
  `limit` at 500 server-side, and pages on `nextOffset`. The summary counts
  cover the whole window regardless of paging. Rows carry `transactionDate` and
  no filing date (trap 11). `codeDescription` separates `P` open-market purchase
  and `S` open-market sale from `A` grant, `F` tax withholding, `M` option
  exercise, `G` gift and `J` other, and `M` rows appear twice, once derivative
  and once not. The response carries `coverageFrom` (2024-01-02) and a
  `coverageNote` when the window predates it, and several issuers carry a
  `coverageNote` of their own; counts are then a lower bound.
- **`/sec/ownership/{t}/history`** returns `periods` with `holdersCount`,
  `filerCikCount`, `totalValue`, `totalShares`, `newHolders`, `exitedHolders`,
  the three QoQ fields, `isPeriodComplete` and `corporateActionSuspected`. Eight
  quarters by default and 38 with `?quarters=40`, which is the corpus floor.
  No concentration field at any historical date.

### The price file

A current-listings end-of-day bundle. Closes are split-adjusted retroactively to
the download date, so returns are **price returns and omit dividends**, and the
file set is current listings, so **delisted issuers are absent entirely**.

The second property is the one that bites. A delisted symbol is deleted rather
than ended, so a "the series stopped" event is not estimable from such a file at
all: on one 2026-08 bundle, no symbol in 13,239 readable files ends before
2026-02-06 and none before 2026-01-01. Any flag in a derived frame that appears
to mark delisting is marking the right edge of the file.

## API shapes that bite

The full list, each hit for real, is [docs/traps.md](traps.md). The short form,
in the order they tend to be hit:

| # | trap | one-line form |
|---|---|---|
| 1 | split-basis mismatch | the filer restates the diluted series about two fiscal years back and no further, so a window crossing an older split disagrees with the price by the split factor |
| 2 | `sharesOutstanding` is never restated | use `weightedAverageSharesDiluted` for anything multi-year |
| 3 | the price file is survivorship-biased and the fundamentals are not | report the match rate, and read every joined result as a floor |
| 4 | lookahead in fiscal-year-anchored ratios | a year-end multiple using that year's revenue uses a number filed weeks later; use the as-of endpoint |
| 5 | foreign private issuers return unflagged native currency | `screen` omits them, single-ticker lookups do not |
| 6 | endpoints disagree about coverage | a 404 for an uncovered issuer is byte-identical to a 404 for a typo; `/sec/profile` separates them |
| 7 | pre-2009 EPS cannot be combined with modern prices | only split-invariant quantities cross that boundary |
| 8 | pre-2009 coverage gaps are real | check `factCount` and the returned years |
| 9 | a pool selected on being priced has a 100% match rate **by construction** | report the match rate over the universe the pool came from |
| 10 | count revisions **per filing**, not per fact | one annual report recasts dozens of facts; per-fact counting inflates events 4.26x |
| 11 | a Form 4 row carries the **transaction** date, not the filing date | Form 4 is due within two business days; 38% of one +20-day spread sat in days 0 to 2 |
| 12 | a 13F concentration change is a lagged restatement of the quarter behind it | 20.5pp of monotone spread backward, 1.0pp forward; rank within firm before cutting on the size of a move |
| 13 | the diluted share count can arrive in the wrong unit | some years arrive in millions inside a response otherwise in raw shares; `netIncome / epsDiluted` detects it |
| 14 | a split-basis flag is a candidate, not a split | 46% corroborated, 37% contradicted, 17% untestable over 473 tickers (computed before the `corroborate_flags` NaN fix in CORRECTIONS entry 20; the market-cap study's rate on the fixed helper is 95/82/47 over its own pool) |
| 15 | a "next" fiscal year is usually the one the price already ran through | a December snapshot's next filed year overlaps the price window completely on 72% of rows; date every period from `periodEnd` |
| 16 | a December panel row's annual figures are a median 275 days old | a fiscal year enters the panel at 74% of March quarter-ends, so anchor on the record refresh rather than on the December row |
| 17 | cumulative paths do not difference into segment returns | compound each segment from its own start, or compute daily abnormal returns bar to bar |
| 18 | a reused symbol in the price bundle may not be a company at all | a delisted issuer's ticker resolves to a fund file; `stooq.index` is equities only, and the diff against `include_etfs=True` is the exposure |
| 19 | a delisted company cannot be named from the free SEC file, and asking by ticker names someone else | 0.0% of 3,104 ended filers are nameable from `company_tickers.json` against 88.7% of the listed; the ticker-keyed profile route returned a different CIK on 12.4% of them |

Two more shapes worth knowing before you design around them:

- **The join key.** The panel's `ticker` is current, is not point-in-time, and
  is occasionally a preferred or a baby-bond symbol rather than the common
  (`DTB` for DTE Energy, `PFH` for Prudential Financial). Ticker collisions also
  exist in both directions: some tickers map to more than one CIK across the
  export, and some resolve at SEC to a different CIK than the panel gives. Join
  on CIK wherever both sides carry one. The cost of not doing so is measured:
  over the 3,104 panel firms whose listing has ended, a ticker-keyed
  `/sec/profile` lookup returned a different CIK 386 times, 12.4%, and a ticker
  join to the SEC's own current file returned another company for all 266 whose
  symbol was still in it (trap 19, `research/naming-the-dead/`).
- **Endpoint coverage is not universe coverage.** Firms present in the current
  panel export can 404 on `/history` under the panel's own ticker. Measured on a
  300-firm sample of a December-2017 universe, 65.0% [59.6, 70.4] are served
  today, and about a tenth of the 404s are firms still in the panel's final
  year. If your study needs a past universe, the universe is the first thing to
  measure, not the last.

## The output contract for a study

A study that lands in `findings/` states facts and methods. It does not
recommend, rate, or value a named security. Five things are not optional.

**1. `n` everywhere, in the unit you actually resampled.** Firm-years are not
firms. A pool of 25,619 firm-years over 2,667 firms is 9.6 rows per firm, and
every table carries both counts. State the window with the n: "n = 1,116 events
over 702 firms, 2017-2024" rather than "n = 1,116".

**2. A placebo, and cluster it by firm.** Repeat firm-years are the default
shape of this data, and a row-level shuffle breaks a dependence the observed
statistic keeps, producing a null that is far too tight. One published z of 15.3
became 7.0 under a firm-clustered shuffle. Three forms are worth knowing:

- **clustered shuffle**: permute the label among firms, so each firm carries one
  label for its whole history.
- **within-firm shuffle**: permute a firm's own values across its own periods.
  This keeps every firm-level property and destroys all timing, and it is the
  test that separates "which firms" from "which periods". It removed a 9.5pp
  tail finding that four other controls left standing.
- **cluster bootstrap**: resample whole firms with replacement for the interval,
  and say so, including when a control cohort is reused across events and
  therefore is not in the interval.

For an event study, add a **date placebo** placed where it cannot overlap the
event window. A one-period-back placebo overlapped the event window for 59.9% of
events in one study, because the events themselves were a median of 368 days
long.

**3. The match rate, on the honest denominator.** See trap 9. If the working
pool was selected on being priced, say what fraction of the universe it came
from carries a price at all, and state which direction the missing names bias
the result. "Every rate here is a floor and nothing in this data bounds by how
much" is an acceptable ending; a 100% match rate presented as a result is not.

**4. Reproducibility and vintage.** One script reproduces every number in the
write-up from files already on disk, run from the repository root, ideally with
no network call. State the data vintage of every source. Pin what you read: a
shared response cache being filled by other work moves denominators underneath a
running study, so a study whose base rate is "what is in the cache" writes its
own manifest of the exact list.

**5. The language.** Facts and base rates over cohorts. A named company appears
only as a fact it exhibits in the data. Never "undervalued", "buy", "target",
"should", "warns", "opportunity", or any sentence about where a price goes next.
If the result is a return spread, say what the spread was over what window with
what n, and stop there. Chart headlines are held to the same standard as prose,
and a headline states the fact with its n and its window. Write as if a
regulator will read it, because the publisher gives no financial advice.

**Negative results are results.** Write them up the same way. Three of the most
useful documents in `findings/` are nulls, and each is useful because of the
control that produced it rather than in spite of it. State what you needed that
did not exist and what data you wished you had; those two lists are the most
useful part of a null result.

## API budget etiquette

Every uncached call takes about a second.

- **Treat the API as a fallback, not something to loop over.** Cache aggressively and
  check the cache before spending. Never loop over a whole universe.
- **Set a budget before you start and report what you spent**, including
  overruns and what caused them. `client.request` negative-caches a 400 and a
  404 and re-raises them from disk, so a restarted probe does not pay twice for
  the same miss. Price the sweep first with `client.is_cached(path, **params)`,
  which is true for error entries too, and record `client.manifest()` at the
  start and the end of a run so a cache filled underneath the study shows up as
  a changed input.
- **Prefer the bulk lane.** One `screen/export` call returns the panel that
  would otherwise take hours of paged screen calls. Per-ticker endpoints do not
  batch, so a cross-sectional study over N tickers costs N calls against a
  60-per-minute limit, roughly 17 minutes per thousand.
- **Page rather than re-request.** Where an endpoint caps `limit` server-side,
  read the cap it reports and page on the offset it hands back.
  `client.get_paged(path, limit=500, **params)` follows `nextOffset`, caches each
  page under its own offset and stops on an offset that does not advance.
- **Expect a cold first touch, and handle the two failures.** First-touch
  latency on a path runs into seconds where a warm call is fast. A 200 carries
  no rate-limit headers, so honour `retryAfter` on the 429 rather than
  predicting it, and retry once on a transport error.
- **Keep the data out of the repository.** Responses, panels, price files and
  notebook outputs stay on your disk. See [CONTRIBUTING.md](../CONTRIBUTING.md)
  and [docs/data-sources.md](data-sources.md) for what each source's terms
  require, and run `python scripts/check_hygiene.py` before pushing.

## The helpers in the package

A helper moves out of a study and into `distill_toolkit` when a SECOND study
needs it. Until then it lives in the study that wrote it, because one use is not
yet evidence of a shape. The list below is what is there now, one line each;
every docstring carries the constraint the helper exists to hold, and several
carry a number that was paid for once already.

Reach for these before writing your own. A reimplementation that disagrees is
either a bug in your version or a finding about the helper, and both are worth
knowing before the study is written.

### `analysis`, the panel and the price file

| helper | what it is for |
|---|---|
| `december_snapshots` | listed, revenue-positive December rows with an unambiguous ticker |
| `match_rate`, `priced_flags`, `fresh_close_flags` | nominal against usable price coverage, which every study prints |
| `record_refresh_events` | the first quarter end a fiscal year appears at, which is the anchor at which a filed change is new (trap 16) |
| `exit_frame` | per-CIK last row, last refresh and exit flag, with the observability censor and the anchor as a parameter |
| `transitions`, `add_outcomes` | firm-years joined to their own snapshot n years later, with the forward changes |
| `forward_paths` | one row per priced firm-year with cumulative and market-adjusted returns at monthly horizons |
| `market_adjust_by` | each column minus its own cohort median, where the cohort key is the thing that fixes the window |
| `segment_returns` | compounded market-adjusted returns over arbitrary calendar-day segments, with a hard right edge (trap 17) |
| `event_window`, `abnormal_window`, `abnormal_path`, `path_between` | event-time returns from a fixed offset grid, a signed offset grid, or two anchors an arbitrary distance apart |
| `daily_abnormal` | bar-to-bar abnormal returns, which are not the difference of a cumulative path (trap 17) |
| `med_abs_ratio` | an event day's absolute move over the firm's own quiet days, pooled across firms of any volatility |
| `qcut_within`, `tercile` | rank-first quantiles inside a cohort, so a column with an atom at zero still splits |
| `decomposition_ladder` | the same sort read four ways, which separates "which firms" from "which of a firm's years" |
| `presample_label` | a firm label fixed on an early window and evaluated on a later disjoint one |
| `failure_times`, `kaplan_meier`, `survival_curve`, `crossing` | time to an event with censoring, and reading a level off the incidence |
| `cluster_bootstrap`, `cluster_boot_diff` | intervals that resample whole firms, for a statistic and for a difference of two cohorts |
| `cluster_resample_index`, `boot_ratio` | the same resampler exposed, for a statistic that is not a function of one value column |
| `clustered_shuffle`, `within_firm_shuffle`, `year_stratum_shuffle` | the three nulls: wrong firm, wrong period, and one coarse firm property kept |
| `extremes_vs_middle` | both tails against the middle, for a variable that sorts by size and not by direction |
| `family_chance` | how many cells of a reported grid clear the study's own null by chance |
| `r2_lattice`, `shapley` | every subset's R-squared, and the per-block credit that does not depend on a ladder order |
| `fiscal_periods`, `overlap_years` | date a filed year from `periodEnd`, and measure how much of it the price window already ran through (trap 15) |
| `revision_filings` | one row per revising filing rather than per revised fact (trap 10) |
| `shift_trading_days` | a date moved on the ticker's own calendar, for a transaction date that is not a publication date (trap 11) |
| `benchmark_return` | an ETF or index return over the same window, for a sector-relative read |

### `joins`, fundamentals against prices

| helper | what it is for |
|---|---|
| `split_basis_flags`, `corroborate_flags`, `rebase_shares` | candidate splits from the diluted series, tested against the never-restated one (traps 1, 2, 14) |
| `share_series_sanity` | fiscal years where the two share counts disagree too much: a split basis or the unit defect (trap 13) |
| `firm_basis`, `rebase`, `snap` | the join between those two, turning a run of flags into a split year, a factor, or an unrepairable break |
| `market_cap` | a share count times a close, with the fiscal-alignment check and the split-basis warning on it (trap 4) |
| `decompose` | price return as revenue-per-share growth times multiple change, which survives negative earnings |
| `forward_return`, `market_adjust` | a single forward return with staleness guards, and a one-column cohort adjustment |

### `stooq`, the price file you hold

`index`, `bars`, `closes`, `asof`, `px` read a bundle already on your disk;
`close_at` is `px` with the staleness rule, so a frozen print from a name that
stopped trading is refused rather than returned as a price; `split_scan` lists
the day-over-day moves worth resolving before a long-window return is trusted.

### `client`, the API

`get`, `post`, `get_paged`, `download` and `is_cached` are the call surface;
`manifest` records the whole cache and `pin` records the slice of it a study's
tickers depend on, so a cache filled underneath a run shows up as a changed
input rather than as a moved denominator. `offline()`, and `DISTILL_OFFLINE=1`
for a whole run, make any uncached call raise, which is how a reproduction claim
is tested rather than asserted.

## Charts

Every chart goes through `distill_toolkit.charts`, which carries the house
style: `figure`, `label`, `finish`, `save`, the colour tokens, and the marks
`bars`, `grouped_bars`, `quantile_bars`, `paths`, `lines`, `date_bars` and
`date_ticks`. `bars` and `grouped_bars` take `err=` and draw the interval
whisker themselves, in the ink tone rather than the series colour; a cohort
statistic charted without its interval invites the reader to rank bins a
firm-clustered bootstrap cannot separate. Colours are fixed and up and down are reserved for sign, never for
identity.

Layouts: `figure` is one row of panels, `stack` is a vertical panel stack on one
shared x axis, and `grid` is rows by columns. `lines` draws a plain series with
no interquartile band, which is what a survival curve wants; `date_bars` and
`date_ticks` index on real dates rather than `numpy.arange`, so a mark can share
an axis with a daily price series. The defects that produced these shapes, and
their fixes, are recorded in
[CORRECTIONS.md](../CORRECTIONS.md#15-chart-module-defects-found-while-rendering-the-studies).
Each chart carries a source line naming the data and its vintage.
