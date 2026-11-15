# Data shapes

The pipeline writes these files into `web/public/data/`. The web app reads only these. Types are in `web/lib/types.ts`.

| File | What's in it |
| --- | --- |
| `meta.json` | `as_of` (IST), `sample` flag, lookback days, classification stats, model cost totals by step, model names |
| `config.json` | holdings, research set, default thresholds, watched categories, pillars, category list |
| `prices.json` | `stocks[SYMBOL].series[]`: `date, close, change_pct, volume, avg_vol_20, vol_multiple` for the last 30 sessions |
| `digest.json` | `items[]`: one per filing (below) |
| `holdings.json` | per holding: last session, 20-day closes, metrics for pillars (`revenue_yoy, pat_yoy, ebitda_margin, pat_margin, cfo_to_pat`), credibility |
| `companies/SYMBOL.json` | full research for one company (below) |
| `nse_symbols.json` | `[{s, n}]` symbol and name, for search |

## Filing (`digest.json` item)

```
id, symbol, company, time, source (nse|bse), url
exchange_category, subject            as filed
category, material, rule, classified_by   from config/rules.yaml or the model
summary                               one line, material filings only
results_card                          results only: metrics[], margins[], settles[], check
management                            management changes only: people[] with bio and orphaned_promises[]
promise_links                         {settles, orphaned, ledger_updated}
```

## Promise thread (`companies/SYMBOL.json` → `ledger.threads[]`)

```
id, metric, metric_key, unit
target_text, target_low, target_high, deadline (e.g. "Q2 FY27", "FY28")
first_said, times_said, speakers[]
revised, revision_direction, quietly_dropped
status            kept | missed | pending | unverifiable   (settled by code where numbers allow)
display_status    kept | missed | revised | dropped | pending | unverifiable
actual_text, progress, reason, settled_by (code | model)
mentions[]        quarter_said, speaker_name, speaker_role, verbatim_quote, page, transcript_url
```

## Company research (`companies/SYMBOL.json`)

```
ledger              threads[], credibility {kept, missed, settled, score}, counts, summary, stats
guidance[]          open promises with progress so far
financial_snapshot  tiles[]
trajectory          years[], quarters[], headline[]
balance_sheet       years[], note
cash_quality        years[] (cfo, pat, ratio), five_year_ratio, verdict
business            what_they_do, segments[], revenue_mix (page-cited)
bull_bear           bull[], bear[], pillars[] (red-team)
sources             screener, transcripts[], annual_reports[]
```
