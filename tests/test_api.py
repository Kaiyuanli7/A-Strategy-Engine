"""End-to-end tests for the FastAPI server using TestClient + isolated tmp DB."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from astrategy.api.main import app, get_cache, get_loader, get_storage
from astrategy.api.storage import RunStorage
from astrategy.config import classify_board, is_st_name
from astrategy.data.akshare_client import AKShareClient
from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader
from astrategy.data.synthetic import generate_synthetic_ohlcv
from astrategy.data.universe import DEMO_UNIVERSE


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """An isolated SQLite DB seeded with synthetic data for all demo stocks."""
    db = tmp_path / "test.db"
    cache = SQLiteCache(str(db))
    for code, name in DEMO_UNIVERSE:
        cache.upsert_stock_meta(code, name, classify_board(code), is_st_name(name))
        df = generate_synthetic_ohlcv(code, "2023-05-18", "2026-05-18")
        cache.upsert_daily_bars(code, df)
        cache.record_fetch(code, "2023-05-18", "2026-05-18", len(df))
    cache.upsert_index_constituents("DEMO", [c for c, _ in DEMO_UNIVERSE], "2026-05-18")
    return db


@pytest.fixture
def client(tmp_db: Path) -> TestClient:
    """TestClient with FastAPI deps overridden to use the tmp_db."""
    db_path = str(tmp_db)

    def _cache_override() -> SQLiteCache:
        return SQLiteCache(db_path)

    def _storage_override() -> RunStorage:
        return RunStorage(db_path)

    def _loader_override() -> DataLoader:
        # Real loader pointed at the tmp DB; AKShare client never hit because data is cached
        return DataLoader(client=AKShareClient(), cache=SQLiteCache(db_path))

    app.dependency_overrides[get_cache] = _cache_override
    app.dependency_overrides[get_storage] = _storage_override
    app.dependency_overrides[get_loader] = _loader_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --- meta ---------------------------------------------------------------------

def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["cached_stocks"] == 10
    assert body["cached_runs"] == 0
    assert body["version"]


def test_list_strategies(client: TestClient):
    r = client.get("/api/strategies")
    assert r.status_code == 200
    assert "ma_cross" in r.json()["types"]


# --- data ---------------------------------------------------------------------

def test_universe(client: TestClient):
    r = client.get("/api/data/universe")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "demo"
    assert len(body["codes"]) == 10
    assert "600519" in body["codes"]
    stocks = {s["code"]: s for s in body["stocks"]}
    assert stocks["300750"]["board"] == "chinext"
    assert stocks["600519"]["board"] == "main_sh"


def test_get_stock(client: TestClient):
    r = client.get("/api/data/stock/600519")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "600519"
    assert body["name"] == "贵州茅台"
    assert body["board"] == "main_sh"
    assert len(body["bars"]) > 100
    bar = body["bars"][0]
    assert {"date", "open", "high", "low", "close", "volume"} <= bar.keys()


def test_get_stock_not_found(client: TestClient):
    r = client.get("/api/data/stock/999999")
    assert r.status_code == 404


def test_get_stock_date_range(client: TestClient):
    r = client.get("/api/data/stock/600519", params={"start": "2024-01-01", "end": "2024-02-01"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert all("2024-01-01" <= b["date"] <= "2024-02-01" for b in bars)


def test_fetch_synthetic(client: TestClient, tmp_path):
    payload = {
        "codes": ["600519", "601318"],
        "start": "2023-05-18",
        "end": "2026-05-18",
        "synthetic": True,
    }
    r = client.post("/api/data/fetch", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["used_synthetic"] is True
    assert body["rows_per_code"]["600519"] > 100
    assert body["rows_per_code"]["601318"] > 100


# --- backtest -----------------------------------------------------------------

VALID_BACKTEST_REQ = {
    "strategy": {
        "type": "ma_cross",
        "params": {"fast": 5, "slow": 20, "position_size_pct": 0.05, "max_positions": 10},
    },
    "universe": [c for c, _ in DEMO_UNIVERSE],
    "config": {
        "start": "2023-05-18",
        "end": "2026-05-18",
        "initial_cash": 1_000_000.0,
        "limit_hit_fill_prob": 0.20,
        "random_seed": 42,
    },
}


def test_run_backtest_completes(client: TestClient):
    r = client.post("/api/backtest/run", json=VALID_BACKTEST_REQ)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert "run_id" in body
    s = body["summary"]
    assert s["initial_equity"] == pytest.approx(1_000_000.0)
    assert s["n_bars"] > 100
    assert s["n_fills"] > 0


def test_run_backtest_unknown_strategy(client: TestClient):
    req = dict(VALID_BACKTEST_REQ)
    req["strategy"] = {"type": "nonexistent", "params": {}}
    r = client.post("/api/backtest/run", json=req)
    assert r.status_code == 422  # pydantic Literal validation


def test_run_backtest_unknown_universe(client: TestClient):
    req = {**VALID_BACKTEST_REQ, "universe": ["999999"]}
    r = client.post("/api/backtest/run", json=req)
    assert r.status_code == 404


def test_get_backtest_result(client: TestClient):
    run = client.post("/api/backtest/run", json=VALID_BACKTEST_REQ).json()
    run_id = run["run_id"]

    r = client.get(f"/api/backtest/results/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == run_id
    assert body["status"] == "completed"
    assert len(body["equity_curve"]) > 100
    assert len(body["fills"]) > 0
    assert body["config"]["strategy"]["type"] == "ma_cross"


def test_get_backtest_result_not_found(client: TestClient):
    r = client.get("/api/backtest/results/abc123nonexistent")
    assert r.status_code == 404


def test_list_backtest_runs(client: TestClient):
    # Empty
    assert client.get("/api/backtest/runs").json() == []

    client.post("/api/backtest/run", json=VALID_BACKTEST_REQ)
    client.post("/api/backtest/run", json={
        **VALID_BACKTEST_REQ,
        "strategy": {"type": "ma_cross", "params": {"fast": 10, "slow": 30}},
    })

    runs = client.get("/api/backtest/runs").json()
    assert len(runs) == 2
    assert all(r["status"] == "completed" for r in runs)
    assert all(r["strategy_type"] == "ma_cross" for r in runs)
    assert runs[0]["universe_size"] == 10


def test_backtest_persists_equity_curve_ordered(client: TestClient):
    run = client.post("/api/backtest/run", json=VALID_BACKTEST_REQ).json()
    result = client.get(f"/api/backtest/results/{run['run_id']}").json()
    dates = [p["date"] for p in result["equity_curve"]]
    assert dates == sorted(dates)
