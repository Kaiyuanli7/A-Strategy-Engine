"""Portfolio + T+1 settlement tests."""

import pytest

from astrategy.engine.portfolio import Portfolio


def test_initial_state():
    pf = Portfolio(1_000_000.0)
    assert pf.cash == 1_000_000.0
    assert pf.equity({}) == 1_000_000.0
    assert pf.positions == {}


def test_buy_then_t1_lock():
    pf = Portfolio(1_000_000.0)
    ok = pf.apply_buy("600519", 100, 1000.0, 30.0)  # 100 shares @ ¥1000 + ¥30 cost
    assert ok is True
    pos = pf.positions["600519"]
    assert pos.shares == 100
    assert pos.sellable == 0          # T+1: same day sells blocked
    assert pf.cash == 1_000_000.0 - 100_000.0 - 30.0


def test_t1_settle_unlocks():
    pf = Portfolio(1_000_000.0)
    pf.apply_buy("600519", 100, 1000.0, 30.0)
    assert pf.positions["600519"].sellable == 0
    pf.settle_t1()
    assert pf.positions["600519"].sellable == 100


def test_cannot_sell_more_than_sellable():
    pf = Portfolio(1_000_000.0)
    pf.apply_buy("600519", 200, 100.0, 5.0)
    pf.settle_t1()  # now 200 sellable
    ok = pf.apply_sell("600519", 300, 100.0, 5.0)
    assert ok is False
    assert pf.positions["600519"].shares == 200


def test_sell_reduces_position():
    pf = Portfolio(1_000_000.0)
    pf.apply_buy("600519", 200, 100.0, 5.0)
    pf.settle_t1()
    ok = pf.apply_sell("600519", 100, 110.0, 5.5)
    assert ok is True
    assert pf.positions["600519"].shares == 100
    assert pf.positions["600519"].sellable == 100
    assert pf.cash == pytest.approx(1_000_000.0 - 200 * 100 - 5.0 + 100 * 110 - 5.5)


def test_intraday_buy_blocked_sell():
    """Classic T+1 scenario: buy on day N, sell attempt on day N before settle fails."""
    pf = Portfolio(1_000_000.0)
    pf.apply_buy("600519", 100, 100.0, 5.0)
    # No settle_t1 between buy and sell → sellable still 0
    assert pf.apply_sell("600519", 100, 110.0, 5.5) is False


def test_buy_fails_if_insufficient_cash():
    pf = Portfolio(1_000.0)
    assert pf.apply_buy("600519", 100, 1000.0, 30.0) is False
    assert pf.cash == 1_000.0


def test_equity_with_positions():
    pf = Portfolio(100_000.0)
    pf.apply_buy("600519", 100, 500.0, 13.0)
    # Cash = 100000 - 50000 - 13 = 49987; mark @ 550 → 100*550 = 55000
    assert pf.equity({"600519": 550.0}) == pytest.approx(49_987.0 + 55_000.0)
