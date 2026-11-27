"""Reading Kalshi's trade files and expressing both markets of a game in home-team terms."""
import gzip
import json

from build_trades import read_trades, to_home

ROWS = [["2026-07-18T01:45:23.311247Z", "0.4000", "10.00", "yes", False],
        ["2026-07-18T01:45:24Z", "0.4100", "2.50", "no", False]]


def write(tmp_path):
    f = tmp_path / "t.jsonl.gz"
    f.write_bytes(gzip.compress("\n".join(json.dumps(r) for r in ROWS).encode()))
    return f


def test_timestamps_with_and_without_fractional_seconds(tmp_path):
    t = read_trades(write(tmp_path))
    assert t.ts.iloc[1] - t.ts.iloc[0] == 1_000_000 - 311_247          # microseconds
    assert list(t.yes_cents) == [40.0, 41.0] and list(t.contracts) == [10.0, 2.5]


def test_home_market_keeps_price_and_direction(tmp_path):
    t = to_home(read_trades(write(tmp_path)), "home")
    assert list(t.home_cents) == [40.0, 41.0]
    assert list(t.dir) == [1, -1]                  # taker bought YES = bought the home team


def test_away_market_flips_price_and_direction(tmp_path):
    t = to_home(read_trades(write(tmp_path)), "away")
    assert list(t.home_cents) == [60.0, 59.0]      # away team at 40 = home team at 60
    assert list(t.dir) == [-1, 1]                  # buying the away team is selling the home team
