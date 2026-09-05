# Adding a data source

The toolkit joins the Distill record to files you hold. A new source is a
file on your disk with a date on every row and a key the join can reach, and
adding one is a reader module, two paragraphs of terms, one synthetic test and
one study that states its match rate. `distill_toolkit/stooq.py` is the
template; this page is the checklist.

## The rule

The toolkit reads files. It never downloads them. Obtaining the file and
complying with its terms is the user's act, so a reader module has no URL in
it, no fetch, and no default that reaches the network. `scripts/check_hygiene.py`
fails the build on any URL in Python that is not the Distill API, and on any
data file in the tree.

## The reader module

`distill_toolkit/<source>.py`, shaped like the Stooq reader:

- **Root resolution.** An explicit `root` argument, else an environment
  variable named for the source (`STOOQ_DIR` is the precedent), else a folder
  under the cache directory. Document the expected layout in the module
  docstring, as the file ships.
- **An index.** One walk of the root that maps the source's key to a path, then
  cached. Nothing else touches the file system.
- **Absent means absent.** A symbol with no file returns `None`, never an empty
  series, so a study can count what the source does not cover.
- **A dated lookup.** `asof(series, date)` returns the last observation on or
  before the date, because period ends land on weekends and holidays.
- **The key.** Say what the file is keyed on (ticker, CUSIP, company name) and
  what that means for the join. A ticker is reused across time and across
  security types; a name needs matching; a CUSIP changes on a corporate
  action. The Distill panel carries ticker and CIK.
- **What the numbers are.** Split-adjusted or not, dividend-adjusted or not,
  current listings only or complete, revised in place or versioned. Each of
  these decides what a study computed from the file can claim, and each goes
  in the docstring.

## The terms

Before any example uses the source, add an entry to `NOTICE` and to
[data-sources.md](data-sources.md): what the source's terms require of the
user, what the toolkit does and does not do with it, and any disclaimer the
source mandates. If the terms cannot be read, say so. A public-domain source
(SEC and other US federal data) still gets the entry, stating that it is
public domain.

## The test

Synthetic fixtures only, under `tests/`, with invented numbers that are
obviously invented and a comment saying so. Cover the index, an absent symbol,
and the dated lookup at a weekend.

## The study

The first study on a new source answers one question about coverage before
any result: what fraction of the Distill universe does the file reach, on the
honest denominator, and which way are the missing names biased? That number
goes in the study README and, if the source stays, in `docs/traps.md`. The
Stooq answer was a third of December firm-years, the weakest third, and it
shaped every study that followed.

## Checklist

1. `distill_toolkit/<source>.py`: root, index, `None` for absent, `asof`,
   docstring stating key and adjustments. No URL.
2. `NOTICE` and `docs/data-sources.md` entries.
3. `tests/test_<source>.py`, synthetic.
4. A study under `research/` from `templates/study/` reporting the match rate.
5. `.env.example` gains the root variable, commented out.
6. `python scripts/check_hygiene.py` and `pytest` pass.

Sources that fit this shape and are public domain: SEC fails-to-deliver files
(ticker and CUSIP, twice monthly, a prior close on every row), the EDGAR
quarterly index (every filing with its acceptance time, Form 25 and Form 15
for delisting and deregistration dates), and federal event streams keyed by
company name.
