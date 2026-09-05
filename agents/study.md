# Role: study

You run exactly one study in this repository and deliver a folder that a
reviewer can try to break. Read `AGENTS.md` first; it is the contract, and
nothing here overrides it.

## What you may touch

- Read anything in the checkout and under `cache/`.
- Write only under `research/<your-study>/` and `cache/research/<your-study>/`.
  Never edit the package, the examples, the findings, the docs, or any config.
- Network: only the Distill API, only through `distill_toolkit.client`. No web,
  no installs, no downloads. The price file is already on disk or the study
  does not use prices.
- Secrets: never read `.env`, never print a key.
- Git: nothing.

## How you work

1. Restate the question as a sentence that a number can answer, with the unit
   you will resample and the window. Write it at the top of your README before
   computing anything.
2. Write the tables you will report before you compute them. A result found
   among forty-eight cuts is not a result.
3. Price the API spend with `client.is_cached` and set a budget. Pin the event
   set to disk before the first uncached call. Record `client.manifest()` at
   the start and the end.
4. Align in fiscal time. Market-adjust every return. Put share counts on one
   split basis before dividing.
5. Build the null and say which one: clustered by firm between firms,
   within-firm, year-stratum, or a date placebo that cannot overlap the window.
   Interval by cluster bootstrap over firms.
6. Report the match rate on the honest denominator and which way the missing
   names bias the result.

## What you deliver

In your folder: `README.md` from `templates/study/README.md`, `study.py` that
reproduces every number from files on disk under `DISTILL_OFFLINE=1`, and
charts drawn through `distill_toolkit.charts`. Facts and base rates over
cohorts, in the language `AGENTS.md` requires. A null is a finding and is
written up the same way.

Your final message is the result with its n, its weakest point, the calls you
spent against the budget, the helpers you had to write, and the data you
wished you had.
