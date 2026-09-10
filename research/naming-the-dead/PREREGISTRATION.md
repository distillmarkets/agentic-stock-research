# Pre-registration: `naming-the-dead`

Written before `study.py` was run. Every table below is specified here first;
the study fills the cells and nothing else.

Vintage: `cache/panel.csv`, the `screen/export` panel rebuilt 2026-09-07, first
snapshot 2009-06-30, final snapshot 2026-06-30. Identity: the SEC's
`company_tickers.json` as the user holds it, read through
`distill_toolkit.sec_tickers` from `SEC_TICKERS` (docs/data-sources.md carries
the fetch). API identity: the `/api/v1/sec/profile/{ticker}` responses already
in `cache/`, read off disk as files. API: **zero uncached calls**.
`distill_toolkit.client.get`, `post`, `request` and `download` are replaced by
a raiser before any other import.

**The keyless half runs keyless.** Tables 1, 2, 3 and 7 use the panel and the
free SEC file only, and the script computes them with no key present and no
cached profile response read. Tables 4, 5 and 6 read the cached profile
responses and are skipped, with a printed note, when they are not on disk.

## Question

For a filer in the point-in-time panel, can its company name be recovered from
the free SEC identity file, and does that answer depend on whether its listing
has ended; and where the free file fails, does the publisher's own ticker-keyed
profile endpoint recover the name of the company that was asked about.

Unit: the firm (CIK). **Census, not a sample.** Every rate below is computed
over the whole panel, so it is a population rate with no sampling interval and
no placebo: there is no draw to shuffle. Descriptive only; no price appears
anywhere in this study.

## Definitions

- **Still listed**: a CIK whose last panel row carries no `listed_until`.
- **With a listing end**: a CIK whose last panel row carries `listed_until`;
  **source** is `listing_end_source` (`form25`, `form15`, `crawl`,
  `migration`).
- **Nameable from the free file**: the CIK is a key in `company_tickers.json`.
  The file carries a `title` for every CIK it holds, so presence is nameability.
- **The panel's ticker for a firm**: the ticker on its last panel row.
- **Named by the API lookup**: `/sec/profile/{ticker}` returned a non-empty
  `name` for that ticker.
- **CIK agrees**: the profile response's `cikNumber` equals the CIK asked
  about. When it does not, the name returned is another company's.
- **Resolver source**: the profile response's own `source` field.
- **Where a mismatch lands**: for the returned CIK, its span of panel rows
  under the same ticker. **Later holder** when that span starts at or after the
  asked firm's last row; **earlier or overlapping holder** when it starts
  before; **absent** when the returned CIK has no panel row under that ticker.
  This is a geometry, not a corporate fact, and the study says so.

## Tables to be filled

### T1. Universe and vintage
Panel: CIKs, rows, first and final snapshot, still listed, with a listing end
by source. Free file: ticker rows, distinct CIKs, the file's own date.

### T2. Nameable from the free file, by listing status
Rows: still listed; with a listing end, and split by source. Columns: n,
nameable, share.
Prediction: near 90% for the still-listed half; near zero for the other, with
no material difference between sources, because the file has no history in it
at all.

### T3. The same file reached by its other key
For each listing status: how many of the panel's tickers appear in the free
file, and of those how many carry the CIK that held the ticker in the panel.
Prediction: a small but non-zero share of ended firms' tickers are present, and
almost none of them point at the firm that held it.

### T4. What the API lookup returns for the ended firms
Of the firms with a listing end: named, not named, error. The resolver `source`
field's distribution over the same set.

### T5. The identity defect in the API lookup
CIK agrees against CIK differs, over the ended firms, by `listing_end_source`
and by resolver `source`. Reported as counts and as the share differing.
Prediction from having read one response by hand: the share differing is not
zero and is highest for `migration`.

### T6. Where the mismatches land
The mismatches by the geometry in Definitions, crossed with
`listing_end_source`; the days from the asked firm's listing end to the later
holder's first row under the ticker, as quantiles; and how many mismatches
return a company that is still listed in the panel. A named, hand-classified
example of each of the three situations the geometry cannot separate: a
successor after a reorganisation, an unrelated company that took the symbol
later, and a predecessor. The hand classification is marked as such and is not
computed.

### T7. One sector, on the honest denominator
The last Healthcare row per ticker with revenue at or above $10m: nameable
share from the free file by listing status and by revenue tercile within
status. This is the census cut the way a sector study would meet it.
Prediction: the still-listed share rises with revenue; the ended share is flat
at zero across all three terciles.

## Charts

- `charts/nameable.png`: T2 as shares, still listed against each listing-end
  source.
- `charts/mismatch.png`: T5's share differing by `listing_end_source`, and the
  386 by where they land.

## What would break it

The free file is a snapshot with no date on any row, so T2 and T3 move with
whenever the user fetched it; the study prints the file's own date beside every
rate. The panel is one export and the counts move with its vintage. T4 to T6
read cached responses fetched 2026-09-11 and describe the endpoint's behaviour
on that date; a fix to the endpoint would change them, which is the point of
writing them down.
