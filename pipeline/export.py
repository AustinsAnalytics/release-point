"""Everything the page draws, in one file: site/data/release.json.

    python pipeline/export.py

Reads data/out/results.json (analysis.py), data/out/simulation.json (simulate.py), the event tables, and, for the
opening figure, every trade around one pitch: the home run of the season that the market repriced the most.
"""
import gzip
import json

import duckdb
import numpy as np
import pandas as pd

from common import DATA, OUT, RAW, ROOT, SEASONS
from events import GRID
from tape import build_tape, mid_at

SITE = ROOT / "site"


def season_meta(season):
    con = duckdb.connect()
    t = con.execute(f"""select count(*), sum(contracts), count(distinct game_pk)
                        from '{DATA / "interim" / str(season) / "trades.parquet"}'""").fetchone()
    g = pd.read_parquet(DATA / "interim" / str(season) / "games.parquet")
    p = pd.read_parquet(DATA / "interim" / str(season) / "pitches.parquet", columns=["game_pk"])
    return {"trades": int(t[0]), "contracts": float(t[1]), "games_traded": int(t[2]), "games": int(len(g)),
            "pitches": int(len(p))}


def hero(season=2026):
    """The home run the market moved on most, with every fill from 8 seconds before to 30 seconds after."""
    ev = pd.read_parquet(OUT / str(season) / "events.parquet")
    # a clear picture: a big move that stays inside 15-85 cents, a market that traded in the five seconds before, a
    # steady price before the pitch and after the dust settles; postseason games first, then the biggest move
    post = ev.p_ref + ev.F
    ev = ev[(ev.kind == "Home run") & ev.clean & ~ev.last_pitch & (ev.age <= 5) & ev.p_ref.between(15, 85)
            & post.between(15, 85) & ev.F.abs().between(10, 30) & ev.half_time.notna()
            & ((ev["m-5"] - ev["m-1"]).abs() <= 1) & ((ev["m+30"] - ev["m+20"]).abs() <= 1.5)]
    ev = ev.assign(score=ev.F.abs() + 20 * (ev.game_type != "R")).sort_values("score", ascending=False)
    con = duckdb.connect()
    trades_path = DATA / "interim" / str(season) / "trades.parquet"
    for _, e in ev.head(25).iterrows():
        lo, hi = int(e.t0 - 8e6), int(e.t0 + 30e6)
        tr = con.execute(f"select ts, home_cents, dir, contracts from '{trades_path}' where game_pk = {e.game_pk} "
                         f"and ts between {int(e.t0 - 600e6)} and {hi} order by ts").df()
        win = tr[tr.ts >= lo]
        if len(win) < 40:
            continue
        tape = build_tape(tr.ts.to_numpy(), tr.home_cents.to_numpy(float), tr.dir.to_numpy(),
                          tr.contracts.to_numpy(float))
        grid = np.arange(-8, 30.01, 0.1)
        mid = mid_at(tape, (e.t0 + grid * 1e6).astype(np.int64))
        pk = int(e.game_pk)
        p = pd.read_parquet(DATA / "interim" / str(season) / "pitches.parquet")
        row = p[(p.game_pk == pk) & (p.t_start == e.t0)].iloc[0]
        pbp = json.loads(gzip.decompress((RAW / "mlb" / str(season) / "pbp" / f"{pk}.json.gz").read_bytes()))
        play = next(pl for pl in pbp["allPlays"] if pl["about"]["atBatIndex"] == row.ab_index)
        g = pd.read_parquet(DATA / "interim" / str(season) / "games.parquet").set_index("game_pk").loc[pk]
        # report in the batting team's terms: a home run is good news for the team that hit it
        batting_home = not bool(e.top)
        flip = (lambda v: v) if batting_home else (lambda v: 100 - v)
        return {
            "game_pk": pk, "date": g.official_date, "away": g.away, "home": g.home, "game_type": g.game_type,
            "inning": int(e.inning), "top": bool(e.top), "batter": play["matchup"]["batter"]["fullName"],
            "batting_team": g.home if batting_home else g.away,
            "description": play["result"]["description"],
            "F": float(e.F if batting_home else -e.F), "p_ref": float(flip(e.p_ref)),
            "half_time": float(e.half_time), "feed_delay": float(e.feed_delay),
            "trades": [[round((t - e.t0) / 1e6, 3), round(float(flip(c)), 2), int(d if batting_home else -d),
                        round(float(s), 2)] for t, c, d, s in win.itertuples(index=False)],
            "mid": [[round(float(x), 1), round(float(flip(m)), 2)] for x, m in zip(grid, mid) if np.isfinite(m)],
        }
    raise RuntimeError("no home run with enough trades around it")


def main():
    res = json.loads((OUT / "results.json").read_text())
    sim = json.loads((OUT / "simulation.json").read_text())
    out = {"grid": GRID.tolist(), "seasons": {}, "sim": {k: sim[k] for k in ("curve_grid", "beta_est", "beta_true")}}
    for s in SEASONS:
        r = res.get(str(s))
        if not r:
            continue
        sp = r["speed"]
        out["seasons"][str(s)] = {
            "meta": {**season_meta(s), "usable": r["usable"], "big": r["big"]},
            "beta_all": sp["beta_all"], "beta_big": sp["beta_big"], "half_hist": sp["half_time"]["hist"],
            "kinds": [{"kind": k, **{x: v[x] for x in ("n", "median_F", "half_median", "half_q25", "half_q75",
                                                       "feed_median", "ahead_of_feed", "beta60")}}
                      for k, v in sp["by_kind"].items()],
            "markouts": r["speed_tax"]["curve"], "pulse": r["pulse"], "calibration": r["accuracy"]["calibration"],
            "monthly": r["monthly"]}
    out["hero"] = hero()
    (SITE / "data").mkdir(parents=True, exist_ok=True)
    (SITE / "data" / "release.json").write_text(json.dumps(out, separators=(",", ":"), allow_nan=False))
    h = out["hero"]
    print(f"site data written; opening figure: {h['batter']}, {h['away']} at {h['home']} {h['date']} "
          f"({h['description'][:60]}...)", flush=True)


if __name__ == "__main__":
    main()
