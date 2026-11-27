"""On a simulated market with known repricing times, the estimators recover the truth (or bound it from above)."""
import numpy as np

from simulate import run

R = run(n_games=60, seed=3)


def test_half_adjustment_time_never_beats_the_true_repricing():
    assert R["half_after_true_share"] == 1.0           # a trade-based measure can only see a move after it happens


def test_half_adjustment_time_lags_the_truth_by_well_under_a_second():
    assert 0 <= R["half_minus_true_median"] < 0.5


def test_long_run_response_and_markouts_are_unbiased():
    i = R["curve_grid"].index(60)
    assert abs(R["beta_est"][i] - R["beta_true"][i]) < 0.02
    assert abs(R["markout_ratio"] - 1) < 0.03


def test_no_response_before_the_pitch():
    for g, b in zip(R["curve_grid"], R["beta_est"]):
        if g <= 0:
            assert abs(b) < 0.01
