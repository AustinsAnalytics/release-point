# Release Point

**How fast does a market price a pitch?** Every in-game trade on Kalshi's MLB game markets in 2025 and 2026, lined up
to the millisecond against the pitch before it.
Site: https://austinsanalytics.github.io/release-point/

A stock market is an awkward place to study how prices absorb news, because nobody observes what a share is worth. A
baseball game is a cleaner experiment: news arrives on a schedule (a pitch every twenty seconds or so), MLB stamps each
pitch to the millisecond, and what it is worth can be worked out from the game state. Kalshi's game-winner markets
publish every trade to the microsecond, with the price, the size and the side that crossed the spread. This project
downloads the trades made during the games (40.1 million in 2,469 games in 2026, 3.2 million in 2,185
games in 2025, plus the 45 minutes before each first pitch), lines each one up against MLB's pitch-by-pitch record, and measures three things for every pitch: the fair move (how far
the price should go, from Baseball Savant's win expectancy shifted to agree with the market a second before the pitch),
the response (where the market actually traded over the next two minutes), and what every trade earned one minute later.

## What it found (2026)

| Question | Answer |
|---|---|
| Does the price move before the pitch? | **No.** Five seconds before, it has absorbed 0.01% of the coming move; a placebo pitch ten seconds early: 0.00% (95% interval −0.07% to 0.06%). |
| How fast? | The trading price is halfway to its new level **6.1 s** after the pitch (95% interval 6.0&ndash;6.2) and 90% there by 18.6 s. On the 39,725 big pitches (fair value moved 4+ points), the first trade past halfway came a median **4.0 s** after the pitch: 4% within one second, 18% within two. |
| Faster than MLB's own feed? | **Yes.** 83% of big pitches traded past halfway before MLB's feed marked the result final (feed: a median 3.9 s for a called pitch, 9.6 s for a ball in play). |
| Who gets there first? | Big orders in the direction of the news: a median 133 contracts, 3.6 times the median order in the same game. Busier markets are faster (3.2 s in the busiest third of moments, 5.0 s in the quietest). |
| Is it getting faster? | **Yes.** In 2025, a big pitch took a median 17.6 s to trade past halfway and 20% were priced before MLB's feed; in 2026, 4.0 s and 83%. Within 2026: 8.9 s in March to 2.9 s in September, and 6.8 s to 2.8 s in equally busy markets. (A pitch never traded past halfway within a minute counts as slower than a minute.) |
| Does it move the right amount? | **Yes.** A minute after a big pitch the market has moved 1.02 times the fair move (1.01&ndash;1.02). After 30 s, the next 90 s add 4.4% of the fair move (SE 0.4%), about 0.28&cent;, under the cost of one trade; the final result on the fair move: slope 0.060 (SE 0.013). Prices are calibrated; Brier 0.1749 against 0.1775 for the average-team model. |
| Who pays for speed? | Trades in the five seconds after a pitch that moved fair value 2+ points were 5.0% of contracts and cost makers 2.83&cent; each; every other trade earned makers 0.39&cent;. Before fees, makers handed back **38%** of what they earned on ordinary trades (95% interval 35%&ndash;42%), about $11.4 million over the season; after Kalshi's maker fee, 62%. |

The measurements were checked on a simulated market with known repricing times (400 games): the first trade
past halfway comes after the true repricing every time, by a median of 0.23 s, and makers' one-minute markouts
come back within 0.02% of the truth.

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
| Build | `pipeline/build_mlb.py`, `build_savant.py`, `build_trades.py` | One row per pitch with its state and win expectancy; flags pitches followed by a between-pitch state change (pickoffs, balks); matches each market to its game by teams and close time (a postponed game keeps its original date in Kalshi's ticker), keeps trades from 45 minutes before first pitch, and converts every trade to home-team terms |
| Tape | `pipeline/tape.py` | Reads quotes off the tape: fills that share a time and side are one taker order; the latest buy and sell bracket the midpoint; a side that is crossed or stale is dropped; the typical spread is a running median, so nothing looks ahead |
| Event study | `pipeline/events.py` | For every pitch: the fair move, the midpoint at 44 offsets from 30 s before to 120 s after, the first trade past halfway, pre-pitch activity; for every fill: one-minute markouts and fees, by seconds since the pitch |
| Analysis | `pipeline/analysis.py` | Response curves, latency, accuracy and drift tests (clustered by game), calibration, the maker/taker split, the order-flow pulse, a placebo; intervals resample whole games |
| Simulation | `pipeline/simulate.py` | A market with known repricing delays, run through the same estimators |
| Site | `pipeline/export.py`, `story.py`, `tools/og.py` | Site data, the page and this README with every number filled in, the share card |

## Checks

`tests/` (22 tests): order grouping and the trade-implied midpoint (consistent, stale and crossed books, no
look-ahead in prices or spreads), the fair-move formula, event labels, exposure accounting, ticker parsing, team
splitting and matching markets to games (doubleheaders, postponed games), and the simulation recovering known answers. Every matched market settled the way the final score says it should
(4,938 of 4,938 in 2026, 4,370 of 4,370 in 2025).

## Limits

Kalshi's archive keeps trades, not the order book, so a quote move is seen only when someone trades against it; the
times here run a little late (by a median of 0.23 s on the simulated market). The clock is MLB's pitch timestamp, so any delay in MLB's system
is inside every number. The fair move comes from an average-team model shifted to the market's view, which ignores who
is batting and pitching. One-minute markouts include the next pitches' news, which averages out but adds noise. Fees
follow the formula Kalshi publishes for these markets (taker 0.035 &times; p(1 &minus; p), maker 0.00875 &times; p(1 &minus; p)
dollars per contract), before any rounding to the cent. One exchange; nothing here is a recommendation to trade.

Data from Kalshi's public market-data API, the MLB Stats API and Baseball Savant. Raw trades are not republished; the
aggregated results are in `data/out/results.json` and `data/out/simulation.json`, and everything the page draws is in
`site/data/release.json`. Not affiliated with Kalshi, MLB or any club.
