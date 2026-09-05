# Contributing

## The one rule that matters: no third-party data in the repository

This repository contains code and documentation. It never contains data
obtained from the Distill Markets API, from Stooq, or from any other source.
That is what keeps the project distributable. A committed API response, a
cached panel, a price file, or a notebook with saved outputs turns the repo into
a redistributor of licensed data, whatever the intent.

Concretely, a pull request is rejected if it adds:

- anything under `cache/` or `data/`, or any `.csv`, `.parquet`, `.jsonl`,
  `.feather`, `.pkl` or `.zip` file
- a notebook with outputs. Strip them before committing:
  `jupyter nbconvert --clear-output --inplace notebooks/*.ipynb`
- a test fixture built from real records. Fixtures are synthetic and say so in
  a comment. Numbers in them should be obviously made up
- a documentation table that reproduces more than a small illustrative sample
  of any source. A handful of rows to show a shape is fine. A dataset is not
- a downloader for any third-party source. The toolkit reads files you already
  hold; obtaining them is the user's act, not the toolkit's

`scripts/check_hygiene.py` enforces the mechanical parts of this, including a
ban on any URL to a third-party data host in package or example code, and runs in
CI. Run it locally before pushing:

```
python scripts/check_hygiene.py
```

## Findings and studies

Any study added to `findings/` states facts and methods. It does not
recommend, rate, or value a named security. Base rates over cohorts are facts.
"Undervalued", "buy", "target" and their cousins are opinions, and they do not
belong here. Every study carries the data vintage it was computed on and the
script that reproduces it.

Name a ticker only when the sentence is about a fact that ticker exhibits in
the data, and never in a way that reads as a call on where its price goes.

## Code

- Python 3.11 or later. Type hints on public functions. Docstrings state what a
  function assumes about its inputs, especially split basis and date handling.
- Tests under `tests/` with synthetic inputs. `pytest` must pass.
- Examples under `examples/` are runnable scripts that use the package, not
  copies of package code.

## Sign-off

Commits carry a Developer Certificate of Origin sign-off
(`git commit -s`), certifying that you have the right to submit the work under
the project licence. See https://developercertificate.org.
