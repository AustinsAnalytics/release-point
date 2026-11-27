"""The fair move, the event labels, exposure accounting, and matching Kalshi markets to MLB games."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from build_trades import split_teams
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
