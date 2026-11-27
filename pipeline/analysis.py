"""Every number in the write-up, with game-level bootstrap intervals. Writes data/out/results.json.

    python pipeline/analysis.py

Pitches enter the main sample if the market traded in the minute before the pitch, the pre-pitch price is between 2
and 98 cents, nothing outside the pitch changed the state before the next pitch, and the pitch did not end the game.
"Big" pitches moved fair value by at least 4 points. Intervals resample whole games (500 draws), because pitches in
the same game share a market.
"""
import json

import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import OUT, SEASONS
from events import GRID, NEWS_BINS, SINCE_BINS

RNG = np.random.default_rng(20260927)
B = 500
BIG = 4.0
COLS = [f"m{g:+g}" for g in GRID]
KINDS = ["Home run", "Hit", "Out in play", "Strikeout", "Walk or HBP"]


def usable(ev):
    return ev[(ev.age <= 60) & ev.p_ref.between(2, 98) & ev.clean & ev.F.notna() & ~ev.last_pitch].copy()


def game_sums(ev, cols=COLS):
    """Per-game sums for the response regression R(tau) = beta(tau) F (through the origin)."""
    F = ev.F.to_numpy()
    out = {"game_pk": ev.game_pk.to_numpy()}
    for c in cols:
        r = ev[c].to_numpy(float)
        ok = np.isfinite(r)
        out[f"rf_{c}"] = np.where(ok, r * F, 0.0)
        out[f"ff_{c}"] = np.where(ok, F * F, 0.0)
    return pd.DataFrame(out).groupby("game_pk").sum()


def beta_curve(sums, cols=COLS):
    rf = sums[[f"rf_{c}" for c in cols]].to_numpy()
    ff = sums[[f"ff_{c}" for c in cols]].to_numpy()
    est = rf.sum(0) / ff.sum(0)
    idx = RNG.integers(0, len(sums), size=(B, len(sums)))
    boots = np.stack([rf[i].sum(0) / ff[i].sum(0) for i in idx])
    lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
    return est, lo, hi, boots


def time_to(curve, frac, final):
    """First tau (interpolated, tau >= 0) where the curve reaches frac * final."""
    target = frac * final
    g = GRID
    for k in range(1, len(g)):
        if g[k] > 0 and curve[k - 1] < target <= curve[k]:
            return float(g[k - 1] + (target - curve[k - 1]) / (curve[k] - curve[k - 1]) * (g[k] - g[k - 1]))
    return float("nan")


def boot_stat(df, fn, by="game_pk"):
    """Point estimate and 95% interval of fn(df) resampling games."""
    groups = df.groupby(by).indices
    keys = np.array(list(groups))
    est = fn(df)
    draws = []
    for _ in range(B):
        pick = RNG.choice(keys, size=len(keys))
        draws.append(fn(df.iloc[np.concatenate([groups[k] for k in pick])]))
    lo, hi = np.nanpercentile(draws, [2.5, 97.5])
    return {"est": float(est), "lo": float(lo), "hi": float(hi)}


def clustered_slope(y, x, groups):
    m = sm.OLS(y, sm.add_constant(x)).fit(cov_type="cluster", cov_kwds={"groups": groups})
    return {"slope": float(m.params[1]), "se": float(m.bse[1]), "intercept": float(m.params[0]), "n": int(len(y))}


def speed(ev, big):
    s_all, s_big = game_sums(ev), game_sums(big)
    e_all, lo_all, hi_all, boots_all = beta_curve(s_all)
    e_big, lo_big, hi_big, boots_big = beta_curve(s_big)
    k60 = list(GRID).index(60)
    t50 = [time_to(b, 0.5, b[k60]) for b in boots_all]
    t90 = [time_to(b, 0.9, b[k60]) for b in boots_all]
    ht = big.half_time
    by_kind = {}
    for k in KINDS:
        d = big[big.kind == k]
        if len(d) < 20:
            continue
        sk = game_sums(d)
        ek = sk[[f"rf_{c}" for c in COLS]].sum().to_numpy() / sk[[f"ff_{c}" for c in COLS]].sum().to_numpy()
        by_kind[k] = {"n": int(len(d)), "median_F": float(d.F.abs().median()),
                      "half_median": float(d.half_time.median()), "half_q25": float(d.half_time.quantile(.25)),
                      "half_q75": float(d.half_time.quantile(.75)), "feed_median": float(d.feed_delay.median()),
                      "ahead_of_feed": float((d.half_time < d.feed_delay).mean()),
                      "beta60": float(ek[k60]), "curve": [round(float(v), 4) for v in ek]}
    return {
        "grid": GRID.tolist(),
        "beta_all": {"est": e_all.round(4).tolist(), "lo": lo_all.round(4).tolist(), "hi": hi_all.round(4).tolist()},
        "beta_big": {"est": e_big.round(4).tolist(), "lo": lo_big.round(4).tolist(), "hi": hi_big.round(4).tolist()},
        "t50": {"est": time_to(e_all, .5, e_all[k60]), "lo": float(np.nanpercentile(t50, 2.5)),
                "hi": float(np.nanpercentile(t50, 97.5))},
        "t90": {"est": time_to(e_all, .9, e_all[k60]), "lo": float(np.nanpercentile(t90, 2.5)),
                "hi": float(np.nanpercentile(t90, 97.5))},
        "beta_at": {f"{g:g}": {"est": float(e_all[i]), "lo": float(lo_all[i]), "hi": float(hi_all[i])}
                    for i, g in enumerate(GRID) if g in (-5, 0, 0.5, 1, 2, 5, 10, 30, 60)},
        "half_time": {"n": int(ht.notna().sum()), "median": float(ht.median()), "q25": float(ht.quantile(.25)),
                      "q75": float(ht.quantile(.75)), "within_1s": float((ht < 1).mean()),
                      "within_2s": float((ht < 2).mean()), "within_5s": float((ht < 5).mean()),
                      "never_60s": float(ht.isna().mean()),
                      "hist": np.histogram(ht.dropna().clip(upper=29.99), np.arange(0, 30.5, 0.5))[0].tolist()},
        "half_median_ci": boot_stat(big, lambda d: d.half_time.median()),
        "ahead_of_feed": boot_stat(big, lambda d: (d.half_time < d.feed_delay).mean()),
        "feed_delay_median": float(big.feed_delay.median()),
        "by_kind": by_kind,
    }


def accuracy(ev, big):
    """Is anything about the pitch left to price after the first 30 seconds? Regress what happens next on the fair
    move F, which everyone knew at the time. Under efficiency the slope is zero. (Regressing on the residual F - R(30)
    instead would manufacture a positive slope, because noise in the 30-second price reverses.)"""
    k60 = "m+60"
    out = {}
    for name, d in (("all", ev), ("big", big)):
        d = d[d["m+30"].notna() & d["m+120"].notna()]
        drift = d["m+120"] - d["m+30"]
        out[f"drift_{name}"] = clustered_slope(drift.to_numpy(), d.F.to_numpy(), d.game_pk.to_numpy())
        y = 100 * d.home_win.astype(float) - (d.p_ref + d["m+30"])
        out[f"outcome_{name}"] = clustered_slope(y.to_numpy(), d.F.to_numpy(), d.game_pk.to_numpy())
    out["beta60_big"] = boot_stat(big[big[k60].notna()], lambda d: float((d[k60] * d.F).sum() / (d.F ** 2).sum()))
    # calibration of the pre-pitch price against the final result, and its Brier score against Savant's average-team WE
    d = ev[["game_pk", "p_ref", "we_before", "home_win"]].dropna()
    y = d.home_win.astype(float).to_numpy()
    bins = np.arange(0, 101, 10)
    cal = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (d.p_ref >= lo) & (d.p_ref < hi)
        if m.sum() > 200:
            cal.append({"lo": int(lo), "hi": int(hi), "n": int(m.sum()), "price": float(d.p_ref[m].mean()),
                        "won": float(y[m].mean()),
                        "ci": [float(v) for v in boot_cal(d[m])]})
    out["calibration"] = cal
    out["brier_market"] = float(np.mean((d.p_ref / 100 - y) ** 2))
    out["brier_average_team"] = float(np.mean((d.we_before - y) ** 2))
    return out


def boot_cal(d):
    g = d.groupby("game_pk").home_win.agg(["sum", "count"])
    idx = RNG.integers(0, len(g), size=(B, len(g)))
    s, n = g["sum"].to_numpy(float), g["count"].to_numpy(float)
    rates = s[idx].sum(1) / n[idx].sum(1)
    return np.percentile(rates, [2.5, 97.5])


def speed_tax(mk, n_games):
    """Maker P&L (cents) by seconds since the last pitch, and the share of it handed to traders who react first."""
    mk = mk.copy()
    mk["fast"] = mk.since_bin <= np.searchsorted(SINCE_BINS, 5) - 1          # fills within 5 s of a pitch
    mk["news"] = mk.news_bin >= np.searchsorted(NEWS_BINS, 2)                # pitch moved fair value 2+ points
    by_since = mk.groupby("since_bin")[["contracts", "maker_60", "maker_5"]].sum()
    curve = [{"lo": float(SINCE_BINS[i]), "hi": float(SINCE_BINS[i + 1]), "share": float(r.contracts /
              by_since.contracts.sum()), "maker_c": float(r.maker_60 / r.contracts)} for i, r in by_since.iterrows()]
    tot = mk[["contracts", "maker_60", "fee_taker", "fee_maker"]].sum()
    hit = mk[mk.fast & mk.news]
    quiet = mk[~(mk.fast & mk.news)]
    snipe = hit[hit.aligned]
    per_game = mk.groupby(["game_pk"]).apply(lambda g: pd.Series({
        "after_news": g.loc[g.fast & g.news, "maker_60"].sum(), "rest": g.loc[~(g.fast & g.news), "maker_60"].sum(),
        "contracts": g.contracts.sum()}), include_groups=False)
    return {
        "curve": curve,
        "maker_c_per_contract": float(tot.maker_60 / tot.contracts),
        "taker_fee_c": float(tot.fee_taker / tot.contracts), "maker_fee_c": float(tot.fee_maker / tot.contracts),
        "after_news_share_contracts": float(hit.contracts.sum() / tot.contracts),
        "after_news_maker_c": float(hit.maker_60.sum() / hit.contracts.sum()),
        "rest_maker_c": float(quiet.maker_60.sum() / quiet.contracts.sum()),
        "rest_dollars_per_game": float(quiet.maker_60.sum() / 100 / n_games),
        "after_news_dollars_per_game": float(hit.maker_60.sum() / 100 / n_games),
        "given_back": float(-hit.maker_60.sum() / quiet.maker_60.sum()),
        "given_back_ci": [float(v) for v in np.percentile(
            [(-per_game.after_news.iloc[i].sum() / per_game.rest.iloc[i].sum())
             for i in RNG.integers(0, len(per_game), size=(B, len(per_game)))], [2.5, 97.5])],
        "snipe_share_contracts": float(snipe.contracts.sum() / tot.contracts),
        "snipe_taker_c": float(-snipe.maker_60.sum() / snipe.contracts.sum()),
        "snipe_taker_fee_c": float(snipe.fee_taker.sum() / snipe.contracts.sum()),
        # when, within those five seconds, the makers' losses happen: share lost by the end of each second-bin
        "loss_by": {f"{SINCE_BINS[b + 1]:g}": float(hit[hit.since_bin <= b].maker_60.sum() / hit.maker_60.sum())
                    for b in sorted(hit.since_bin.unique())},
        "after_news_dollars_total": float(hit.maker_60.sum() / 100),
        "rest_dollars_total": float(quiet.maker_60.sum() / 100),
        # the same split at Kalshi's full standard fee (no 0.5 multiplier), to show nothing hinges on the fee
        "snipe_taker_fee_c_full_rate": float(2 * snipe.fee_taker.sum() / snipe.contracts.sum()),
    }


def who_and_when(big):
    """Who trades first, and whether the market is faster when it is busier or the game matters more."""
    d = big[big.half_time.notna()]
    terc = pd.qcut(d.activity.rank(method="first"), 3, labels=["quietest", "middle", "busiest"])
    by_act = {str(k): {"n": int(len(g)), "half_median": float(g.half_time.median()),
                       "orders_per_s": float(g.activity.median())} for k, g in d.groupby(terc, observed=True)}
    post = d.game_type != "R"
    return {
        "first_size_median": float(d.half_size.median()),
        "order_size_median": float(d.drop_duplicates("game_pk").game_order_median.median()),
        "first_aligned": float(d.half_aligned.mean()),
        "first_size_1000": float((d.half_size >= 1000).mean()),
        "by_activity": by_act,
        "regular_half_median": float(d[~post].half_time.median()), "regular_n": int((~post).sum()),
        "post_half_median": float(d[post].half_time.median()) if post.any() else None, "post_n": int(post.sum()),
    }


def pulse(p):
    s = p.groupby("lo")[["orders_since", "orders_until", "contracts_since", "contracts_until", "exposure"]].sum()
    keep = s.index < 30
    base = s.orders_since[(s.index >= 10) & (s.index < 15)].sum() / s.exposure[(s.index >= 10) & (s.index < 15)].sum()
    return {"lo": s.index[keep].tolist(),
            "since": (s.orders_since / s.exposure)[keep].round(4).tolist(),
            "until": (s.orders_until / s.exposure)[keep].round(4).tolist(),
            "since_contracts": (s.contracts_since / s.exposure)[keep].round(2).tolist(),
            "until_contracts": (s.contracts_until / s.exposure)[keep].round(2).tolist(),
            "baseline": float(base)}


def placebo(ev):
    """A fake pitch ten seconds early: does the price drift toward the coming news before the pitch? (should be 0)"""
    d = ev[ev["m-10"].notna() & ev["m-5"].notna()]
    r = (d["m-5"] - d["m-10"]).to_numpy()
    F = d.F.to_numpy()
    g = d.game_pk.to_numpy()
    est = float((r * F).sum() / (F * F).sum())
    sums = pd.DataFrame({"g": g, "rf": r * F, "ff": F * F}).groupby("g").sum().to_numpy()
    idx = RNG.integers(0, len(sums), size=(B, len(sums)))
    b = sums[idx, 0].sum(1) / sums[idx, 1].sum(1)
    return {"est": est, "lo": float(np.percentile(b, 2.5)), "hi": float(np.percentile(b, 97.5))}


BAND = (1.0, 2.0)          # orders a second in the five minutes before a pitch: "equally busy" across months


def monthly(ev, big):
    """Median time to halfway by month, for every big pitch and for big pitches in equally busy markets only, so a
    speed-up can be told apart from a market that simply got busier."""
    big = big.assign(month=pd.to_datetime(big.t0, unit="us", utc=True).dt.strftime("%Y-%m"))
    rows = []
    for mth, d in big.groupby("month"):
        if len(d) < 50:
            continue
        band = d[d.activity.between(*BAND)]
        rows.append({"month": mth, "n": int(len(d)), "half_median": float(d.half_time.median()),
                     "within_2s": float((d.half_time < 2).mean()), "activity": float(d.activity.median()),
                     "band_n": int(len(band)), "band_half_median": float(band.half_time.median()) if len(band) >= 50
                     else None})
    return rows


def pulse_big(pb):
    s = pb.groupby("lo").orders.sum()
    n = pb.drop_duplicates("game_pk").n_big.sum()
    rate = s / (n * 0.25)                     # orders per second around one big pitch
    before = rate[(rate.index >= -10) & (rate.index < -5)].mean()
    return {"lo": rate.index.tolist(), "rate": rate.round(4).tolist(), "n_big": int(n), "before": float(before),
            "peak": float(rate[rate.index >= 0].max()), "peak_t": float(rate[rate.index >= 0].idxmax() + 0.125),
            "last_before": float(rate[(rate.index >= -1) & (rate.index < 0)].mean())}


def clean(o):
    """JSON has no NaN or infinity: write them as null."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def main():
    res = {}
    for season in SEASONS:
        f = OUT / str(season) / "events.parquet"
        if not f.exists():
            continue
        ev_raw = pd.read_parquet(f)
        ev = usable(ev_raw)
        big = ev[ev.F.abs() >= BIG]
        mk = pd.read_parquet(OUT / str(season) / "markouts.parquet")
        res[str(season)] = {
            "games": int(ev_raw.game_pk.nunique()), "pitches": int(len(ev_raw)), "usable": int(len(ev)),
            "big": int(len(big)),
            "speed": speed(ev, big), "accuracy": accuracy(ev, big),
            "speed_tax": speed_tax(mk, ev_raw.game_pk.nunique()),
            "pulse": pulse(pd.read_parquet(OUT / str(season) / "pulse.parquet")),
            "pulse_big": pulse_big(pd.read_parquet(OUT / str(season) / "pulse_big.parquet")),
            "placebo": placebo(ev), "monthly": monthly(ev, big), "who": who_and_when(big)}
        print(f"{season}: {res[str(season)]['games']} games, {len(ev):,} usable pitches, {len(big):,} big", flush=True)
    (OUT / "results.json").write_text(json.dumps(clean(res), indent=1, allow_nan=False))


if __name__ == "__main__":
    main()
