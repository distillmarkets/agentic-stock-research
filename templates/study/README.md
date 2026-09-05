# <Question, as a sentence that can be answered with a number>

**Uncached API calls:** <budget> budgeted, <spent> spent. Manifest at start and
end in `manifest.json`.

## Question

One paragraph. What is being measured, on what unit, over what window.
Descriptive association only; nothing here is about where a price goes next.

## Data and vintage

- Distill panel: `cache/panel.csv`, vintage <as_of of the export>.
- Price file: Stooq daily US bundle through <last date>.
- Event set pinned to `events.parquet` before the first call.

## Pool

n = <firm-years> over <firms>, <window>. Match rate against the price file:
<matched> of <universe> firm-years (<pct>%). The missing names are <smaller,
weaker, ...>, which biases every rate here <up, down>.

## Method

The sort, the outcome, the anchor in fiscal time, the market adjustment.

## Null

Which construction: between-firm clustered shuffle, within-firm shuffle,
year-stratum shuffle, date placebo. Interval by cluster bootstrap over firms.

## Results

| cut | n (rows / firms) | statistic | interval | placebo |
|---|---|---|---|---|

## What did not hold

## What data was wished for

## Disclosure

Distill Markets Pty Ltd, the publisher of this repository, operates the paid
data service this study uses. Authors and the publisher may hold positions in
securities named here. Everything above is general information derived from
public SEC filings and from a price file the author holds. It is not financial
product advice, does not consider your objectives, financial situation or
needs, and past patterns do not guarantee future results. See
[NOTICE](../../NOTICE).
