"""Match each Kalshi market to its MLB game and convert the trades into one table, in home-team terms.

    python pipeline/build_trades.py 2026

Every game has two markets, "home team wins" and "away team wins". A trade in either is a trade in the home team's
win probability: buying "away wins" at q cents is selling the home team at 100 - q. Each trade is stored with
  home_cents  the price in home-win terms (cents = probability points)
  dir         +1 if the taker bought the home team, -1 if the taker sold it
  contracts   number of $1 contracts
Output: data/interim/<season>/trades.parquet (sorted by game, then time) and markets.parquet (the game matching).
"""
import gzip
import json
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from common import DATA, RAW
from fetch_kalshi import EDT, parse_event

ALIASES = {"ARI": "AZ"}          # Kalshi used ARI for a few early-2025 games; MLB's code is AZ


def split_teams(code, known):
    """'TBBOS' -> ('TB', 'BOS') using the set of known team codes."""
    for i in range(2, len(code) - 1):
        a, h = code[:i], code[i:]
        if a in known and h in known:
            return a, h
    return None, None


def match_markets(season):
    ms = [m for m in json.loads((RAW / "kalshi" / "markets.json").read_text())
          if m["ticker"].startswith(f"KXMLBGAME-{season % 100:02d}")]
    games = pd.read_parquet(DATA / "interim" / str(season) / "games.parquet")
    games["et_date"] = pd.to_datetime(games.scheduled_utc, unit="us", utc=True).dt.tz_convert(EDT).dt.date
    known = {m["ticker"].rsplit("-", 1)[1] for m in ms}
    rows = []
    for m in ms:
        day, start, teams, gnum = parse_event(m["event_ticker"])
        away, home = split_teams(teams, known)
        side_code = m["ticker"].rsplit("-", 1)[1]
        rows.append({"ticker": m["ticker"], "event_ticker": m["event_ticker"], "source": m["source"],
                     "away_k": ALIASES.get(away, away), "home_k": ALIASES.get(home, home),
                     "team_k": ALIASES.get(side_code, side_code), "game_number_k": gnum, "et_date": day,
                     "close_us": int(datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp() * 1e6),
                     "result": m.get("result"), "volume": float(m.get("volume_fp") or 0)})
    mk = pd.DataFrame(rows)
    # same teams on the same date; when there are two (a doubleheader), the game that ended closest to the moment the
    # market closed (Kalshi closes a game market right after the final out). A G1/G2 tag, when present, must agree.
    cand = mk.merge(games[["game_pk", "et_date", "away", "home", "game_number", "home_win", "last_event_utc"]],
                    left_on=["et_date", "away_k", "home_k"], right_on=["et_date", "away", "home"], how="left")
    cand = cand[cand.game_number_k.isna() | (cand.game_number == cand.game_number_k) | cand.game_pk.isna()]
    cand["dt"] = (cand.close_us - cand.last_event_utc).abs()
    cand = cand.sort_values(["ticker", "dt"]).drop_duplicates("ticker")
    cand["side"] = np.where(cand.team_k == cand.home_k, "home", np.where(cand.team_k == cand.away_k, "away", None))
    ok = cand.game_pk.notna() & cand.side.notna() & cand.result.isin(["yes", "no"])
    # check the settlement against the final score: the home market settles yes exactly when the home team won
    cand["settles_right"] = np.where(cand.side == "home", (cand.result == "yes") == cand.home_win,
                                     (cand.result == "yes") == ~cand.home_win.astype(bool))
    out = cand[ok].copy()
    out["game_pk"] = out.game_pk.astype(int)
    print(f"{season}: {len(mk)} markets, {ok.sum()} matched to a final game "
          f"({out.game_pk.nunique()} games); settlement agrees with the final score for "
          f"{out.settles_right.sum()} of {len(out)}", flush=True)
    keep = ["ticker", "event_ticker", "source", "game_pk", "side", "result", "volume", "settles_right"]
    out[keep].to_parquet(DATA / "interim" / str(season) / "markets.parquet", index=False)
    return out[out.settles_right.astype(bool)]


def read_trades(path):
    rows = [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines() if line.strip()]
    if not rows:
        return None
    t = pd.DataFrame(rows, columns=["created", "yes", "contracts", "taker", "block"])
    t["ts"] = pd.to_datetime(t.created, utc=True, format="ISO8601").astype("int64") // 1000     # microseconds
    t["yes_cents"] = (t.yes.astype(float) * 100).round(4)
    t["contracts"] = t.contracts.astype(float)
    t["taker_yes"] = t.taker == "yes"
    return t[["ts", "yes_cents", "contracts", "taker_yes", "block"]]


def to_home(t, side):
    """Express one market's trades in home-team terms. In the away market, YES at q cents is the home team at
    100 - q, and a taker buying YES is selling the home team."""
    home = side == "home"
    t = t.copy()
    t["home_cents"] = t.yes_cents if home else 100 - t.yes_cents
    t["dir"] = np.where(t.taker_yes == home, 1, -1).astype("int8")
    t["side"] = side
    return t


def build(season):
    mk = match_markets(season)
    folder = RAW / "kalshi" / "trades" / str(season)
    schema = pa.schema([("game_pk", pa.int64()), ("ts", pa.int64()), ("home_cents", pa.float32()),
                        ("dir", pa.int8()), ("contracts", pa.float32()), ("side", pa.string()), ("block", pa.bool_())])
    path = DATA / "interim" / str(season) / "trades.parquet"
    writer = pq.ParquetWriter(path, schema, compression="zstd")
    n, games, missing = 0, 0, 0
    for pk, grp in mk.groupby("game_pk"):
        parts = []
        for _, m in grp.iterrows():
            f = folder / f"{m.ticker}.jsonl.gz"
            if not f.exists():
                missing += 1
                continue
            t = read_trades(f)
            if t is None:
                continue
            parts.append(to_home(t, m.side))
        if not parts:
            continue
        t = pd.concat(parts).sort_values("ts", kind="stable")
        t["game_pk"] = pk
        writer.write_table(pa.Table.from_pandas(t[schema.names], schema=schema, preserve_index=False))
        n += len(t)
        games += 1
    writer.close()
    print(f"{season}: {n:,} trades in {games} games ({missing} market files not downloaded yet)", flush=True)


if __name__ == "__main__":
    for s in map(int, sys.argv[1:]):
        build(s)
