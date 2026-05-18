"""Backtest run persistence — extends the SQLite cache with run/fills/equity tables."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

from astrategy.engine.backtest import BacktestResult
from astrategy.engine.orders import Fill, OrderSide


RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id            TEXT PRIMARY KEY,
    config_json   TEXT NOT NULL,
    summary_json  TEXT,
    status        TEXT NOT NULL,
    error         TEXT,
    created_at    TEXT NOT NULL,
    completed_at  TEXT
);

CREATE TABLE IF NOT EXISTS backtest_equity (
    run_id   TEXT NOT NULL,
    date     TEXT NOT NULL,
    equity   REAL NOT NULL,
    PRIMARY KEY (run_id, date)
);

CREATE TABLE IF NOT EXISTS backtest_fills (
    run_id    TEXT NOT NULL,
    seq       INTEGER NOT NULL,
    date      TEXT NOT NULL,
    code      TEXT NOT NULL,
    side      TEXT NOT NULL,
    shares    INTEGER NOT NULL,
    price     REAL NOT NULL,
    cost      REAL NOT NULL,
    rejected  TEXT,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON backtest_runs(created_at DESC);
"""


class RunStorage:
    def __init__(self, db_path: str | Path = "data/astrategy.db"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(RUNS_SCHEMA)

    def new_run(self, config: dict) -> str:
        run_id = uuid.uuid4().hex
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO backtest_runs (id, config_json, status, created_at) "
                "VALUES (?, ?, 'pending', ?)",
                (run_id, json.dumps(config, default=str), datetime.utcnow().isoformat()),
            )
        return run_id

    def mark_failed(self, run_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE backtest_runs SET status = 'failed', error = ?, completed_at = ? "
                "WHERE id = ?",
                (error, datetime.utcnow().isoformat(), run_id),
            )

    def save_result(self, run_id: str, result: BacktestResult) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE backtest_runs SET status = 'completed', summary_json = ?, "
                "completed_at = ? WHERE id = ?",
                (
                    json.dumps(_jsonable(result.summary), default=str),
                    datetime.utcnow().isoformat(),
                    run_id,
                ),
            )
            equity_rows = [
                (run_id, str(d.date() if hasattr(d, "date") else d), float(v))
                for d, v in result.equity_curve.items()
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO backtest_equity (run_id, date, equity) "
                "VALUES (?, ?, ?)",
                equity_rows,
            )
            fills_rows = []
            seq = 0
            for f in result.fills:
                fills_rows.append(_fill_row(run_id, seq, f, rejected=None))
                seq += 1
            for r in result.rejections:
                fills_rows.append(_fill_row(run_id, seq, r, rejected=r.rejected_reason))
                seq += 1
            conn.executemany(
                "INSERT OR REPLACE INTO backtest_fills "
                "(run_id, seq, date, code, side, shares, price, cost, rejected) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                fills_rows,
            )

    def get_run(self, run_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM backtest_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            equity = conn.execute(
                "SELECT date, equity FROM backtest_equity WHERE run_id = ? ORDER BY date",
                (run_id,),
            ).fetchall()
            fills = conn.execute(
                "SELECT date, code, side, shares, price, cost, rejected FROM backtest_fills "
                "WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
        return {
            "id": row["id"],
            "config": json.loads(row["config_json"]),
            "summary": json.loads(row["summary_json"]) if row["summary_json"] else None,
            "status": row["status"],
            "error": row["error"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "equity_curve": [{"date": r["date"], "equity": r["equity"]} for r in equity],
            "fills": [dict(r) for r in fills],
        }

    def list_runs(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, config_json, summary_json, status, created_at "
                "FROM backtest_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items = []
        for r in rows:
            config = json.loads(r["config_json"])
            summary = json.loads(r["summary_json"]) if r["summary_json"] else None
            items.append({
                "run_id": r["id"],
                "status": r["status"],
                "strategy_type": config.get("strategy", {}).get("type", "unknown"),
                "universe_size": len(config.get("universe", [])),
                "start": config.get("config", {}).get("start", ""),
                "end": config.get("config", {}).get("end", ""),
                "created_at": r["created_at"],
                "sharpe": summary.get("sharpe") if summary else None,
                "total_return": summary.get("total_return") if summary else None,
            })
        return items

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]


def _fill_row(run_id: str, seq: int, f: Fill, rejected: str | None) -> tuple:
    return (
        run_id, seq,
        str(f.timestamp.date() if hasattr(f.timestamp, "date") else f.timestamp),
        f.code, f.side.value, int(f.shares), float(f.price), float(f.cost),
        rejected,
    )


def _jsonable(d: dict) -> dict:
    """Coerce non-JSON types (Timestamp, numpy floats) into JSON-safe primitives."""
    out = {}
    for k, v in d.items():
        if isinstance(v, pd.Timestamp):
            out[k] = v.isoformat()
        elif hasattr(v, "item"):  # numpy scalar
            out[k] = v.item()
        else:
            out[k] = v
    return out
