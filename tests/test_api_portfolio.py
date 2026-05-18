"""End-to-end tests for /api/portfolios/* endpoints."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from astrategy.api.main import app, get_cache, get_loader, get_storage
from astrategy.api.storage import RunStorage
from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader


@pytest.fixture
def cache(tmp_path):
    return SQLiteCache(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def storage(tmp_path):
    return RunStorage(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def loader(cache):
    return DataLoader(cache=cache)


@pytest.fixture
def primed(cache, loader):
    loader.prime_universe_synthetic(
        index_code="000300", start="2023-01-01", end="2024-06-30",
        n_members=40,
    )
    return cache


@pytest.fixture
def client(primed, storage, loader):
    app.dependency_overrides[get_cache] = lambda: primed
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_loader] = lambda: loader
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _basic_request_body() -> dict:
    return {
        "composite": {
            "method": "equal_weight",
            "factors": [
                {"factor_name": "momentum_skip",
                 "params": {"lookback": 20, "skip": 5}, "weight": None},
                {"factor_name": "northbound_momentum",
                 "params": {"lookback": 5}, "weight": None},
            ],
        },
        "portfolio": {
            "top_n": 10,
            "rebalance_freq": "monthly",
            "max_sector_pct": 0.5,
            "max_single_position_pct": 0.20,
            "min_market_cap": 0.0,
            "exclude_st": True,
            "weighting": "equal",
        },
        "universe": "000300",
        "start": "2023-06-01",
        "end": "2024-06-30",
        "initial_cash": 1_000_000.0,
        "limit_hit_fill_prob": 1.0,
        "random_seed": 42,
    }


def test_portfolio_backtest_endpoint(client):
    body = _basic_request_body()
    r = client.post("/api/portfolios/backtest", json=body)
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["status"] == "completed"
    assert resp["run_id"]
    assert resp["summary"] is not None


def test_portfolio_result_retrievable(client):
    body = _basic_request_body()
    r = client.post("/api/portfolios/backtest", json=body)
    run_id = r.json()["run_id"]

    r2 = client.get(f"/api/portfolios/runs/{run_id}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["run_id"] == run_id
    assert body2["status"] == "completed"
    # Equity curve has many points
    assert len(body2["equity_curve"]) > 50
    # Some fills were generated (10-stock rebalance over 12 months)
    assert isinstance(body2["fills"], list)


def test_portfolio_run_404_for_unknown_id(client):
    r = client.get("/api/portfolios/runs/does_not_exist")
    assert r.status_code == 404


def test_portfolio_runs_list(client):
    # No runs yet
    r0 = client.get("/api/portfolios/runs")
    assert r0.status_code == 200
    n_before = len(r0.json())

    body = _basic_request_body()
    client.post("/api/portfolios/backtest", json=body)

    r1 = client.get("/api/portfolios/runs")
    assert r1.status_code == 200
    assert len(r1.json()) == n_before + 1


def test_portfolio_rejects_unknown_factor(client):
    body = _basic_request_body()
    body["composite"]["factors"][0]["factor_name"] = "does_not_exist"
    r = client.post("/api/portfolios/backtest", json=body)
    assert r.status_code == 400
    assert "unknown factor" in r.json()["detail"]


def test_portfolio_rejects_empty_factor_list(client):
    body = _basic_request_body()
    body["composite"]["factors"] = []
    r = client.post("/api/portfolios/backtest", json=body)
    # Pydantic schema enforces min_length=1
    assert r.status_code == 422


def test_portfolio_rejects_over_5_factors(client):
    body = _basic_request_body()
    body["composite"]["factors"] = [
        {"factor_name": "momentum_skip", "params": {}, "weight": None}
    ] * 6
    r = client.post("/api/portfolios/backtest", json=body)
    # max_length=5 enforced (anti-overfitting per CLAUDE.md)
    assert r.status_code == 422
