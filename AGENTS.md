# Brief for an agent working in this repository

You are joining SEC fundamentals served point-in-time by the Distill Markets
API to prices the user holds on disk. Read this whole file before the first
call. The long form is [docs/agent-guide.md](docs/agent-guide.md); the mistakes
are [docs/traps.md](docs/traps.md); the numbers that did not survive review are
[CORRECTIONS.md](CORRECTIONS.md).

## The two sources

- **Distill** serves what companies filed, as it was knowable on a date, for
  every filer including the ones that later delisted, with every revision.
  The bulk lane is one call: `GET /api/v1/sec/screen/export` returns the whole
  panel, one row per (CIK, quarter end) since 2009. A departed firm's rows
  carry `listed_until` and `listing_end_source` where a Form 25 or Form 15 is
  on file, which is 3,104 of the 3,672 firms that leave the panel; the rest
  stopped filing without one, and their exit stays an inference from the last
  row. Pass the column through to `analysis.forward_paths` and no return is
  read past the listing end, which matters because a ticker is reused. If you
  also have the
  Distill MCP server connected, it serves the same endpoints as tools; use it
  to look, and use `distill_toolkit.client` to fetch what a study reproduces,
  so every input lands in the cache the reproduction reads from.
- **The price file** serves prices for names that still trade. Close to a third
  of filer-years have no price series, and it is the weakest third (trap 3).

The fundamentals are complete and the prices are not. Every result joined to
prices is a survivor's result until you say what fraction of the universe
carries a price at all.

## What the key can reach

Check the tier before planning the calls; a 403 carries the tier that grants
the route, and a study planned above its key wastes its budget finding out.

| key | per day | reaches |
|---|---|---|
| Free | 150 | today's snapshot export without the four scored columns; filings, insider, revisions, ownership per ticker; ten single-name as-of lookups a day |
| Analyst | 2,000 | plus the scored columns, fundamentals history and unlimited single-name as-of |
| Pro | 15,000 | plus the point-in-time export, the bulk lane the longitudinal studies start from |

On Free, design cross-sections on today's snapshot and per-ticker studies over
a few dozen names. Anything that needs the record as it stood on an earlier
date needs Pro or the 200-firm sample of the export (README, Install), and the
study README says which rather than substituting latest-filing-wins history. A
result on the sample is a base-rate check with 200 firms behind it, and says
so.

## Before the first API call

1. Check the cache: `client.is_cached(path, **params)`. The panel is probably
   already on disk under `cache/`.
2. Set a budget of uncached calls and write it in the study README. Each
   uncached call takes about a second; the limit is sixty a minute per key.
   Never loop over a universe.
3. Pin the event set to disk before the first call, so a cache filled by other
   work cannot move the denominator under you.
4. Record `client.manifest()` at the start and the end.

`DISTILL_OFFLINE=1` makes the client raise on any call not already cached. Run
reproductions under it.

## Reading the data

- Align in fiscal time, never calendar time. A December panel row's annual
  block is a median 275 days old (trap 16). The "next" fiscal year is usually
  the one the price already ran through (trap 15).
- Put share counts on one split basis before dividing (`joins.split_basis_flags`).
  `sharesOutstanding` is never restated, and the diluted count arrives in the
  wrong unit on a small share of filer-years, measured at about 1% on one priced
  pool and not a universe rate (traps 1, 2, 13).
- A Form 4 row carries the transaction date, not the filing date (trap 11).
- A 404 means uncovered or nonexistent and does not say which (trap 6).
- A name is not a free key. The SEC's `company_tickers.json` names 88.7% of
  the panel's still-listed filers and 1 of the 3,104 whose listing has ended,
  and a ticker join to it returns another company for every ended filer whose
  symbol is still in it. Key identity on the CIK, and where you must ask by
  ticker, check the CIK that comes back (trap 19).

## What a study has to contain

Write it in a folder under `research/<name>/`, from
[templates/study/](templates/study/):

1. **n in the unit you resampled**, firm-years and firms both, with the window.
2. **A placebo clustered by firm.** `analysis.clustered_shuffle` between firms,
   `within=` for the within-firm null, `analysis.cluster_boot_diff` for the
   interval. A null is a construction: say which one you built.
3. **The match rate on the honest denominator**, and which way the missing
   names bias the result.
4. **One script that reproduces every number** from files on disk, run from
   the repository root, and the vintage of every source.
5. **Facts and base rates over cohorts.** Never "undervalued", "buy",
   "target", "should", "opportunity", or any sentence about where a price goes
   next. A named company appears only as a fact it exhibits in the data.

Negative results are results, written up the same way. State what data you
wished you had.

## What you must not do

- Commit anything under `cache/`, any `.csv`, `.parquet`, `.jsonl`, a notebook
  with outputs, or a fixture built from real records.
- Add a downloader for any third-party source.
- Print or read `.env`.
- Install a package without saying so and why.

Run `pytest` and `python scripts/check_hygiene.py` before you say you are done.
