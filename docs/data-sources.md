# Data sources and what you owe each one

The toolkit ships no data and downloads nothing from third parties. You bring
the data; this page says what that means for each source.

## Distill Markets

The publisher's own API. You need your own key. A free key covers the endpoint
sweep and the current-snapshot examples; the point-in-time history grid is a
paid tier.

Use of the API and its responses is governed by the
[Distill Markets terms of service](https://distillmarkets.com/legal/terms),
not by this project's licence. The parts that matter for a repository:

- You may cache responses for the duration of your subscription and use them
  in your own research, models and systems.
- You may publish your own research derived from the data, and small
  illustrative samples of responses in documentation, repositories and
  articles.
- You may not redistribute, mirror, or republish substantial portions of the
  data, or offer it as a dataset. A committed cache directory is exactly that.

That is why `cache/` is gitignored and `scripts/check_hygiene.py` fails the
build if data files are tracked.

The one exception is published by the publisher itself: a 200-firm cut of the
point-in-time export attached to a release of this repository (README,
Install). It is served under the same terms as an API response, for your own
research; it is not a dataset to redistribute. `scripts/cut_sample.py` is the
cut, seeded, so a Pro key reproduces it exactly.

## Stooq

Stooq publishes free end-of-day price files, including a bulk daily bundle
for US listings. The toolkit reads that bundle from your
disk. It never contacts stooq.com.

The publisher has not verified Stooq's current terms and makes no statement
about what they permit, including whether commercial use or redistribution is
allowed. Stooq also discloses that its quotes come from upstream vendors whose
own licences may apply. Before using the files:

- read Stooq's terms yourself, and the upstream vendors' where relevant
- keep the files on your own disk and out of any repository
- do not use the toolkit to automate retrieval from Stooq. It has no
  downloader, and adding one is out of scope for this project

Two properties of the files shape every result computed from them. Closes are
split-adjusted retroactively to the download date, so returns are price
returns and omit dividends. The file set is current listings only, so
delisted issuers are absent and any historical cohort is biased toward
survivors. See `docs/traps.md`.

## Adding a source

A new source gets an entry here and in NOTICE before any example uses it. The
entry states what the source's terms require of the user, what the toolkit
does and does not do with the source, and any endorsement disclaimer the
source mandates. If the source's terms cannot be read, say so, as above.
