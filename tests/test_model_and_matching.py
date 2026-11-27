"""The fair move, the event labels, exposure accounting, and matching Kalshi markets to MLB games."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from build_trades import pick_games, split_teams
from events import classify, exposure, fair_move
from fetch_kalshi import scheduled_start


def test_fair_move_is_the_win_expectancy_change_when_the_market_agrees_with_it():
    F = fair_move(np.array([50.0]), np.array([0.5]), np.array([0.6]))
    assert np.isclose(F[0], 10.0)


def test_fair_move_respects_the_markets_view_of_the_teams():
    # the market makes the home team a 75% favorite where an average team would be 50%: the same state change is
    # worth less in points near the edge of the scale, and it keeps the market's tilt
    F = fair_move(np.array([75.0]), np.array([0.5]), np.array([0.6]))
    assert 0 < F[0] < 10
    s = np.log(0.75 / 0.25) - 0.0
    post = 1 / (1 + np.exp(-(np.log(0.6 / 0.4) + s)))
    assert np.isclose(F[0], 100 * (post - 0.75))


def test_the_last_pitch_settles_the_game():
    F = fair_move(np.array([62.0, 62.0]), np.array([0.7, 0.7]), np.array([1.0, 0.0]))
    assert np.allclose(F, [38.0, -62.0])


def test_event_labels():
    df = pd.DataFrame({
        "pa_event": ["home_run", "strikeout", "walk", "double", "field_out", None, None],
        "description": ["In play, run(s)", "Swinging Strike", "Ball", "In play, no out", "In play, out(s)", "Ball",
                        "Foul"],
        "ends_pa": [True, True, True, True, True, False, False],
        "in_play": [True, False, False, True, True, False, False]})
    assert list(classify(df)) == ["Home run", "Strikeout", "Walk or HBP", "Hit", "Out in play", "Ball",
                                  "Strike or foul"]


def test_exposure_counts_seconds_observed_in_each_bin():
    edges = np.array([0, 5, 10, 15.0])
    # gaps of 7 s and 20 s: 0-5 observed 10 s, 5-10 observed 2 + 5 = 7 s, 10-15 observed 5 s
    assert np.allclose(exposure(np.array([7.0, 20.0]), edges), [10, 7, 5])


def test_kalshi_event_codes():
    assert split_teams("TBBOS", {"TB", "BOS", "MIL"}) == ("TB", "BOS")
    assert split_teams("NYYNYM", {"NYY", "NYM"}) == ("NYY", "NYM")
    assert scheduled_start("KXMLBGAME-26OCT282000MILTB") == datetime(2026, 10, 29, 0, 0, tzinfo=timezone.utc)


H = 3600 * 1_000_000


def test_markets_find_their_games_by_close_time_even_when_the_game_moved():
    """A doubleheader is told apart by when each market closed; a postponed game keeps its original ticker date and is
    still found; a market that closed nowhere near a game's end is left unmatched."""
    from datetime import date
    games = pd.DataFrame({
        "game_pk": [1, 2, 3, 4], "et_date": [date(2026, 7, 4), date(2026, 7, 4), date(2026, 7, 6), date(2026, 7, 7)],
        "away": ["TB"] * 4, "home": ["BOS"] * 4, "home_win": [True, False, True, False],
        "last_event_utc": [100 * H, 106 * H, 150 * H, 175 * H]})
    mk = pd.DataFrame({
        "ticker": ["DH1-BOS", "DH2-BOS", "PPD-BOS", "LOST-BOS", "NEXT-BOS"],
        "et_date": [date(2026, 7, 4), date(2026, 7, 4), date(2026, 7, 5), date(2026, 7, 9), date(2026, 7, 7)],
        "away_k": ["TB"] * 5, "home_k": ["BOS"] * 5, "team_k": ["BOS"] * 5,
        "close_us": [100 * H + 120e6, 106 * H + 90e6, 150 * H + 60e6, 230 * H, 175 * H + 100e6],
        "result": ["yes", "no", "yes", "no", "no"]})
    out = pick_games(mk, games).set_index("ticker")
    assert out.loc["DH1-BOS", "game_pk"] == 1 and out.loc["DH2-BOS", "game_pk"] == 2
    assert out.loc["PPD-BOS", "game_pk"] == 3                  # ticker says July 5; played July 6
    assert out.loc["NEXT-BOS", "game_pk"] == 4
    assert "LOST-BOS" not in out.index
    assert out.settles_right.all()
