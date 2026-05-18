"""Transaction cost unit tests."""

import pytest

from astrategy.engine.costs import buy_cost, sell_cost


def test_buy_cost_above_floor():
    # 100,000 yuan notional: commission = 25, transfer = 1.0 → 26.0
    assert buy_cost(100_000.0) == pytest.approx(25.0 + 1.0, abs=0.01)


def test_buy_cost_floor():
    # 1,000 yuan notional: 0.025% = 0.25 → floor to ¥5.00. Transfer = 0.01.
    assert buy_cost(1_000.0) == pytest.approx(5.0 + 0.01, abs=0.01)


def test_sell_cost_adds_stamp_tax():
    # 100,000 yuan notional sell: buy_cost (26.0) + stamp tax (50.0)
    assert sell_cost(100_000.0) == pytest.approx(26.0 + 50.0, abs=0.01)


def test_sell_cost_floor():
    # 1,000 yuan notional sell: floor commission ¥5 + transfer 0.01 + stamp 0.5
    assert sell_cost(1_000.0) == pytest.approx(5.0 + 0.01 + 0.5, abs=0.01)
