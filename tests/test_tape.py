"""Reading quotes off the tape: order grouping, the trade-implied midpoint, and no look-ahead."""
import numpy as np

from tape import build_tape, mid_at, orders, spread_at

S = 1_000_000  # one second in microseconds


def test_fills_at_one_instant_are_one_order():
    ts = np.array([10, 10, 10, 20]) * S
    px = np.array([50, 51, 52, 49.0])
    d = np.array([1, 1, 1, -1])
    c = np.array([5, 5, 10, 3.0])
    t, side, last, vwap, size = orders(ts, px, d, c)
    assert list(t) == [10 * S, 20 * S]
    assert list(side) == [1, -1]
    assert last[0] == 52 and last[1] == 49          # a buy sweeps up to its highest fill; a sell down to its lowest
    assert size[0] == 20 and np.isclose(vwap[0], (50 * 5 + 51 * 5 + 52 * 10) / 20)


def test_midpoint_averages_a_consistent_book():
    tape = build_tape(np.array([1, 2, 3, 4]) * S, np.array([51, 50, 51, 50.0]), np.array([1, -1, 1, -1]),
                      np.ones(4))
    assert spread_at(tape, np.array([5 * S]))[0] == 1.0
    assert mid_at(tape, np.array([5 * S]))[0] == 50.5


def test_a_stale_side_is_ignored_after_the_price_moves():
    # quiet book at 50/51, then news: buyers lift offers at 58 and 59; the old 50 bid is stale
    ts = np.array([1, 2, 3, 4, 20, 20.5]) * S
    px = np.array([51, 50, 51, 50, 58, 59.0])
    d = np.array([1, -1, 1, -1, 1, 1])
    tape = build_tape(ts.astype(np.int64), px, d, np.ones(6))
    q = np.array([21 * S])
    assert mid_at(tape, q)[0] == 59 - spread_at(tape, q)[0] / 2


def test_crossed_prints_use_the_newer_side():
    ts = np.array([1, 2, 3, 4, 10]) * S
    px = np.array([51, 50, 51, 50, 45.0])          # a sell at 45 after a buy at 51: the old offer is gone
    d = np.array([1, -1, 1, -1, -1])
    tape = build_tape(ts, px, d, np.ones(5))
    q = np.array([11 * S])
    assert mid_at(tape, q)[0] == 45 + spread_at(tape, q)[0] / 2


def test_strict_reference_never_sees_the_print_at_the_reference_time():
    ts = np.array([1, 2, 3]) * S
    tape = build_tape(ts, np.array([51, 50, 70.0]), np.array([1, -1, 1]), np.ones(3))
    q = np.array([3 * S])
    assert mid_at(tape, q, strict=True)[0] == 50.5     # the 70 print at exactly t=3 s is excluded
    assert mid_at(tape, q, strict=False)[0] != 50.5


def test_the_typical_spread_uses_only_the_past():
    # a tight 50/51 book early on, a 4-cent book later: the early midpoint is judged with the early spread only
    ts = np.array([1, 2, 3, 4, 100, 101, 102, 103]) * S
    px = np.array([51, 50, 51, 50, 54, 50, 54, 50.0])
    d = np.array([1, -1, 1, -1, 1, -1, 1, -1])
    tape = build_tape(ts, px, d, np.ones(8))
    assert spread_at(tape, np.array([5 * S]))[0] == 1.0
    assert spread_at(tape, np.array([104 * S]))[0] > 1.0
    assert mid_at(tape, np.array([5 * S]))[0] == 50.5


def test_no_prints_yet_is_nan():
    tape = build_tape(np.array([5 * S]), np.array([50.0]), np.array([1]), np.ones(1))
    assert np.isnan(mid_at(tape, np.array([1 * S]))[0])
