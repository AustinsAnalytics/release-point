"""Kalshi public market data: every MLB game-winner market and each one's trades during the game.

    python pipeline/fetch_kalshi.py markets          # market list (settled markets live under /historical)
    python pipeline/fetch_kalshi.py trades 2026      # trades from 45 minutes before first pitch to market close

No account or key is needed; these are public endpoints. One file per market lands in
data/raw/kalshi/trades/<season>/<ticker>.jsonl.gz; markets already on disk are skipped.
Each line is one trade: [created_time, yes_price, contracts, taker_side, is_block_trade].
"""
import gzip
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

from common import RAW, RateLimiter, get_json, write_atomic

API = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXMLBGAME"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
                                       "DEC"], 1)}
EDT = timezone(timedelta(hours=-4))      # every game in both seasons was played under daylight time


def markets():
    out = []
    for source, path in (("historical", "/historical/markets"), ("live", "/markets")):
        cursor = ""
        while True:
            d = get_json(f"{API}{path}?series_ticker={SERIES}&limit=1000" + (f"&cursor={cursor}" if cursor else ""))
            out += [{**m, "source": source} for m in d.get("markets", [])]
            cursor = d.get("cursor")
            if not cursor or not d.get("markets"):
                break
    seen, uniq = set(), []
    for m in out:                         # a market can appear in both listings around the archive cutoff
        if m["ticker"] not in seen:
            seen.add(m["ticker"])
            uniq.append(m)
    write_atomic(RAW / "kalshi" / "markets.json", json.dumps(uniq).encode())
    print(f"markets: {len(uniq)}", flush=True)


def parse_event(event_ticker):
    """'KXMLBGAME-26JUL171910TBBOSG2' -> (date 2026-07-17, start 19:10 Eastern as UTC, 'TBBOS', game 2).
    2025 tickers carry no start time ('KXMLBGAME-25APR16ATHCWS'); start is then None. Game is None unless tagged."""
    code = event_ticker.split("-")[1]
    day = date(2000 + int(code[0:2]), MONTHS[code[2:5]], int(code[5:7]))
    rest, start, game = code[7:], None, None
    if rest[:4].isdigit():
        start = datetime(day.year, day.month, day.day, int(rest[:2]), int(rest[2:4]), tzinfo=EDT).astimezone(
            timezone.utc)
        rest = rest[4:]
    if rest[-2:] in ("G1", "G2"):
        rest, game = rest[:-2], int(rest[-1])
    return day, start, rest, game


def scheduled_start(event_ticker):
    """The ticker's scheduled first pitch as UTC, or None when the ticker has no time."""
    return parse_event(event_ticker)[1]


def trades(season, workers=10, rate=10.0):
    ms = [m for m in json.loads((RAW / "kalshi" / "markets.json").read_text())
          if m["ticker"].startswith(f"{SERIES}-{season % 100:02d}")]
    folder = RAW / "kalshi" / "trades" / str(season)
    todo = [m for m in ms if not (folder / f"{m['ticker']}.jsonl.gz").exists()]
    print(f"{season} trades: {len(ms)} markets, {len(todo)} to fetch", flush=True)
    limiter = RateLimiter(rate)

    def one(m):
        start = scheduled_start(m["event_ticker"])
        if start:                                  # from 45 minutes before the scheduled first pitch
            lo = int((start - timedelta(minutes=45)).timestamp())
        else:                                      # 2025 markets opened the morning of the game: take all of it
            lo = int(datetime.fromisoformat(m["open_time"].replace("Z", "+00:00")).timestamp())
        close = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        hi = int((close + timedelta(minutes=10)).timestamp())
        path = "/historical/trades" if m["source"] == "historical" else "/markets/trades"
        rows, cursor = [], ""
        while True:
            d = get_json(f"{API}{path}?ticker={m['ticker']}&min_ts={lo}&max_ts={hi}&limit=1000"
                         + (f"&cursor={cursor}" if cursor else ""), limiter)
            for t in d.get("trades", []):
                rows.append([t["created_time"], t["yes_price_dollars"], t["count_fp"], t["taker_side"],
                             bool(t.get("is_block_trade"))])
            cursor = d.get("cursor")
            if not cursor or not d.get("trades"):
                break
        body = "\n".join(json.dumps(r) for r in rows).encode()
        write_atomic(folder / f"{m['ticker']}.jsonl.gz", gzip.compress(body, 6))
        return len(rows)

    total = 0
    with ThreadPoolExecutor(workers) as pool:
        for i, f in enumerate(as_completed([pool.submit(one, m) for m in todo]), 1):
            total += f.result()
            if i % 100 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} markets, {total:,} trades", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "markets":
        markets()
    else:
        for s in map(int, sys.argv[2:]):
            trades(s)
