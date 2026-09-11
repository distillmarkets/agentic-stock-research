# Findings

Each study states its data vintage, names the script that reproduces every
number in it, and reports the match rate between the filings and the price
file it was joined to. Nulls are written up the same way as the rest. A number
in [CORRECTIONS.md](../CORRECTIONS.md) supersedes the same number anywhere else.

| study | what it found |
|---|---|
| [survival-clock.md](survival-clock.md) | A health label times the fall: a tenth of the weakest bucket is 50 points behind by month 7, the strongest by month 17. Recovery is flat everywhere. |
| [ghost-cohort.md](ghost-cohort.md) | Close to a third of SEC firm-years since 2010 have no price series, the weakest third. Exit base rates on priced data are understated five times. |
| [pre-exit-signature.md](pre-exit-signature.md) | A firm with Altman Z below 1.8 stops filing within two years 10% to 27% of the time depending on how the exit is dated. The signature is a level two years out, not a slope. |
| [vintage-gap.md](vintage-gap.md) | Restatement changes 5% of the rows a screen returns. Firms the history endpoint no longer serves change it by a third. |
| [eightk-items.md](eightk-items.md) | Earnings 8-Ks print on a day twice a quiet day. The rest run 1.0 to 1.5 times, seven of eighteen item classes are indistinguishable from a quiet day, and no class has a direction or a drift afterwards. |
| [what-moves.md](what-moves.md) | Of the variance in a twelve-month move, the fiscal year the price ran through carries 11 points of 17, sector 2, and everything knowable at the start under 1. |
| [post-filing-drift.md](post-filing-drift.md) | After a weak revenue print enters the record, the decile whose revenue growth accelerated most runs about 2 points below the decile that decelerated most over the next six weeks. That is the whole of the drift. |
| [share-issuance.md](share-issuance.md) | The heaviest-issuing fifth is in the two-year tail 33% of the time against 13%. It is a firm type visible years earlier, not a timing signal; buybacks time nothing. |
| [market-cap.md](market-cap.md) | A point-in-time market cap from on-file shares and the close. Value sorts on this data are not a base rate: the sign flips by entry year. |
| [naming-the-dead.md](naming-the-dead.md) | The free SEC company list names 95.3% of the filers still filing and none of the 3,104 whose listing has ended. Asked by ticker, 266 of those come back as a different company, and the publisher's own lookup returns the wrong company 12.4% of the time. |
| [nulls.md](nulls.md) | Six results that did not survive their control: 13F crowding, capex clocks, the correcting filing, record change leading price, and more. |

Charts for every study are under [charts/](charts/). Each document names the
script under `research/` that reproduces it. Two of them, the pre-exit signature and the identity census, are kept in the checkout as the
worked examples with their reviews ([../research/](../research/)); every other
script named here is held by the publisher and available on request (open an issue at
https://github.com/distillmarkets/agentic-stock-research/issues).

General information from public SEC filings, not financial product advice. See
the [disclosure](../README.md#disclosure).
