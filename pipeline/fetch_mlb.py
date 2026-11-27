"""MLB Stats API: the schedule and the full play-by-play (with every pitch's timestamps) for each final game.

    python pipeline/fetch_mlb.py 2026        # regular season and postseason

Files land in data/raw/mlb/<season>/. Games already on disk are skipped, so the script can be re-run safely.
"""
import gzip
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import RAW, RateLimiter, get, write_atomic

API = "https://statsapi.mlb.com/api/v1"
GAME_TYPES = "R,F,D,L,W"          # regular season, wild card, division series, LCS, World Series


def schedule(season):
    out = RAW / "mlb" / str(season) / "schedule.json"
    body = get(f"{API}/schedule?sportId=1&season={season}&gameType={GAME_TYPES}&hydrate=team,venue")
    write_atomic(out, body)
    games = final_games(season)
    print(f"{season} schedule: {len(games)} final games", flush=True)
    return games


def final_games(season):
    d = json.loads((RAW / "mlb" / str(season) / "schedule.json").read_text())
    games = {}
    for day in d["dates"]:
        for g in day["games"]:
            if g["status"].get("codedGameState") == "F":
                games[g["gamePk"]] = g          # a suspended game is listed twice; keep one record per gamePk
    return games


def pbp(season, workers=4, rate=5.0):
    games = final_games(season)
    folder = RAW / "mlb" / str(season) / "pbp"
    todo = [pk for pk in sorted(games) if not (folder / f"{pk}.json.gz").exists()]
    print(f"{season} play-by-play: {len(games)} games, {len(todo)} to fetch", flush=True)
    limiter = RateLimiter(rate)

    def one(pk):
        body = get(f"{API}/game/{pk}/playByPlay", limiter)
        write_atomic(folder / f"{pk}.json.gz", gzip.compress(body, 6))

    with ThreadPoolExecutor(workers) as pool:
        for i, f in enumerate(as_completed([pool.submit(one, pk) for pk in todo]), 1):
            f.result()
            if i % 250 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)


if __name__ == "__main__":
    for s in map(int, sys.argv[1:]):
        schedule(s)
        pbp(s)
