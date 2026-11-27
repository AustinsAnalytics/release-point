"""Fill templates/index.html with numbers from the pipeline's outputs -> site/index.html. Nothing on the page is typed.

    python pipeline/story.py

Refuses to write the page if any {{placeholder}} is left without a value.
"""
import json
import os
import re
from datetime import date

import pandas as pd

from common import DATA, OUT, ROOT

SITE = ROOT / "site"
REPO = "https://github.com/AustinsAnalytics/release-point"
ORD = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth",
       9: "ninth", 10: "10th", 11: "11th", 12: "12th", 13: "13th"}


def pct(x, d=0):
    s = f"{100 * abs(x):.{d}f}%"
    return ("−" + s) if x < 0 and float(s[:-1]) != 0 else s


def drift_text(acc, med_F, cost_c):
    """Say what is left to price after 30 seconds, in words that match the test's verdict."""
    b, se = acc["drift_big"]["slope"], acc["drift_big"]["se"]
    cents = abs(b) * med_F
    if abs(b) > 2 * se:
        long = (f"Almost nothing about the pitch is left to price after half a minute. The last few percent take "
                f"longer: from thirty seconds to two minutes after a big pitch the price "
                f"moves {'another' if b > 0 else 'back'} {pct(abs(b), 1)} of the fair move (standard error "
                f"{pct(se, 1)}, clustered by game), about {cents:.2f}&cent; on a typical big pitch, "
                f"{'less' if cents < cost_c else 'more'} than the {cost_c:.1f}&cent; it costs to trade once.")
        short = (f"the next 90 s add {pct(b, 1)} of the fair move (SE {pct(se, 1)}), about {cents:.2f}&cent;, "
                 f"{'under' if cents < cost_c else 'over'} the cost of one trade")
    else:
        long = (f"Nothing about the pitch is left to price after half a minute. From thirty seconds to two minutes "
                f"after a big pitch the price moves {pct(b, 1)} of the fair move "
                f"(standard error {pct(se, 1)}, clustered by game), zero within the noise.")
        short = f"the next 90 s add {pct(b, 1)} of the fair move (SE {pct(se, 1)}), zero within the noise"
    return long, short


def outcome_text(acc, med_F, cost_c):
    """How each game ended, regressed on the fair move (known at the time) after the price thirty seconds later."""
    b, se = acc["outcome_big"]["slope"], acc["outcome_big"]["se"]
    if abs(b) > 2 * se:
        cents = abs(b) * med_F
        again = "again " if cents < cost_c else ""
        return (f"The final scores say the same. Judged against how each game ended, the price thirty seconds after a "
                f"big pitch had {'left' if b > 0 else 'overshot by'} about {pct(abs(b))} of the fair move"
                f"{' unpriced' if b > 0 else ''} (standard error {100 * se:.1f} percentage points, clustered by game), "
                f"{cents:.2f}&cent; on a typical big pitch, {again}{'less' if cents < cost_c else 'more'} than the cost "
                f"of a trade.")
    return (f"The final scores agree: judged against how each game ended, the price thirty seconds after a big pitch "
            f"had left {pct(b)} of the fair move unpriced (standard error {100 * se:.1f} percentage points, clustered by game), "
            f"zero within the noise.")


def calibration_text(cal):
    b = min(cal, key=lambda r: abs((r["lo"] + r["hi"]) / 2 - 75))
    return (f"Teams the market priced between {b['lo']} and {b['hi']} cents before a pitch ({b['price']:.0f} on "
            f"average) went on to win {pct(b['won'], 1)} of the time (95% interval {pct(b['ci'][0], 1)}&ndash;"
            f"{pct(b['ci'][1], 1)}; Fig. 5)")


def millions(n):
    if n >= 1e9:
        return f"{n / 1e9:.1f} billion"
    if n >= 1e6:
        return f"{n / 1e6:.1f} million"
    return f"{n:,.0f}"


def signed(x, d=2):
    return ("−" if x < 0 else "") + f"{abs(x):.{d}f}"


def s1(x):
    return f"{x:.1f}"


def nice_date(s):
    d = date.fromisoformat(s)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def kinds_sentence(k):
    hr, so, bb, hit, out = (k.get(x) for x in ("Home run", "Strikeout", "Walk or HBP", "Hit", "Out in play"))
    parts = []
    fastest = min(k, key=lambda x: k[x]["half_median"])
    if hr:
        lead = "Home runs are priced fastest" if fastest == "Home run" else "Home runs are priced quickly"
        parts.append(f"{lead}, a median {s1(hr['half_median'])} seconds after the pitch, while MLB&rsquo;s feed does "
                     f"not mark the play final until {s1(hr['feed_median'])} seconds after it.")
    if so and bb:
        parts.append(f"Strikeouts and walks are decided the moment the pitch arrives, and the market is past halfway "
                     f"in {s1(so['half_median'])} and {s1(bb['half_median'])} seconds, against the feed&rsquo;s "
                     f"{s1(so['feed_median'])} and {s1(bb['feed_median'])}.")
    if hit and out:
        slow = "Outs in play take longest" if out["half_median"] >= max(v["half_median"] for v in k.values()) \
            else "Outs in play are slower"
        parts.append(f"{slow}, a median {s1(out['half_median'])} seconds, because the ball has to be caught or thrown "
                     f"before the play is over. Hits take {s1(hit['half_median'])}.")
    return " ".join(parts)


def jump_word(r):
    """How much the order rate rises after a big pitch, in words."""
    if 1.75 <= r < 2.25:
        return "doubles,"
    if 2.75 <= r < 3.25:
        return "triples,"
    return f"rises {r:.1f}-fold,"


def after_rate(pb):
    """Orders a second, per game, from ten to twenty seconds after a big pitch."""
    v = [r for lo, r in zip(pb["lo"], pb["rate"]) if 10 <= lo < 20]
    return sum(v) / len(v)


def month_name(m):
    return date.fromisoformat(m + "-01").strftime("%B")


def is_post(m):
    return m["month"].endswith("post")


def hundreds(x):
    return f"{round(x, -2):,.0f}"


def seasons_paragraph(r25, r26, m25, m26, first_day):
    """Two paragraphs on how the market changed, worded from the direction of each comparison."""
    tpg25, tpg26 = m25["trades"] / m25["games_traded"], m26["trades"] / m26["games_traded"]
    t25, t26 = r25["speed"]["t50"]["est"], r26["speed"]["t50"]["est"]
    h25, h26 = r25["speed"]["half_time"]["median"], r26["speed"]["half_time"]["median"]
    a25, a26 = r25["speed"]["ahead_of_feed"]["est"], r26["speed"]["ahead_of_feed"]["est"]
    c25, c26 = r25["speed_tax"]["rest_maker_c"], r26["speed_tax"]["rest_maker_c"]
    g25, g26 = r25["speed_tax"]["given_back"], r26["speed_tax"]["given_back"]
    p1 = (f"These markets are young. Kalshi&rsquo;s archive of MLB game markets begins on {nice_date(first_day)}, and "
          f"in that first season a game drew about {hundreds(tpg25)} trades while it was played; in 2026, about "
          f"{hundreds(tpg26)}. ")
    if h26 < h25:
        p1 += (f"Along with the volume came speed. The whole response moved earlier, halfway to the fair move "
               f"{s1(t25)} seconds after the pitch in 2025 and {s1(t26)} in 2026 (Fig. 8). The median time from a big "
               f"pitch to the first trade past halfway fell from {s1(h25)} seconds to {s1(h26)}, and the share of big "
               f"pitches priced before MLB&rsquo;s feed had the result rose from {pct(a25)} to {pct(a26)}.")
    else:
        p1 += (f"The speed did not follow: the median time from a big pitch to the first trade past halfway was "
               f"{s1(h25)} seconds in 2025 and {s1(h26)} in 2026, and the response curves are alike (Fig. 8).")
    mo = r26["monthly"]
    reg = [m for m in mo if not is_post(m)]
    post = [m for m in mo if is_post(m)]
    first, last = reg[0], reg[-1]
    p2 = ""
    if last["half_median"] < first["half_median"]:
        p2 = (f"Within 2026 it kept getting faster, from {s1(first['half_median'])} seconds in "
              f"{month_name(first['month'])} to {s1(last['half_median'])} in {month_name(last['month'])}"
              + (f" and {s1(post[0]['half_median'])} in the postseason" if post else "") + ". ")
        band = [m for m in reg if m["band_half_median"] is not None]
        if len(band) >= 2 and band[-1]["band_half_median"] < band[0]["band_half_median"]:
            p2 += (f"That is not only because the markets got busier: in markets that were equally busy before the pitch "
                   f"(one to two orders a second), it fell from {s1(band[0]['band_half_median'])} seconds in "
                   f"{month_name(band[0]['month'])} to {s1(band[-1]['band_half_median'])} in "
                   f"{month_name(band[-1]['month'])} (Fig. 9). ")
    # the share of makers' ordinary profit lost after news, for windows of 2, 5 and 15 seconds after the pitch
    w25, w26 = r25["speed_tax"]["given_back_by_window"], r26["speed_tax"]["given_back_by_window"]
    p2 += (f"Market makers felt it. On ordinary trades they earned {c25:.2f}&cent; a contract in 2025 and "
           f"{c26:.2f}&cent; in 2026. ")
    if abs(w26["15"] - w25["15"]) < 0.05 and w26["2"] - w25["2"] > 0.1:
        p2 += (f"Of that profit, the share lost within two seconds of a pitch that moved fair value two points or more "
               f"went from {pct(w25['2'])} to {pct(w26['2'])}, and within five seconds from {pct(g25)} to {pct(g26)}. "
               f"Over fifteen seconds it was about the same, {pct(w25['15'])} and {pct(w26['15'])}. The faster market "
               f"did not take a much bigger share from a stale quote; it took it sooner.")
    elif w26["15"] > w25["15"] and g26 > g25:
        p2 += (f"The share of that profit they handed to faster traders after news rose, from {pct(g25)} to {pct(g26)} "
               f"within five seconds of the pitch and from {pct(w25['15'])} to {pct(w26['15'])} within fifteen.")
    else:
        p2 += (f"They handed {pct(g25)} and {pct(g26)} of that profit to faster traders within five seconds of news, "
               f"and {pct(w25['15'])} and {pct(w26['15'])} within fifteen.")
    return p1 + "</p>\n    <p>" + p2.strip()


def build():
    res = json.loads((OUT / "results.json").read_text())
    sim = json.loads((OUT / "simulation.json").read_text())
    site = json.loads((SITE / "data" / "release.json").read_text())
    r26, r25 = res["2026"], res.get("2025")
    m26, m25 = site["seasons"]["2026"]["meta"], site["seasons"].get("2025", {}).get("meta")
    sp, acc, tax = r26["speed"], r26["accuracy"], r26["speed_tax"]
    k = sp["by_kind"]
    h = site["hero"]

    p = pd.read_parquet(DATA / "interim" / "2026" / "pitches.parquet", columns=["game_pk", "t_start", "t_end", "in_play"])
    delay = (p.t_end - p.t_start) / 1e6
    gap_median = (p.sort_values(["game_pk", "t_start"]).groupby("game_pk").t_start.diff() / 1e6).median()
    mk26 = pd.read_parquet(DATA / "interim" / "2026" / "markets.parquet")
    mk25 = pd.read_parquet(DATA / "interim" / "2025" / "markets.parquet") if r25 else None
    first_day = None
    if mk25 is not None:
        g25 = pd.read_parquet(DATA / "interim" / "2025" / "games.parquet", columns=["game_pk", "official_date"])
        first_day = g25[g25.game_pk.isin(mk25.game_pk)].official_date.min()
    n_tests = sum(len(re.findall(r"^def test_", f.read_text(), re.M)) for f in (ROOT / "tests").glob("test_*.py"))

    fair_after = h["p_ref"] + h["F"]
    team = h["batting_team"]
    half_inn = "top" if h["top"] else "bottom"
    stage = {"R": "", "F": " in the Wild Card Series", "D": " in the Division Series", "L": " in the League Championship Series",
             "W": " in the World Series"}[h["game_type"]]
    pulse = r26["pulse"]
    lo = pulse["lo"]
    def sim_pct(x):
        d = 100 * abs(x - 1)
        return f"{d:.1f}%" if d >= 0.1 else f"{max(d, 0.01):.2f}%"

    reg_months = [m for m in r26["monthly"] if not is_post(m)]
    band_months = [m for m in reg_months if m["band_half_median"] is not None]
    who = r26["who"]
    act = who["by_activity"]
    post_sentence = ""
    if who["post_half_median"] is not None and who["post_n"] >= 50:
        faster = who["post_half_median"] < who["regular_half_median"]
        post_sentence = (f" Postseason games, the busiest markets of all, were {'faster still' if faster else 'no faster'}: "
                         f"{s1(who['post_half_median'])} seconds over {who['post_n']:,} big pitches, against "
                         f"{s1(who['regular_half_median'])} in the regular season.")

    def dollars(x):
        return f"{x / 1e6:.1f} million" if abs(x) >= 1e6 else f"{x:,.0f}"

    ev26 = pd.read_parquet(OUT / "2026" / "events.parquet", columns=["F", "spread", "age", "p_ref", "clean", "last_pitch"])
    big_F = ev26[(ev26.F.abs() >= 4) & (ev26.age <= 60) & ev26.p_ref.between(2, 98) & ev26.clean & ~ev26.last_pitch].F
    cost = ev26.spread.median() / 2 + tax["taker_fee_c"]           # half the typical spread plus the taker fee
    drift_long, drift_short = drift_text(acc, float(big_F.abs().median()), float(cost))

    v = {
        "loss_15": pct(tax["loss_by"]["1.5"]), "loss_3": pct(tax["loss_by"]["3"]),
        "speedup": f"{r25['speed']['half_time']['median'] / sp['half_time']['median']:.1f}".rstrip("0").rstrip(".")
        if r25 else "", "h25": s1(r25["speed"]["half_time"]["median"]) if r25 else "",
        "a25": pct(r25["speed"]["ahead_of_feed"]["est"]) if r25 else "",
        "mar_half": s1(reg_months[0]["half_median"]), "sep_half": s1(reg_months[-1]["half_median"]),
        "band_first": s1(band_months[0]["band_half_median"]), "band_last": s1(band_months[-1]["band_half_median"]),
        "drift_sentence": drift_long, "drift_short": drift_short, "outcome_sentence": outcome_text(acc, float(big_F.abs().median()), float(cost)),
        "cal_sentence": calibration_text(acc["calibration"]),
        "beta60_word": ("slightly more" if acc["beta60_big"]["lo"] > 1 else "slightly less" if acc["beta60_big"]["hi"] < 1
                        else "not different from one"),
        "gap_median": s1(float(gap_median)),
        "first_size": f"{who['first_size_median']:,.0f}",
        "first_ratio": f"{who['first_ratio_median']:.1f}",
        "first_aligned": pct(who["first_aligned"]), "first_1000": pct(who["first_size_1000"]),
        "act_hi": s1(act["busiest"]["half_median"]), "act_lo": s1(act["quietest"]["half_median"]),
        "act_hi_rate": f"{act['busiest']['orders_per_s']:.1f}", "act_lo_rate": f"{act['quietest']['orders_per_s']:.1f}",
        "post_sentence": post_sentence or " ",
        "tax_total": dollars(-tax["after_news_dollars_total"]), "rest_total": dollars(tax["rest_dollars_total"]),
        "repo": REPO,
        "trades26": millions(m26["trades"]), "games26": f"{m26['games_traded']:,}",
        "trades_all": millions(m26["trades"] + (m25["trades"] if m25 else 0)),
        "contracts26": millions(m26["contracts"]), "pitches26": f"{m26['pitches']:,}",
        "pitches25": f"{m25['pitches']:,}" if m25 else "", "usable25": f"{r25['usable']:,}" if r25 else "",
        "trades25": millions(m25["trades"]) if m25 else "", "games25": f"{m25['games_traded']:,}" if m25 else "",
        "usable26": f"{r26['usable']:,}", "big26": f"{r26['big']:,}",
        "hero_team": team,
        "hero_title": f"{h['batter']} homers: {team} from {h['p_ref']:.0f}&cent; to {h['p_after']:.0f}&cent;",
        "hero_caption": (f"Every fill in the market on {team} winning, from eight seconds before the pitch to thirty "
                         f"after: {h['batter']}&rsquo;s home run in the {half_inn} of the {ORD.get(h['inning'], str(h['inning']) + 'th')} "
                         f"inning, {h['away']} at {h['home']}{stage}, {nice_date(h['date'])}. The first trade more "
                         f"than halfway to the new price came <strong>{h['half_time']:.2f} seconds</strong> after "
                         f"MLB&rsquo;s pitch timestamp; MLB&rsquo;s public feed marked the play final at "
                         f"{h['feed_delay']:.1f} seconds. The fair move said {fair_after:.0f}&cent;; the market "
                         f"settled near {h['p_after']:.0f}&cent;. Dot area is proportional to contracts."),
        "half_med": s1(sp["half_time"]["median"]), "half_med_raw": f"{sp['half_time']['median']:.3f}",
        "ahead_feed": pct(sp["ahead_of_feed"]["est"]), "ahead_lo": pct(sp["ahead_of_feed"]["lo"]),
        "ahead_hi": pct(sp["ahead_of_feed"]["hi"]),
        "beta60_big": f"{acc['beta60_big']['est']:.2f}", "beta60_lo": f"{acc['beta60_big']['lo']:.2f}",
        "beta60_hi": f"{acc['beta60_big']['hi']:.2f}",
        "given_back": pct(tax["given_back"]), "gb_lo": pct(tax["given_back_ci"][0]), "gb_hi": pct(tax["given_back_ci"][1]),
        "given_back_net": pct(tax["given_back_net"]) if tax["given_back_net"] is not None else "more than all of it",
        "gb_dollars": f"{-tax['after_news_dollars_per_game']:,.0f}",
        "beta_m5": pct(abs(sp["beta_at"]["-5"]["est"]), 2),
        "t50": s1(sp["t50"]["est"]), "t50_lo": s1(sp["t50"]["lo"]), "t50_hi": s1(sp["t50"]["hi"]),
        "t50_raw": f"{sp['t50']['est']:.3f}", "t90": s1(sp["t90"]["est"]), "t90_raw": f"{sp['t90']['est']:.3f}",
        "within1": pct(sp["half_time"]["within_1s"]), "within2": pct(sp["half_time"]["within_2s"]),
        "within5": pct(sp["half_time"]["within_5s"]), "never60": pct(sp["half_time"]["never_60s"], 1),
        "feed_called": s1(delay[~p.in_play].median()), "feed_inplay": s1(delay[p.in_play].median()),
        "kinds_sentence": kinds_sentence(k),
        "sim_lag": f"{sim['half_minus_true_median']:.2f}", "sim_gap": pct(sim["curve_max_gap"]),
        "sim_after": ("every time" if sim["half_before_true_n"] == 0 else
                      f"in all but {sim['half_before_true_n']:,} of {sim['big_events']:,} simulated big pitches"),
        "sim_catch": f"{sim['curve_within_1pct_from']:g}",
        "sim_markout": sim_pct(sim["markout_ratio"]), "sim_games": f"{sim['games']:,}",
        "drift": signed(acc["drift_big"]["slope"], 3), "drift_se": f"{acc['drift_big']['se']:.3f}",
        "outcome": signed(acc["outcome_big"]["slope"], 3), "outcome_se": f"{acc['outcome_big']['se']:.3f}",
        "brier_m": f"{acc['brier_market']:.4f}", "brier_a": f"{acc['brier_average_team']:.4f}",
        "maker_c": f"{tax['maker_c_per_contract']:.2f}", "maker_fee_c": f"{tax['maker_fee_c']:.2f}", "after_news_share": pct(tax["after_news_share_contracts"], 1),
        "after_news_c": f"{-tax['after_news_maker_c']:.2f}", "rest_c": f"{tax['rest_maker_c']:.2f}",
        "snipe_share": pct(tax["snipe_share_contracts"], 1), "snipe_c": f"{tax['snipe_taker_c']:.2f}",
        "snipe_fee_c": f"{tax['snipe_taker_fee_c']:.2f}",
        "pulse_before": f"{pulse['until'][0]:.2f}", "pulse_base": f"{pulse['baseline']:.2f}",
        "big_before": f"{r26['pulse_big']['before']:.1f}", "big_peak": f"{r26['pulse_big']['peak']:.1f}",
        "big_jump": jump_word(r26["pulse_big"]["peak"] / r26["pulse_big"]["before"]),
        "big_after": f"{after_rate(r26['pulse_big']):.1f}",
        "big_peak_t": s1(r26["pulse_big"]["peak_t"]), "big_n": f"{r26['pulse_big']['n_big']:,}",
        "seasons_paragraph": seasons_paragraph(r25, r26, m25, m26, first_day) if r25 else "",
        "placebo": pct(r26["placebo"]["est"], 2), "placebo_lo": pct(r26["placebo"]["lo"], 2),
        "placebo_hi": pct(r26["placebo"]["hi"], 2),
        "settle26": f"{int(mk26.settles_right.sum()):,} of {len(mk26):,}",
        "settle25": f"{int(mk25.settles_right.sum()):,} of {len(mk25):,}" if mk25 is not None else "",
        "n_tests": str(n_tests),
    }
    for tpl, dest in (("index.html", SITE / "index.html"), ("README.md", ROOT / "README.md")):
        text = (ROOT / "templates" / tpl).read_text()
        missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)) - {key for key, val in v.items() if val != ""})
        if missing and not os.environ.get("DRAFT"):
            raise SystemExit(f"{tpl}: no value for: {', '.join(missing)}")
        fill = {**v, **{key: "[pending]" for key in missing}}     # DRAFT=1 previews while a season is downloading
        dest.write_text(re.sub(r"\{\{(\w+)\}\}", lambda m: str(fill[m.group(1)]), text))
    print(f"site/index.html and README.md written ({len(v)} numbers)", flush=True)


if __name__ == "__main__":
    build()
