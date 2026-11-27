"""Parse MLB play-by-play into one row per pitch (with both of its timestamps) and one row per non-pitch event.

    python pipeline/build_mlb.py 2026

Every pitch in MLB's feed carries two times. `startTime` is when the pitch happened; `endTime` is when its result was
final in the feed (about 4 seconds later for a called pitch, about 10 for a ball in play). The analysis uses both.
Output: data/interim/<season>/{games,pitches,actions}.parquet
"""
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime

import pandas as pd

from common import DATA, RAW

# non-pitch events that change the base-out state on their own, between pitches (not during one)
BETWEEN_PITCH_STATE_CHANGES = {
    "pickoff_1b", "pickoff_2b", "pickoff_3b", "pickoff_error_1b", "pickoff_error_2b", "pickoff_error_3b",
    "pickoff_caught_stealing_2b", "pickoff_caught_stealing_3b", "pickoff_caught_stealing_home", "balk",
    "forced_balk", "error", "other_advance", "other_out", "runner_double_play"}


def ts_us(s):
    """'2026-09-26T16:37:23.972Z' -> microseconds since the epoch (UTC)."""
    if not s:
        return None
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1_000_000)


def parse_game(d, pk):
    pitches, actions = [], []
    for pl in d["allPlays"]:
        ab, about = pl["about"]["atBatIndex"], pl["about"]
        moved = defaultdict(list)
        for r in pl.get("runners", []):
            moved[r["details"].get("playIndex")].append(r)
        pitch_idx = [e["index"] for e in pl["playEvents"] if e.get("isPitch")]
        last_pitch = pitch_idx[-1] if pitch_idx else None
        for e in pl["playEvents"]:
            det = e.get("details", {})
            row = {"game_pk": pk, "ab_index": ab, "ev_index": e["index"], "inning": about["inning"],
                   "top": about["isTopInning"], "t_start": ts_us(e.get("startTime")), "t_end": ts_us(e.get("endTime")),
                   "runners_moved": bool(moved.get(e["index"])),
                   "outs_made": sum(bool(r["movement"].get("isOut")) for r in moved.get(e["index"], []))}
            if e.get("isPitch"):
                ends_pa = e["index"] == last_pitch and about.get("isComplete", True) and bool(pl["result"].get("type"))
                pitches.append({**row, "pitch_number": e.get("pitchNumber"), "call": (det.get("call") or {}).get("code"),
                                "description": det.get("description"), "in_play": bool(det.get("isInPlay")),
                                "ends_pa": ends_pa, "pa_event": pl["result"].get("eventType") if ends_pa else None,
                                "play_id": e.get("playId")})
            else:
                actions.append({**row, "type": e.get("type"), "event_type": det.get("eventType"),
                                "description": (det.get("description") or "")[:120]})
    return pitches, actions


def build(season):
    sched = json.loads((RAW / "mlb" / str(season) / "schedule.json").read_text())
    games, all_p, all_a = {}, [], []
    for day in sched["dates"]:
        for g in day["games"]:
            if g["status"].get("codedGameState") != "F":
                continue
            games[g["gamePk"]] = {
                "game_pk": g["gamePk"], "season": season, "game_type": g["gameType"], "official_date": g["officialDate"],
                "scheduled_utc": ts_us(g["gameDate"]), "double_header": g.get("doubleHeader"),
                "game_number": g.get("gameNumber"), "away": g["teams"]["away"]["team"]["abbreviation"],
                "home": g["teams"]["home"]["team"]["abbreviation"], "away_score": g["teams"]["away"].get("score"),
                "home_score": g["teams"]["home"].get("score"), "venue": g.get("venue", {}).get("name"),
                "scheduled_innings": g.get("scheduledInnings", 9)}
    folder = RAW / "mlb" / str(season) / "pbp"
    for i, pk in enumerate(sorted(games)):
        f = folder / f"{pk}.json.gz"
        if not f.exists():
            continue
        p, a = parse_game(json.loads(gzip.decompress(f.read_bytes())), pk)
        all_p += p
        all_a += a
        if p:
            games[pk]["first_pitch_utc"] = min(x["t_start"] for x in p if x["t_start"])
            games[pk]["last_event_utc"] = max(x["t_end"] or x["t_start"] for x in p + a if (x["t_end"] or x["t_start"]))
    out = DATA / "interim" / str(season)
    out.mkdir(parents=True, exist_ok=True)
    g = pd.DataFrame(games.values())
    g["home_win"] = g.home_score > g.away_score
    g.to_parquet(out / "games.parquet", index=False)
    pd.DataFrame(all_p).to_parquet(out / "pitches.parquet", index=False)
    pd.DataFrame(all_a).to_parquet(out / "actions.parquet", index=False)
    print(f"{season}: {len(g)} games, {len(all_p):,} pitches, {len(all_a):,} other events", flush=True)


if __name__ == "__main__":
    for s in map(int, sys.argv[1:]):
        build(s)
