# Release Point

**How fast does a market price a pitch?** Every trade on every MLB game market Kalshi listed in 2025 and 2026, lined up
against the pitch that moved it, to the millisecond.
Site: https://austinsanalytics.github.io/release-point/

A stock market is an awkward place to study how prices absorb news, because nobody observes what a share is worth. A
baseball game is a cleaner experiment: news arrives on a schedule (a pitch every twenty seconds or so), MLB stamps each
pitch to the millisecond, and what it is worth can be worked out from the game state. Kalshi's game-winner markets
publish every trade to the microsecond, with the price, the size and the side that crossed the spread. This project
downloads all of them ({{trades26}} trades in {{games26}} games in 2026, {{trades25}} in {{games25}} games in 2025),
lines each one up against MLB's pitch-by-pitch record, and measures three things for every pitch: the fair move (how far
the price should go, from Baseball Savant's win expectancy shifted to agree with the market a second before the pitch),
the response (where the market actually traded over the next two minutes), and what every trade earned one minute later.

## What it found (2026)

| Question | Answer |
|---|---|
| Does the price move before the pitch? | **No.** Five seconds before, it has absorbed {{beta_m5}} of the coming move; a placebo pitch ten seconds early: {{placebo}} (95% interval {{placebo_lo}} to {{placebo_hi}}). |
| How fast? | The trading price is halfway to its new level **{{t50}} s** after the pitch (95% interval {{t50_lo}}&ndash;{{t50_hi}}) and 90% there by {{t90}} s. On the {{big26}} big pitches (fair value moved 4+ points), the first trade past halfway came a median **{{half_med}} s** after the pitch: {{within1}} within one second, {{within2}} within two. |
| Faster than MLB's own feed? | **Yes.** {{ahead_feed}} of big pitches traded past halfway before MLB's feed marked the result final (feed: a median {{feed_called}} s for a called pitch, {{feed_inplay}} s for a ball in play). |
| Who gets there first? | Big orders in the direction of the news: a median {{first_size}} contracts, {{first_ratio}} times the typical order. Busier markets are faster ({{act_hi}} s in the busiest third of moments, {{act_lo}} s in the quietest). |
| Is it getting faster? | **Yes.** In 2025, a big pitch took a median {{h25}} s to trade past halfway and {{a25}} were priced before MLB's feed; in 2026, {{half_med}} s and {{ahead_feed}}. Within 2026: {{mar_half}} s in March to {{sep_half}} s in September, and {{band_first}} s to {{band_last}} s in equally busy markets. |
| Does it move the right amount? | **Yes.** A minute after a big pitch the market has moved {{beta60_big}} times the fair move ({{beta60_lo}}&ndash;{{beta60_hi}}). After 30 s, {{drift_short}}; the final result on the fair move: slope {{outcome}} (SE {{outcome_se}}). Prices are calibrated; Brier {{brier_m}} against {{brier_a}} for the average-team model. |
| Who pays for speed? | Trades in the five seconds after a pitch that moved the price 2+ points were {{after_news_share}} of contracts and cost makers {{after_news_c}}&cent; each; every other trade earned makers {{rest_c}}&cent;. Makers handed back **{{given_back}}** of their ordinary trading profit (95% interval {{gb_lo}}&ndash;{{gb_hi}}), about ${{tax_total}} over the season. |

The measurements were checked on a simulated market with known repricing times ({{sim_games}} games): the first trade
past halfway always comes after the true repricing, by a median of {{sim_lag}} s, and makers' one-minute markouts come
back within {{sim_markout}} of the truth.

## Run it

```bash
pip install -r requirements.txt
make data       # Kalshi markets and trades, MLB play-by-play, Savant pitch states (slow: polite request spacing)
make all        # tables, event study, simulation, analysis, the page, tests
make serve      # http://localhost:8646
```

`make site` also draws the share card with headless Google Chrome. Every number on the page and in this README is
written by `pipeline/story.py` from the pipeline's outputs, and the renderer refuses to run if a number has no value.

## Pipeline

| Step | File | What it does |
|---|---|---|
| Fetch | `pipeline/fetch_kalshi.py`, `fetch_mlb.py`, `fetch_savant.py` | Kalshi's public trade archive (no key needed); MLB play-by-play with each pitch's two timestamps; Savant pitch rows with game state and win expectancy |
| Build | `pipeline/build_mlb.py`, `build_savant.py`, `build_trades.py` | One row per pitch with its state and win expectancy; flags pitches followed by a between-pitch state change (pickoffs, balks); matches each market to its game by teams, date and close time, and converts every trade to home-team terms |
| Tape | `pipeline/tape.py` | Reads quotes off the tape: fills that share a time and side are one taker order; the latest buy and sell bracket the midpoint; a side that is crossed or stale is dropped |
| Event study | `pipeline/events.py` | For every pitch: the fair move, the midpoint at 44 offsets from 30 s before to 120 s after, the first trade past halfway, pre-pitch activity; for every fill: one-minute markouts and fees, by seconds since the pitch |
| Analysis | `pipeline/analysis.py` | Response curves, latency, accuracy and drift tests (clustered by game), calibration, the maker/taker split, the order-flow pulse, a placebo; intervals resample whole games |
| Simulation | `pipeline/simulate.py` | A market with known repricing delays, run through the same estimators |
| Site | `pipeline/export.py`, `story.py`, `tools/og.py` | Site data, the page and this README with every number filled in, the share card |

## Checks

`tests/` ({{n_tests}} tests): order grouping and the trade-implied midpoint (consistent, stale and crossed books, no
look-ahead), the fair-move formula, event labels, exposure accounting, ticker parsing and team splitting, and the
simulation recovering known answers. Every matched market settled the way the final score says it should
({{settle26}} in 2026, {{settle25}} in 2025).

## Limits

Kalshi's archive keeps trades, not the order book, so a quote move is seen only when someone trades against it; the
times here are upper bounds by a fraction of a second. The clock is MLB's pitch timestamp, so any delay in MLB's system
is inside every number. The fair move comes from an average-team model shifted to the market's view, which ignores who
is batting and pitching. One-minute markouts include the next pitches' news, which averages out but adds noise. Fees
follow Kalshi's published schedule for the series (taker 0.035 &times; p(1 &minus; p), maker 0.00875 &times; p(1 &minus; p)
per contract). One exchange; nothing here is a recommendation to trade.

Data from Kalshi's public market-data API, the MLB Stats API and Baseball Savant. Raw trades are not republished. Not
affiliated with Kalshi, MLB or any club.
