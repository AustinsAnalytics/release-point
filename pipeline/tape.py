"""Read quotes off the tape: a trade-implied midpoint for a market that publishes trades but not its order book.

A taker who buys pays the ask; a taker who sells hits the bid. So the latest buy prints an upper quote and the latest
sell a lower one, and their average is the midpoint. Fills that share a timestamp and direction are one taker order
sweeping the book; the order's last fill (highest for a buy, lowest for a sell) is the quote it left behind.

All prices are in cents of home-team win probability. Times are integer microseconds.
"""
from dataclasses import dataclass

import numpy as np

STALE_US = 10_000_000          # if one side's last print is this much older than the other's, trust the newer side


@dataclass
class Tape:
    buy_t: np.ndarray          # taker-buy orders: time, and the price of the order's last fill
    buy_px: np.ndarray
    sell_t: np.ndarray         # taker-sell orders
    sell_px: np.ndarray
    order_t: np.ndarray        # every order (either side), for activity checks
    spread: float              # typical quoted spread in cents (median of ask - bid when both are fresh)


def orders(ts, px, direction, contracts):
    """Collapse fills into taker orders: one row per (time, direction)."""
    ts, px, direction = np.asarray(ts), np.asarray(px, float), np.asarray(direction)
    contracts = np.asarray(contracts, float)
    key = ts * 2 + (direction > 0)                          # same time and same side -> same order
    order = np.argsort(key, kind="stable")
    key, ts, px, direction, contracts = key[order], ts[order], px[order], direction[order], contracts[order]
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    t = ts[starts]
    d = direction[starts]
    last_hi = np.maximum.reduceat(px, starts)
    last_lo = np.minimum.reduceat(px, starts)
    size = np.add.reduceat(contracts, starts)
    vwap = np.add.reduceat(px * contracts, starts) / np.maximum(size, 1e-12)
    last = np.where(d > 0, last_hi, last_lo)
    return t, d, last, vwap, size


def build_tape(ts, px, direction, contracts):
    t, d, last, _, _ = orders(ts, px, direction, contracts)
    buy, sell = d > 0, d < 0
    bt, bp, st, sp = t[buy], last[buy], t[sell], last[sell]
    # typical spread: at each order, latest ask minus latest bid when both are under 5 seconds old and not crossed
    ia = np.searchsorted(bt, t, side="right") - 1
    ib = np.searchsorted(st, t, side="right") - 1
    ok = (ia >= 0) & (ib >= 0)
    gaps = []
    if ok.any():
        a, b = bp[ia[ok]], sp[ib[ok]]
        fresh = (t[ok] - bt[ia[ok]] < 5_000_000) & (t[ok] - st[ib[ok]] < 5_000_000) & (a >= b)
        gaps = (a - b)[fresh]
    spread = float(np.clip(np.median(gaps), 1.0, 5.0)) if len(gaps) else 1.0
    return Tape(bt, bp, st, sp, t, spread)


def mid_at(tape, q, strict=False):
    """Trade-implied midpoint at query times q (array). strict=True uses only prints before q, not at q.
    Returns NaN where the market has no prints yet."""
    q = np.asarray(q)
    side = "left" if strict else "right"
    ia = np.searchsorted(tape.buy_t, q, side=side) - 1
    ib = np.searchsorted(tape.sell_t, q, side=side) - 1
    has_a, has_b = ia >= 0, ib >= 0
    pick = lambda arr, i, ok, fill: np.where(ok, arr[np.maximum(i, 0)], fill) if len(arr) else np.full(len(q), fill)
    a = pick(tape.buy_px, ia, has_a, np.nan)
    b = pick(tape.sell_px, ib, has_b, np.nan)
    ta = pick(tape.buy_t, ia, has_a, -1)
    tb = pick(tape.sell_t, ib, has_b, -1)
    half = tape.spread / 2
    # average the two sides only when they are consistent with one book: not crossed, no wider than the usual spread
    # plus a cent, and not far apart in time. Otherwise the older side is stale (the price has moved past it): use the
    # newer print and step half a spread toward the middle.
    both = has_a & has_b & (a >= b) & (a - b <= tape.spread + 1) & (np.abs(ta - tb) <= STALE_US)
    newer_is_buy = ta >= tb
    one_side = np.where(newer_is_buy, a - half, b + half)
    one_side = np.where(has_a & ~has_b, a - half, np.where(has_b & ~has_a, b + half, one_side))
    return np.where(both, (a + b) / 2, one_side)


def last_order_age(tape, q):
    """Seconds since the most recent order at or before q (inf if none)."""
    i = np.searchsorted(tape.order_t, q, side="right") - 1
    return np.where(i >= 0, (np.asarray(q) - tape.order_t[np.maximum(i, 0)]) / 1e6, np.inf)
