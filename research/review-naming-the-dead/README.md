# Adversarial review of `research/naming-the-dead`

Reviewer pass over `research/naming-the-dead/` (`PREREGISTRATION.md`,
`README.md`, `study.py` and the tables under `cache/research/naming-the-dead/`).
The job was to break its headline claims. Nothing in that folder was edited.

Reproduce from the repository root:

```
SEC_TICKERS=cache/sec/company_tickers.json \
DISTILL_OFFLINE=1 ./.venv/bin/python research/review-naming-the-dead/study.py
```

**0 uncached Distill API calls.** The client's request functions are replaced by
a raiser before anything else is imported. Inputs are `cache/panel.csv` (the
`screen/export` rebuild of 2026-09-07, 197,332 rows over 6,955 CIKs, snapshots
2009-06-30 to 2026-06-30), `cache/sec/company_tickers.json` as published
2026-09-11, and the reviewed study's own on-disk tables.

**One check needs a file this repository does not ship.** R3 reads SEC's
per-CIK submissions record for each of the 3,104 ended firms, reduced to one
row per CIK at
`cache/research/review-naming-the-dead/submissions.csv` with the columns
`cik, ticker, listed_until, listing_end_source, name, n_former_names,
sec_tickers, sec_exchanges, error`. The toolkit carries no downloader for it;
[`../../docs/data-sources.md`](../../docs/data-sources.md) has the fetch, the
User-Agent condition and the rate limit. `study.py` reads that file, never
fetches, and prints a skip note when it is absent.

The reviewed study is a census of a 6,955-firm panel, not a sample from it. That
removes most of the review contract: there is no null to rebuild, no label to
shuffle, no fiscal time to check and no price window to move. What is left, and
what this review spends itself on, is the denominator, the key the cohorts are
cut on, and the scope of the claim.

---

## Verdicts

| headline claim | verdict |
|---|---|
| (a) Every number in the README comes out of `study.py` | **HELD.** Exact reproduction, all seven tables, zero cache entries changed outside the study's folder. |
| (b) 88.7% of still-listed filers are nameable from the free file | **TRIMMED, and the finding gets stronger.** The pool is not what its label says: **568 of those 3,851 firms have no row at the panel's final snapshot**, so they are not filing either, they simply carry no exit form. On the 3,283 that are still filing the share is **95.3%**; on the 568 it is **50.4%**. **282 of the 436 misses (64.7%) are firms that stopped filing**, so the "SEC's list misses 11.3% of live filers" reading is wrong; the real figure is 154 of 3,283, **4.7%**. The corrected contrast is 95.3% against 0.0%. (R1) |
| (c) 1 of the 3,104 with a listing end is nameable (0.0%), all four end sources agreeing | **HELD.** Exact, and `ADAP` is the single exception in both runs. |
| (d) 266 of 3,104 ended tickers are in the file and none of the 266 points at the filer that held it | **HELD, and restated.** A caller cannot act on "present or absent"; they can act on three outcomes. Asked by ticker: still filing 93.9% / 0.2% / 5.8%, stopped filing with no form 48.1% / 1.9% / 50.0%, listing ended **0.0% / 8.6% / 91.4%** (the company you asked for / a different company / nothing). (R2) |
| (e) The framing that a delisted company cannot be named | **BROKEN as a general claim, and the study never made it, but a reader would.** `data.sec.gov/submissions/CIK##########.json` is free, served per CIK, and named **3,104 of 3,104** ended firms with no errors: 100.0% on every listing-end source. **1,741 (56.1%) also carry former names** for the company asked about, and the file reports the company as gone rather than silently: only 4 still list a ticker and 3 still name an exchange. So "a delisted company cannot be named from free data" is false. What survives, and is sharper, is the **direction**: that file answers "what is this CIK called" and requires the CIK to ask. Going the other way, from a symbol to the CIK, SEC publishes only `company_tickers.json`, which the study measures at 0 of 3,104. (R3) |
| (f) The API lookup names 3,104 of 3,104 and 386 (12.4%) carry another company's CIK, concentrated in the `sec-edgar` resolver at 245 of 245 | **HELD on the study's own responses, NOT independently re-measured.** Every figure reproduces from the cached payloads. This review made no Distill call, so the 12.4% is verified against responses fetched on one day with one key and nothing here re-fetches them. |
| (g) The Healthcare pool: 1,157 firms, 649 still listed and 508 ended, 90.4% against 0.2% | **TRIMMED as counts, HELD as rates.** The pool is keyed on the ticker (`groupby("ticker").tail(1)`), which collapses a reused Healthcare symbol onto its later holder and drops the earlier firm. Keyed on the CIK the pool is **1,167 firms, 649 still listed and 518 ended**. Both shares are unchanged to the decimal. (R4) |
| (h) Language | **HELD.** No sentence in the reviewed README rates, values, forecasts or recommends a security. No em dashes. The disclosure names the publisher's own defect rather than footnoting it. |

**The check that did the most damage** was R3, and it did not move a number. It
bounds the claim: the study measures one file, and a reader who generalises it
to "free data cannot name the dead" would be wrong in a way that changes what
they should build. Second was R1, which found that the denominator behind the
headline percentage was a mixture of two populations.

---

## R1. The denominator

The study splits the panel on `listed_until`: set means the listing ended,
absent means still listed. Absent also covers a firm that stopped appearing with
no Form 25 and no Form 15 on file, and the panel's own final snapshot separates
the two.

| cohort | n | nameable | share |
|---|---|---|---|
| still filing at 2026-06-30 | 3,283 | 3,129 | **95.3%** |
| stopped filing, no exit form on the record | 568 | 286 | **50.4%** |
| listing ended, dated | 3,104 | 1 | **0.0%** |

The middle cohort is not a curiosity, it is the visible residue of `listed_until`
being incomplete, and `findings/ghost-cohort.md` already counts the same 568
firms as the ones whose panel exit is "an inference from a CIK's last row". Its
nameable share falls the further back its last row sits, which is what a
population of undated departures mixed with stragglers looks like:

| year of the firm's last panel row | 2013 | 2015 | 2018 | 2021 | 2023 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| n | 48 | 29 | 30 | 36 | 55 | 88 | 3,301 |
| nameable | 12.5% | 17.2% | 26.7% | 58.3% | 72.7% | 84.1% | 95.2% |

A firm whose last set of accounts reached the SEC in 2013 and which the free
list does not carry is not a live registrant the SEC forgot. The study's own
framing of the residual, "a CIK in the panel with no current ticker row, which
includes filers between symbols", is true of the 154 and not of the 282.

## R2. The key a caller actually holds

The study's table 3 splits a ticker lookup two ways: the symbol is in the file
or it is not. From outside, a caller cannot tell "in the file" from "in the file
and pointing at someone else", and those two have opposite consequences. Split
three ways, on the R1 cohorts:

| cohort | n | the company you asked for | a different company | nothing |
|---|---|---|---|---|
| still filing | 3,283 | 3,084 (93.9%) | 7 (0.2%) | 192 (5.8%) |
| stopped filing, no exit form | 568 | 273 (48.1%) | 11 (1.9%) | 284 (50.0%) |
| listing ended, dated | 3,104 | 0 (0.0%) | 266 (8.6%) | 2,838 (91.4%) |

![What a ticker lookup against the free SEC list returns, by listing status](charts/lookup-outcome.png)

*Leaving the panel is leaving the corpus, not failing.*

The 91.4% that return nothing are a coverage problem and announce themselves.
The 8.6% are a correctness problem and do not. That distinction is the study's
strongest practical content and its table 3 does not make it.

## R3. The scope of the claim

The study measures nameability against `company_tickers.json` and reports 1 of
3,104. That file is not the only free SEC route to a name, and if another free
route names the dead then the study is about one file rather than about free
data. A reader deciding what to build needs that distinction, and the reviewed
README does not draw it.

Asked once for each of the 3,104 ended firms, at eight a second:

| how the listing ended | n | named | carries former names | still lists a ticker |
|---|---|---|---|---|
| Form 25 | 2,469 | 2,469 (100.0%) | | |
| Form 15 | 515 | 515 (100.0%) | | |
| crawl | 89 | 89 (100.0%) | | |
| migration | 31 | 31 (100.0%) | | |
| **all** | **3,104** | **3,104 (100.0%)** | **1,741 (56.1%)** | **4 (0.1%)** |

Zero errors, after retrying two read timeouts that the first pass hit. The former names are
the asked-for company's own, unlike the `formerNamesJson` the study examines in
its post-hoc note, which belongs to whichever company the profile route
returned. The near-empty ticker and exchange columns are SEC clearing those
fields when a registration ends, so the per-CIK file states that the company is
gone where the bulk file merely omits it.

**What survives, and is sharper than the claim it replaces.** The per-CIK file
answers "what is this CIK called" and needs the CIK to ask. The join this study
is about runs the other way: a caller holds a name or a symbol and wants the
CIK. In that direction `company_tickers.json` is the only free map SEC
publishes, and the study's own table 2 puts it at 0 of 3,104. The correct
statement is not "free data cannot name the dead"; it is **"no free source maps
a dead company's symbol back to it"**, which the study measured and did not say.

## R4. The sector cut, re-keyed

`t7_healthcare` builds its pool with `hc.groupby("ticker").tail(1)`. A Healthcare
symbol used by two different filers yields one row, the later holder's, and the
earlier firm leaves the pool. That firm is by construction the one whose listing
ended, so the keying drops from the cohort the study is about.

| keyed on | firms | still listed | ended | still-listed nameable | ended nameable |
|---|---|---|---|---|---|
| ticker (as published) | 1,157 | 649 | 508 | 90.4% | 0.2% |
| CIK | 1,167 | 649 | 518 | 90.4% | 0.2% |

Ten firms, 2.0% of the ended half. No rate moves. The sentence that moves is
"gets 587 firms out of 1,157", which understates what a name join loses.

Rebuilt on the CIK-keyed pool, the tercile table the study publishes stands:

| cohort | small | mid | large | all |
|---|---|---|---|---|
| still listed | 86.6% (n = 216) | 90.7% (n = 216) | 94.0% (n = 217) | 90.4% (n = 649) |
| with a listing end | 0.0% (n = 173) | 0.6% (n = 172) | 0.0% (n = 173) | 0.2% (n = 518) |

The size gradient in the still-listed half and the flat zero in the ended half
are both unchanged.

## What this review did not check

- **The API half was not re-fetched.** Verdict (f) rests on the study's cached
  responses. A re-run on another day with another key could differ, and nothing
  here would catch it.
- **Nameability is presence, not correctness.** Neither the study nor this
  review compares the `title` in the free file against the name in the filings.
- **A name is not a join.** Both measure whether a name exists, never whether a
  name-to-name match against an outside registry succeeds. Every rate in either
  document is a ceiling on such a join, not an estimate of one.

---

General information from public SEC filings, not financial product advice.
Companies are named above only as facts they exhibit in the data. See the
[disclosure](../../README.md#disclosure).
