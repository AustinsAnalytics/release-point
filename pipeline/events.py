"""The event study: how the market's price moves around every pitch, and what each trade earned.

    python pipeline/events.py 2026

For each pitch at time t0 (MLB's startTime, when the pitch happened):
  p_ref  trade-implied midpoint one second before the pitch
  F      the fair move, in probability points: Savant's win expectancy for an average team, shifted in log-odds so it
         agrees with the market before the pitch (the market's view of the two teams), then moved to the state after
         the pitch:  F = expit(logit(WE_after) + s) - p_ref,  s = logit(p_ref) - logit(WE_before)
  mids   the midpoint at t0 + tau for every tau on GRID
  half   seconds until the first order that trades more than halfway from p_ref toward p_ref + F
For each fill: its markout (what the maker earned) at several horizons, binned by seconds since the last pitch and by
how big that pitch's news was. Output: data/out/<season>/{events,markouts,pulse}.parquet
"""
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from common import DATA, OUT
from tape import build_tape, last_order_age, mid_at, orders

GRID = np.array([-30, -20, -15, -10, -7.5, -5, -4, -3, -2, -1.5, -1, -0.5, 0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2,
                 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 25, 30, 40, 50, 60, 90, 120])
REF_US = 1_000_000                      # reference price: one second before the pitch
HORIZONS = (5, 30, 60)                  # markout horizons, seconds
SINCE_BINS = np.array([0, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 30, 60, np.inf])
NEWS_BINS = np.array([0, 0.5, 2, 5, np.inf])     # |F| classes, probability points
PULSE_EDGES = np.arange(0, 60.5, 0.5)
TAKER_FEE, MAKER_FEE = 0.035, 0.00875   # Kalshi quadratic fees for this series (0.07 and 0.0175 at a 0.5 multiplier)


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def expit(x):
    return 1 / (1 + np.exp(-x))


def fair_move(p_ref, we_before, we_after):
    """Fair move in points given the market's pre-pitch price (points) and the average-team win expectancy."""
    p = p_ref / 100
    s = logit(p) - logit(we_before)
    post = np.where(we_after >= 0.9995, 1.0, np.where(we_after <= 0.0005, 0.0, expit(logit(we_after) + s)))
    return 100 * (post - p)


def classify(df):
    e = df.pa_event.fillna("")
    d = df.description.fillna("").str.lower()
    out = np.select(
        [e == "home_run", e.str.startswith("strikeout"), e.isin(["walk", "intent_walk", "hit_by_pitch"]),
         e.isin(["single", "double", "triple"]), df.ends_pa & df.in_play,
         d.str.contains("ball") & ~df.ends_pa, ~df.ends_pa],
        ["Home run", "Strikeout", "Walk or HBP", "Hit", "Out in play", "Ball", "Strike or foul"], "Other")
    return out


def exposure(gaps, edges):
    """Seconds of observation in each bin of time-since-pitch, given the lengths of the pitch-to-pitch intervals."""
    lo, hi = edges[:-1], edges[1:]
    return np.clip(np.minimum(gaps[:, None], hi) - lo, 0, None).sum(0)


def run(season):
    folder = DATA / "interim" / str(season)
    ps = pd.read_parquet(folder / "pitch_states.parquet")
    games = pd.read_parquet(folder / "games.parquet").set_index("game_pk")
    pf = pq.ParquetFile(folder / "trades.parquet")
    trades = pf.read(columns=["game_pk", "ts", "home_cents", "dir", "contracts"]).to_pandas()
    tgroups = trades.groupby("game_pk").indices
    out = OUT / str(season)
    out.mkdir(parents=True, exist_ok=True)

    ev_rows, mk_rows, pulse_rows = [], [], []
    for n, (pk, gp) in enumerate(ps.groupby("game_pk", sort=True)):
        if pk not in tgroups:
            continue
        tr = trades.iloc[tgroups[pk]]
        ts, px, dr, ct = tr.ts.to_numpy(), tr.home_cents.to_numpy(float), tr.dir.to_numpy(), tr.contracts.to_numpy(float)
        tape = build_tape(ts, px, dr, ct)
        gp = gp.sort_values("t_start")
        t0 = gp.t_start.to_numpy()
        t1 = gp.t_end.to_numpy(float)

        # ---- per-pitch event rows
        p_ref = mid_at(tape, t0 - REF_US, strict=True)
        age = last_order_age(tape, t0 - REF_US)
        F = fair_move(p_ref, gp.we_before.to_numpy(), gp.we_after.to_numpy())
        mids = np.stack([mid_at(tape, t0 + int(g * 1e6)) for g in GRID], axis=1) - p_ref[:, None]
        ot, od, olast, _, osize = orders(ts, px, dr, ct)
        half = np.full(len(t0), np.nan)
        half_size = np.full(len(t0), np.nan)            # contracts in the order that first traded past halfway
        half_aligned = np.zeros(len(t0), bool)          # was that order trading in the direction of the news?
        for i in np.flatnonzero(np.isfinite(F) & (np.abs(F) >= 1)):
            j0 = np.searchsorted(ot, t0[i], side="right")
            j1 = np.searchsorted(ot, t0[i] + 60_000_000, side="right")
            level = p_ref[i] + F[i] / 2
            hit = (olast[j0:j1] >= level) if F[i] > 0 else (olast[j0:j1] <= level)
            k = np.flatnonzero(hit)
            if len(k):
                half[i] = (ot[j0 + k[0]] - t0[i]) / 1e6
                half_size[i] = osize[j0 + k[0]]
                half_aligned[i] = od[j0 + k[0]] == np.sign(F[i])
        # how busy the market was: orders per second over the five minutes before the pitch
        activity = (np.searchsorted(ot, t0 - REF_US) - np.searchsorted(ot, t0 - 301_000_000)) / 300
        nxt = np.r_[t0[1:], np.nan]
        ev = pd.DataFrame({
            "game_pk": pk, "t0": t0, "feed_delay": (t1 - t0) / 1e6, "next_gap": (nxt - t0) / 1e6,
            "p_ref": p_ref, "age": age, "F": F, "half_time": half, "spread": tape.spread,
            "half_size": half_size, "half_aligned": half_aligned, "activity": activity,
            "game_order_median": float(np.median(osize)) if len(osize) else np.nan,
            "we_before": gp.we_before.to_numpy(), "we_after": gp.we_after.to_numpy(),
            "kind": classify(gp), "pa_event": gp.pa_event.to_numpy(), "inning": gp.inning.to_numpy(),
            "top": gp.top.to_numpy(), "outs": gp.outs_when_up.to_numpy(), "balls": gp.balls.to_numpy(),
            "strikes": gp.strikes.to_numpy(), "bases": gp.bases.to_numpy(), "clean": gp.clean.to_numpy(),
            "last_pitch": gp.last_pitch.to_numpy(), "in_play": gp.in_play.to_numpy(),
            "launch_speed": gp.launch_speed.to_numpy(float), "home_win": bool(games.at[pk, "home_win"]),
            "game_type": games.at[pk, "game_type"]})
        for g, col in zip(GRID, mids.T):
            ev[f"m{g:+g}"] = col.astype("float32")
        ev_rows.append(ev)

        # ---- markouts for every fill, by seconds since the last pitch and that pitch's news
        j = np.searchsorted(t0, ts, side="right") - 1
        in_game = (j >= 0) & (ts <= t0[-1] + 120_000_000)
        since = np.where(j >= 0, (ts - t0[np.maximum(j, 0)]) / 1e6, np.nan)
        newsF = np.where(j >= 0, F[np.maximum(j, 0)], np.nan)
        cols = {"since_bin": np.digitize(since, SINCE_BINS) - 1,
                "news_bin": np.digitize(np.abs(newsF), NEWS_BINS) - 1,
                "aligned": np.sign(dr) == np.sign(np.nan_to_num(newsF))}
        p = px / 100
        fee_t = TAKER_FEE * p * (1 - p) * ct * 100                   # in cents
        fee_m = MAKER_FEE * p * (1 - p) * ct * 100
        frame = {"contracts": ct, "fills": np.ones_like(ct), "fee_taker": fee_t, "fee_maker": fee_m}
        for h in HORIZONS:
            later = mid_at(tape, ts + h * 1_000_000)
            frame[f"maker_{h}"] = -dr * (later - px) * ct                # cents earned by the maker, per fill
        df = pd.DataFrame({**cols, **frame})[in_game & np.isfinite(newsF)]
        df = df[np.isfinite(df[[f"maker_{h}" for h in HORIZONS]]).all(1)]
        agg = df.groupby(["since_bin", "news_bin", "aligned"]).sum().reset_index()
        agg["game_pk"] = pk
        mk_rows.append(agg)

        # ---- the pulse: orders and contracts per second, by time since the last pitch and until the next
        gaps = np.diff(t0) / 1e6
        oj = np.searchsorted(t0, ot, side="right") - 1
        mid_game = (oj >= 0) & (oj < len(t0) - 1)
        since_o = (ot[mid_game] - t0[oj[mid_game]]) / 1e6
        until_o = (t0[oj[mid_game] + 1] - ot[mid_game]) / 1e6
        pulse_rows.append(pd.DataFrame({
            "game_pk": pk, "lo": PULSE_EDGES[:-1],
            "orders_since": np.histogram(since_o, PULSE_EDGES)[0],
            "contracts_since": np.histogram(since_o, PULSE_EDGES, weights=osize[mid_game])[0],
            "orders_until": np.histogram(until_o, PULSE_EDGES)[0],
            "contracts_until": np.histogram(until_o, PULSE_EDGES, weights=osize[mid_game])[0],
            "exposure": exposure(gaps, PULSE_EDGES)}))
        if (n + 1) % 250 == 0:
            print(f"  {n + 1} games", flush=True)

    events = pd.concat(ev_rows, ignore_index=True)
    events.to_parquet(out / "events.parquet", index=False)
    pd.concat(mk_rows, ignore_index=True).to_parquet(out / "markouts.parquet", index=False)
    pd.concat(pulse_rows, ignore_index=True).to_parquet(out / "pulse.parquet", index=False)
    print(f"{season}: {len(events):,} pitches in {events.game_pk.nunique()} games", flush=True)


if __name__ == "__main__":
    for s in map(int, sys.argv[1:]):
        run(s)
