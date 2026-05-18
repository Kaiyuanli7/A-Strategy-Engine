"""End-to-end API tests for the factor research workstation."""

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
def primed_cache(cache, loader):
    """Synthetic CSI 300 universe with 60+ stocks priming the cache."""
    counts = loader.prime_universe_synthetic(
        index_code="000300",
        start="2023-01-01",
        end="2025-12-31",
        n_members=60,
    )
    assert counts["members"] >= 60
    return cache


@pytest.fixture
def client(primed_cache, storage, loader):
    app.dependency_overrides[get_cache] = lambda: primed_cache
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_loader] = lambda: loader
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["cached_stocks"] >= 1


def test_universe_returns_index_members(client):
    r = client.get("/api/data/universe?index=000300")
    assert r.status_code == 200
    body = r.json()
    assert body["name"]
    assert len(body["codes"]) >= 10
    assert len(body["stocks"]) == len(body["codes"])


def test_stock_ohlcv_endpoint(client, primed_cache):
    code = primed_cache.all_meta_codes()[0]
    r = client.get(f"/api/data/stock/{code}?start=2023-01-01&end=2025-12-31")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == code
    assert len(body["bars"]) > 0


def test_stock_ohlcv_404_for_unknown(client):
    r = client.get("/api/data/stock/999999?start=2023-01-01&end=2025-12-31")
    assert r.status_code == 404


def test_sectors_endpoint(client):
    r = client.get("/api/data/sectors")
    assert r.status_code == 200
    assert "sectors_l1" in r.json()


def test_list_factors_includes_northbound_momentum(client):
    r = client.get("/api/factors")
    assert r.status_code == 200
    factors = r.json()
    names = [f["name"] for f in factors]
    assert "northbound_momentum" in names
    nm = next(f for f in factors if f["name"] == "northbound_momentum")
    assert nm["category"] == "flow"
    assert nm["lookback_days"] > 0
    assert any(p["name"] == "lookback" for p in nm["params"])


def test_evaluate_northbound_momentum_returns_full_payload(client):
    r = client.get(
        "/api/factors/northbound_momentum/evaluate",
        params={
            "start": "2023-06-01",
            "end": "2024-12-31",
            "universe": "000300",
            "horizon": 20,
            "rebalance": "weekly",
            "lookback": 5,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["factor"]["name"] == "northbound_momentum"
    assert body["params"]["lookback"] == 5
    assert body["n_dates"] > 0
    assert len(body["ic_series"]) > 0
    assert "ic_summary" in body
    assert len(body["quintile_cum"]) > 0
    qpoint = body["quintile_cum"][0]
    for col in ("q1", "q2", "q3", "q4", "q5", "long_short"):
        assert col in qpoint
    assert len(body["decay"]) >= 3


def test_evaluate_returns_cached_on_second_call(client):
    params = {
        "start": "2023-06-01",
        "end": "2024-06-30",
        "universe": "000300",
        "horizon": 10,
        "rebalance": "weekly",
        "lookback": 5,
    }
    r1 = client.get("/api/factors/northbound_momentum/evaluate", params=params)
    assert r1.status_code == 200
    assert r1.json()["cached"] is False

    r2 = client.get("/api/factors/northbound_momentum/evaluate", params=params)
    assert r2.status_code == 200
    assert r2.json()["cached"] is True


def test_evaluate_unknown_factor_404(client):
    r = client.get("/api/factors/does_not_exist/evaluate")
    assert r.status_code == 404


def test_list_backtest_runs_empty(client):
    r = client.get("/api/backtest/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_walk_forward_runs_empty(client):
    r = client.get("/api/backtest/walk_forward")
    assert r.status_code == 200
    assert r.json() == []
