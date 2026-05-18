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
    from astrategy.data.synthetic import (
        generate_synthetic_fundamentals,
        generate_synthetic_northbound,
        generate_synthetic_sector,
        generate_synthetic_valuation_daily,
    )

    db = tmp_path / "test.db"
    cache = SQLiteCache(str(db))
    for code, name in DEMO_UNIVERSE:
        cache.upsert_stock_meta(code, name, classify_board(code), is_st_name(name))
        df = generate_synthetic_ohlcv(code, "2023-05-18", "2026-05-18")
        cache.upsert_daily_bars(code, df)
        cache.record_fetch(code, "2023-05-18", "2026-05-18", len(df))
        # Phase 4 tables
        cache.upsert_fundamentals(
            code, generate_synthetic_fundamentals(code, "2023-05-18", "2026-05-18")
        )
        ohlcv_str = df.assign(date=df["date"].astype(str))
        cache.upsert_valuation_daily(
            code,
            generate_synthetic_valuation_daily(code, "2023-05-18", "2026-05-18", ohlcv_str),
        )
        cache.upsert_northbound(
            code, generate_synthetic_northbound(code, "2023-05-18", "2026-05-18")
        )
        sec = generate_synthetic_sector(code)
        cache.upsert_sector(
            code, sw_l1_name=sec["sw_l1_name"], sw_l1_code=sec["sw_l1_code"],
        )
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


# --- Phase 4 ----------------------------------------------------------------

COMPOSABLE_REQ = {
    "strategy": {
        "type": "composable",
        "params": {
            "entry_conditions": [
                {"type": "ma_cross", "fast": 5, "slow": 20, "direction": "up"},
            ],
            "exit_rules": {"max_hold_days": 30, "signal_reversal": True},
            "sizing": {"method": "equal_weight", "position_size_pct": 0.10},
            "max_positions": 5,
        },
    },
    "universe": [c for c, _ in DEMO_UNIVERSE],
    "config": {
        "start": "2023-05-18", "end": "2026-05-18",
        "initial_cash": 1_000_000.0, "limit_hit_fill_prob": 0.20, "random_seed": 42,
    },
}


def test_condition_types_endpoint(client: TestClient):
    r = client.get("/api/strategies/condition-types")
    assert r.status_code == 200
    body = r.json()
    assert len(body["condition_types"]) >= 13
    types = {c["type"] for c in body["condition_types"]}
    assert {"ma_cross", "rsi", "pe_bound", "nb_net_inflow"} <= types


def test_list_strategies_includes_composable(client: TestClient):
    r = client.get("/api/strategies")
    assert r.status_code == 200
    assert "composable" in r.json()["types"]


def test_screener_preview_returns_codes(client: TestClient):
    r = client.get("/api/data/screener/preview")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    assert len(body["filtered_codes"]) == 10


def test_screener_preview_filters_by_board(client: TestClient):
    r = client.get("/api/data/screener/preview", params={"boards": "chinext"})
    assert r.status_code == 200
    # Only 300750 is on ChiNext among the 10 demo stocks
    assert r.json()["filtered_codes"] == ["300750"]


def test_screener_preview_filters_by_sector(client: TestClient):
    r = client.get("/api/data/screener/preview", params={"sectors_l1": "银行"})
    assert r.status_code == 200
    # 601398 (ICBC) and 600036 (CMB) are 银行
    assert set(r.json()["filtered_codes"]) == {"601398", "600036"}


def test_sectors_list(client: TestClient):
    r = client.get("/api/data/sectors")
    assert r.status_code == 200
    sectors = r.json()["sectors_l1"]
    assert "食品饮料" in sectors  # Moutai + Wuliangye


def test_run_composable_strategy_completes(client: TestClient):
    r = client.post("/api/backtest/run", json=COMPOSABLE_REQ)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["summary"]["n_bars"] > 100


def test_universe_filter_narrows_to_chinext(client: TestClient):
    req = {**COMPOSABLE_REQ, "universe_filter": {"boards": ["chinext"], "exclude_st": True}}
    r = client.post("/api/backtest/run", json=req)
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    detail = client.get(f"/api/backtest/results/{run_id}").json()
    fill_codes = {f["code"] for f in detail["fills"]}
    # Only 300750 should appear (the lone ChiNext stock)
    assert fill_codes <= {"300750"}


def test_universe_filter_empty_result_422(client: TestClient):
    req = {
        **COMPOSABLE_REQ,
        "universe_filter": {"boards": ["star"], "exclude_st": True},  # No STAR in demo
    }
    r = client.post("/api/backtest/run", json=req)
    assert r.status_code == 422


def test_run_composable_with_pe_bound_no_crash(client: TestClient):
    """Restrictive composable spec returns 200 with possibly zero fills (not 500)."""
    req = {
        **COMPOSABLE_REQ,
        "strategy": {
            "type": "composable",
            "params": {
                "entry_conditions": [
                    {"type": "ma_cross", "fast": 5, "slow": 20, "direction": "up"},
                    {"type": "pe_bound", "max": 0.01},  # impossibly restrictive
                ],
                "exit_rules": {},
                "sizing": {"method": "equal_weight", "position_size_pct": 0.10},
            },
        },
    }
    r = client.post("/api/backtest/run", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["summary"]["n_fills"] == 0
    assert body["summary"]["final_equity"] == pytest.approx(body["summary"]["initial_equity"])
