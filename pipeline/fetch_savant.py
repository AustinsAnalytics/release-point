"""Baseball Savant: every pitch, one CSV per game day, regular season and postseason.

    python pipeline/fetch_savant.py 2026

Needs data/raw/mlb/<season>/schedule.json (run fetch_mlb.py first). Savant's pitch rows carry the game state and
its published win expectancy before each pitch (home_win_exp) and the change the pitch made (delta_home_win_exp).
"""
import gzip
import json
import sys
import time
import urllib.parse

from common import RAW, get, write_atomic


def days(season):
    d = json.loads((RAW / "mlb" / str(season) / "schedule.json").read_text())
    return sorted({day["date"] for day in d["dates"] for g in day["games"]
                   if g["status"].get("codedGameState") == "F"})


def fetch(season):
    folder = RAW / "savant" / str(season)
    todo = [day for day in days(season) if not (folder / f"{day}.csv.gz").exists()]
    print(f"{season} savant: {len(todo)} game days to fetch", flush=True)
    for i, day in enumerate(todo, 1):
        q = urllib.parse.urlencode({
            "all": "true", "hfGT": "R|F|D|L|W|", "hfSea": f"{season}|", "player_type": "pitcher",
            "game_date_gt": day, "game_date_lt": day, "min_pitches": 0, "min_results": 0, "group_by": "name",
            "sort_col": "pitches", "sort_order": "desc", "min_abs": 0, "type": "details"})
        body = get("https://baseballsavant.mlb.com/statcast_search/csv?" + q, accept="text/csv")
        write_atomic(folder / f"{day}.csv.gz", gzip.compress(body, 6))
        if i % 20 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] {day}: {body.count(b'\n') - 1} pitches", flush=True)
        time.sleep(1.5)


if __name__ == "__main__":
    for s in map(int, sys.argv[1:]):
        fetch(s)
