# Decisions

## 1. Product principle

FINN interrupts me only when something should change what I believe about a holding. A filing's importance isn't fixed: a capex announcement matters if my thesis is about capital efficiency and is noise if it's about volume growth. So FINN judges every event against two ledgers, my thesis pillars and management's own promises, and collapses everything that touches neither. It shows me how much it buried so I can trust the filter. After two minutes I should know which of my beliefs got stronger, weaker or broke today.

## 2. Portfolio (18 stocks)

| Symbol | Sector | Why it's in |
| --- | --- | --- |
| RELIANCE | Conglomerate | Files a lot of routine paperwork; tests the collapse |
| HDFCBANK | Bank | Lender: proves FINN doesn't show a fake EBITDA |
| BAJFINANCE | NBFC | Second lender; gives explicit growth and credit-cost guidance |
| TCS | IT services | Stable margins; a clean metric-pillar test |
| ITC | FMCG | No promoter, so pledging pillars don't apply |
| LT | Capital goods | Guides on order inflow every quarter |
| SUNPHARMA | Pharma | Regulatory and litigation filings |
| ASIANPAINT | Consumer | Margin story under new competition |
| APOLLOHOSP | Healthcare | Capex-heavy bed expansion |
| TRENT | Retail | High-growth expectations, big price moves |
| POLYCAB | Cables and wires | Explicit multi-year revenue and margin targets |
| PERSISTENT | IT services | Revenue run-rate targets |
| DIXON | Electronics manufacturing | Volatile; thin margins; volume alerts |
| DEEPAKNTR | Chemicals | Capex plans and cyclical margins |
| CDSL | Capital markets | Moves with market activity |
| KAYNES | Electronics manufacturing | Revenue guidance plus working-capital risk |
| SUZLON | Wind energy | Large volume swings, so alerts actually fire |
| HAPPSTMNDS | IT services | Small cap with stated revenue goals |

## 3. Research set

POLYCAB, KAYNES and DEEPAKNTR from the portfolio, plus PGEL (PG Electroplast) from outside it. All four talk in numbers on their calls. PG Electroplast gives an explicit annual revenue target, which is a good test of a "revised" promise.

## 4. Alert thresholds

| Setting | Value | Why |
| --- | --- | --- |
| Volume spike | 2.0× the 20-session average | The brief's own example; rare enough to mean something |
| Price move (default) | 4% | Large caps rarely move 4% in a day without a reason |
| Price move (volatile names) | 7% for DIXON, KAYNES, SUZLON, CDSL, HAPPSTMNDS, TRENT | At 4% these would alert every week, and alerts would stop meaning anything |

## 5. Watched categories

Watched: results, management_change, M&A, fund_raise, pledging, insider_trading, credit_rating, litigation, capex.

Not watched: dividend, bonus_split, agm_egm, postal_ballot, investor_meetings, earnings-call notices, unclassified. A press release counts as material only when it states an order or contract value.

## 6. Pillars

Thresholds are beliefs, not facts. They get adjusted once the real numbers are in.

| Symbol | Pillar | Rule |
| --- | --- | --- |
| POLYCAB | Revenue keeps growing fast | revenue_yoy >= 15 |
| POLYCAB | Margins hold | ebitda_margin >= 12 |
| POLYCAB | Promoter doesn't pledge | any pledging filing |
| DIXON | Hyper-growth continues | revenue_yoy >= 30 |
| DIXON | Profits turn into cash | cfo_to_pat >= 0.7 |
| KAYNES | Hyper-growth continues | revenue_yoy >= 30 |
| KAYNES | Working capital doesn't eat the profit | cfo_to_pat >= 0.5 |
| HDFCBANK | Earnings keep compounding | pat_yoy >= 10 |
| HDFCBANK | Leadership stays stable | any management_change filing |
| TCS | Margin moat holds | ebitda_margin >= 25 |
| TCS | Revenue doesn't shrink | revenue_yoy >= 0 |
| DEEPAKNTR | Margins recover | ebitda_margin >= 12 |
| DEEPAKNTR | Promoter doesn't pledge | any pledging filing |

## 7. Models

| Role | Model | Why |
| --- | --- | --- |
| Cheap: leftover classification, one-liners, promise extraction | Flash-tier Gemini (free) | Long context fits a whole transcript, has JSON mode, and the free quota covers the work |
| Strong: verdicts code can't settle, bull vs bear | Pro-tier Gemini | Only sees compact tables, about one call per company |
| Fallback | Groq-hosted open model | Takes over when Gemini rate-limits |

## 8. Results numbers

Screener's quarterly table first: structured, free and consistent across companies. When screener hasn't caught up with a fresh filing, the cheap model reads the filing PDF. When both exist, PAT is cross-checked and a gap above 2% is flagged.

## 9. Research views

All eight from the brief. Promise Scoreboard (narrative vs numbers) comes first because it's the analysis, not a summary. Snapshot, trajectory, balance sheet and cash quality are computed in code with no model. Business snapshot and bull vs bear use a model with page-cited sources.

## 10. Design

Dense like a terminal, calm like a printed page. One amber accent that means "this needs you"; green and red only for the direction of a number. Light and dark mode.

## 11. What gets cut first if time runs out

1. Red-team of pillars
2. Orphaned promises and incoming bio
3. Unexplained moves
4. Custom date range
