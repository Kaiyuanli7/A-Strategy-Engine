"""SQLite cache for OHLCV bars, stock metadata, and index constituents."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_bars (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      REAL NOT NULL,
    amount      REAL,
    pct_change  REAL,
    turnover    REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_bars_date ON daily_bars(date);

CREATE TABLE IF NOT EXISTS stock_meta (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    board        TEXT NOT NULL,
    is_st        INTEGER NOT NULL,
    listing_date TEXT,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_constituents (
    index_code     TEXT NOT NULL,
    member_code    TEXT NOT NULL,
    snapshot_date  TEXT NOT NULL,
    PRIMARY KEY (index_code, member_code, snapshot_date)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    code        TEXT NOT NULL,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    row_count   INTEGER NOT NULL,
    PRIMARY KEY (code, end_date)
);
"""


class SQLiteCache:
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
            conn.executescript(SCHEMA)

    def upsert_daily_bars(self, code: str, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        for _, r in df.iterrows():
            def opt(col: str) -> float | None:
                v = r.get(col)
                if v is None or pd.isna(v):
                    return None
                return float(v)

            rows.append((
                code,
                str(r["date"]),
                float(r["open"]),
                float(r["high"]),
                float(r["low"]),
                float(r["close"]),
                float(r["volume"]),
                opt("amount"),
                opt("pct_change"),
                opt("turnover"),
            ))
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO daily_bars "
                "(code, date, open, high, low, close, volume, amount, pct_change, turnover) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def delete_bars(self, code: str) -> None:
        """Wipe all bars for a stock (used when re-fetching qfq history)."""
        with self._conn() as conn:
            conn.execute("DELETE FROM daily_bars WHERE code = ?", (code,))

    def get_daily_bars(self, code: str, start: str, end: str) -> pd.DataFrame:
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT date, open, high, low, close, volume, amount, pct_change, turnover "
                "FROM daily_bars WHERE code = ? AND date BETWEEN ? AND ? ORDER BY date",
                conn,
                params=(code, start, end),
            )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def upsert_stock_meta(
        self,
        code: str,
        name: str,
        board: str,
        is_st: bool,
        listing_date: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO stock_meta (code, name, board, is_st, listing_date, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code, name, board, int(is_st), listing_date, datetime.utcnow().isoformat()),
            )

    def get_stock_meta(self, code: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM stock_meta WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else None

    def upsert_index_constituents(
        self, index_code: str, codes: list[str], snapshot_date: str
    ) -> None:
        rows = [(index_code, c, snapshot_date) for c in codes]
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO index_constituents (index_code, member_code, snapshot_date) "
                "VALUES (?, ?, ?)",
                rows,
            )

    def get_index_constituents(self, index_code: str) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT member_code FROM index_constituents WHERE index_code = ? "
                "ORDER BY member_code",
                (index_code,),
            ).fetchall()
        return [r["member_code"] for r in rows]

    def record_fetch(self, code: str, start: str, end: str, row_count: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO fetch_log (code, start_date, end_date, fetched_at, row_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (code, start, end, datetime.utcnow().isoformat(), row_count),
            )

    def last_fetch(self, code: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM fetch_log WHERE code = ? ORDER BY fetched_at DESC LIMIT 1",
                (code,),
            ).fetchone()
        return dict(row) if row else None
