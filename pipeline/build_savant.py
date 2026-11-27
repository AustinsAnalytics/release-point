"""Join Baseball Savant's pitch rows (game state and published win expectancy) to MLB's timestamped pitches.

    python pipeline/build_savant.py 2026

Savant's home_win_exp is the home team's win expectancy before the pitch, for an average team, by inning, score,
bases, outs and count; delta_home_win_exp is the change the pitch made (including anything that happened on it, such as
a stolen base). Within a game, home_win_exp of the next pitch = home_win_exp + delta_home_win_exp exactly.
Output: data/interim/<season>/pitch_states.parquet, one row per MLB pitch that Savant also has.
"""
import sys

import numpy as np
import pandas as pd

from common import DATA, RAW
from build_mlb import BETWEEN_PITCH_STATE_CHANGES

COLS = ["game_pk", "game_type", "at_bat_number", "pitch_number", "inning", "inning_topbot", "balls", "strikes",
        "outs_when_up", "on_1b", "on_2b", "on_3b", "home_score", "away_score", "post_home_score", "post_away_score",
        "home_win_exp", "delta_home_win_exp", "delta_run_exp", "events", "description", "batter", "pitcher",
        "launch_speed", "hit_distance_sc"]


def build(season):
    parts = []
    for f in sorted((RAW / "savant" / str(season)).glob("*.csv.gz")):
        d = pd.read_csv(f, compression="gzip", usecols=lambda c: c in COLS, low_memory=False)
        if len(d):
            parts.append(d)
    sv = pd.concat(parts, ignore_index=True).drop_duplicates(["game_pk", "at_bat_number", "pitch_number"])
    sv["bases"] = sv.on_1b.notna() * 1 + sv.on_2b.notna() * 2 + sv.on_3b.notna() * 4
    sv = sv.drop(columns=["on_1b", "on_2b", "on_3b"])

    folder = DATA / "interim" / str(season)
    p = pd.read_parquet(folder / "pitches.parquet")
    p["at_bat_number"] = p.ab_index + 1
    m = p.merge(sv, on=["game_pk", "at_bat_number", "pitch_number"], how="inner", suffixes=("", "_sv"))
    m = m.sort_values(["game_pk", "t_start", "ev_index"]).reset_index(drop=True)
    m["we_before"] = m.home_win_exp
    m["we_after"] = m.home_win_exp + m.delta_home_win_exp

    # a pitch is "clean" if nothing outside the pitch itself changed the state before the next pitch
    a = pd.read_parquet(folder / "actions.parquet")
    a = a[a.event_type.isin(BETWEEN_PITCH_STATE_CHANGES) | (a.type == "pickoff") & (a.outs_made > 0)]
    m["next_start"] = m.groupby("game_pk").t_start.shift(-1)
    dirty = set()
    for pk, grp in a.groupby("game_pk"):
        g = m[m.game_pk == pk]
        idx = np.searchsorted(g.t_start.to_numpy(), grp.t_start.to_numpy(), side="right") - 1
        dirty.update(g.index[idx[idx >= 0]].tolist())
    m["clean"] = ~m.index.isin(dirty)
    m["last_pitch"] = m.next_start.isna()
    m.to_parquet(folder / "pitch_states.parquet", index=False)
    print(f"{season}: Savant has {len(sv):,} pitches; matched {len(m):,} of {len(p):,} MLB pitches "
          f"({len(m) / len(p):.2%}); {(~m.clean).sum():,} have a between-pitch state change", flush=True)


if __name__ == "__main__":
    for s in map(int, sys.argv[1:]):
        build(s)
