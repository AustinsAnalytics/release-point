"""A simulated market with known answers, to check that the estimators measure what they claim to.

    python pipeline/simulate.py          # writes data/out/simulation.json

Each simulated game has a fair value that jumps when news becomes known (0.6 s after each pitch). Market makers quote a
one-cent spread around their belief and update it after a random delay with a known distribution. Noise traders arrive
at random and trade at the quotes. After a big jump, fast traders hit the stale quotes until the makers update.
The script runs the same estimators used on the real tape (tape.py and the response regression) and compares:
  - the half-adjustment time against the true repricing time
  - the trade-implied response curve against the true quote midpoint
  - the makers' measured 60-second markouts against what they truly lost and earned
"""
import json

import numpy as np
import pandas as pd

from common import OUT
from events import GRID, fair_move
from tape import build_tape, mid_at, orders

INFO = 0.6            # seconds from the pitch until its outcome is knowable


def simulate_game(rng, n_pitches=280, maker_mean=2.0, noise_rate=1.0, snipe_rate=6.0):
    gaps = rng.gamma(9, 2.4, n_pitches)                           # ~21.6 s between pitches, like the real game
    t_pitch = np.cumsum(gaps) + 60
    jumps = np.where(rng.random(n_pitches) < 0.08, rng.choice([-1, 1], n_pitches) * rng.uniform(4, 12, n_pitches),
                     rng.normal(0, 0.6, n_pitches))
    v = np.empty(n_pitches + 1)
    v[0] = rng.uniform(35, 65)
    for i, j in enumerate(jumps):                                 # keep the game away from 0 and 100
        v[i + 1] = np.clip(v[i] + j, 6, 94)
    jumps = np.diff(v)
    t_known = t_pitch + INFO
    t_reprice = t_known + rng.exponential(maker_mean, n_pitches)  # when makers move their quotes to the new value
    end = t_pitch[-1] + 120

    def belief(t):                                                # makers' midpoint
        k = np.searchsorted(t_reprice, t, side="right")
        return v[k]

    def truth(t):
        k = np.searchsorted(t_known, t, side="right")
        return v[k]

    fills = []
    # noise traders: Poisson arrivals at the makers' quotes, random side. Activity triples for ten seconds after a big
    # jump, as on the real tape (about 1.4 orders a second before a big pitch, 3 to 4.5 a second in the seconds after).
    big_known = t_known[np.abs(jumps) >= 2]
    peak = 3.0 * noise_rate
    tn = np.cumsum(rng.exponential(1 / peak, int(end * peak * 1.3)))
    tn = tn[tn < end]
    k = np.searchsorted(big_known, tn, side="right") - 1
    surge = (k >= 0) & (tn - big_known[np.maximum(k, 0)] < 10)
    tn = tn[surge | (rng.random(len(tn)) < noise_rate / peak)]           # thin back to the base rate outside surges
    for t, d in zip(tn, rng.choice([-1, 1], len(tn))):
        q = belief(t)
        bid = np.floor(q - 0.5)
        fills.append((t, bid + 1 if d > 0 else bid, d, rng.lognormal(3.5, 1.2)))
    # fast traders: after a big jump, hit the stale side repeatedly until the makers reprice
    for i in np.flatnonzero(np.abs(jumps) >= 2):
        t = t_known[i] + rng.exponential(0.3)
        while t < t_reprice[i]:
            q = belief(t)
            bid = np.floor(q - 0.5)
            d = 1 if jumps[i] > 0 else -1
            fills.append((t, bid + 1 if d > 0 else bid, d, rng.lognormal(5, 1)))
            t += rng.exponential(1 / snipe_rate)
    f = pd.DataFrame(fills, columns=["t", "px", "dir", "contracts"]).sort_values("t")
    f["ts"] = (f.t * 1e6).astype("int64")
    p = pd.DataFrame({"t0": (t_pitch * 1e6).astype("int64"), "v_before": v[:-1], "v_after": v[1:],
                      "jump": jumps, "reprice": t_reprice - t_pitch})
    return f, p, truth, belief


def run(n_games=400, seed=7):
    rng = np.random.default_rng(seed)
    halves, true_rep, rows, mk_est, mk_true = [], [], [], [], []
    curves_est, curves_true, Fs = [], [], []
    for _ in range(n_games):
        f, p, truth, belief = simulate_game(rng)
        tape = build_tape(f.ts.to_numpy(), f.px.to_numpy(), f.dir.to_numpy(), f.contracts.to_numpy())
        t0 = p.t0.to_numpy()
        p_ref = mid_at(tape, t0 - 1_000_000, strict=True)
        F = fair_move(p_ref, p.v_before.to_numpy() / 100, p.v_after.to_numpy() / 100)
        ok = np.isfinite(F)
        est = np.stack([mid_at(tape, t0 + int(g * 1e6)) for g in GRID], 1) - p_ref[:, None]
        tru = np.stack([belief((t0 + g * 1e6) / 1e6) for g in GRID], 1) - belief((t0 - 1e6) / 1e6)[:, None]
        curves_est.append(est[ok]); curves_true.append(tru[ok]); Fs.append(F[ok])
        ot, od, olast, _, _ = orders(f.ts.to_numpy(), f.px.to_numpy(), f.dir.to_numpy(), f.contracts.to_numpy())
        for i in np.flatnonzero(ok & (np.abs(F) >= 4)):
            j0 = np.searchsorted(ot, t0[i], side="right")
            level = p_ref[i] + F[i] / 2
            seg = olast[j0:j0 + 400]
            hit = np.flatnonzero(seg >= level) if F[i] > 0 else np.flatnonzero(seg <= level)
            if len(hit):
                halves.append((ot[j0 + hit[0]] - t0[i]) / 1e6)
                true_rep.append(p.reprice.iloc[i])
        # maker markouts at 60 s: measured with the trade-implied mid vs. with the true value
        later_est = mid_at(tape, f.ts.to_numpy() + 60_000_000)
        later_true = truth(f.t.to_numpy() + 60)
        ok_f = np.isfinite(later_est)
        mk_est.append((-f.dir.to_numpy() * (later_est - f.px.to_numpy()) * f.contracts.to_numpy())[ok_f].sum())
        mk_true.append((-f.dir.to_numpy() * (later_true - f.px.to_numpy()) * f.contracts.to_numpy())[ok_f].sum())
    est, tru, F = np.concatenate(curves_est), np.concatenate(curves_true), np.concatenate(Fs)

    def beta(r):
        m = np.isfinite(r)
        return np.array([(r[:, k][m[:, k]] * F[m[:, k]]).sum() / (F[m[:, k]] ** 2).sum() for k in range(len(GRID))])

    b_est, b_true = beta(est), beta(tru)
    halves, true_rep = np.array(halves), np.array(true_rep)
    out = {
        "games": n_games, "big_events": int(len(halves)),
        "true_reprice_median": float(np.median(true_rep + 0)), "est_half_median": float(np.median(halves)),
        "half_minus_true_median": float(np.median(halves - true_rep)),
        "half_after_true_share": float(np.mean(halves >= true_rep - 1e-9)),
        "curve_grid": GRID.tolist(), "beta_est": b_est.round(4).tolist(), "beta_true": b_true.round(4).tolist(),
        "curve_max_gap": float(np.nanmax(np.abs(b_est - b_true))),
        "markout_est": float(np.sum(mk_est)), "markout_true": float(np.sum(mk_true)),
        "markout_ratio": float(np.sum(mk_est) / np.sum(mk_true)),
    }
    return out


if __name__ == "__main__":
    res = run()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "simulation.json").write_text(json.dumps(res, indent=1))
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.items() if not isinstance(v, list)})
