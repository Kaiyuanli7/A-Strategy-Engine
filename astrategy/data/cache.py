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

-- Phase 4 additions ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS fundamentals (
    code                     TEXT NOT NULL,
    report_date              TEXT NOT NULL,
    announce_date            TEXT NOT NULL,
    pe_ttm                   REAL,
    pb                       REAL,
    ps_ttm                   REAL,
    roe_ttm                  REAL,
    revenue_yoy              REAL,
    net_profit_yoy           REAL,
    eps_ttm                  REAL,
    operating_cash_flow_ttm  REAL,
    net_income_ttm           REAL,
    PRIMARY KEY (code, report_date)
);
CREATE INDEX IF NOT EXISTS idx_fund_announce ON fundamentals(code, announce_date);

CREATE TABLE IF NOT EXISTS valuation_daily (
    code      TEXT NOT NULL,
    date      TEXT NOT NULL,
    pe_ttm    REAL,
    pb        REAL,
    ps_ttm    REAL,
    mkt_cap   REAL,
    float_cap REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_val_date ON valuation_daily(date);

CREATE TABLE IF NOT EXISTS sector_classification (
    code           TEXT NOT NULL,
    sw_l1_code     TEXT,
    sw_l1_name     TEXT NOT NULL,
    sw_l2_code     TEXT,
    sw_l2_name     TEXT,
    snapshot_date  TEXT NOT NULL,
    PRIMARY KEY (code, snapshot_date)
);

CREATE TABLE IF NOT EXISTS northbound_daily (
    code           TEXT NOT NULL,
    date           TEXT NOT NULL,
    holding_shares REAL,
    holding_value  REAL,
    holding_pct    REAL,
    net_buy_shares REAL,
    net_buy_value  REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_north_date ON northbound_daily(date);

-- Phase 5: point-in-time index membership ------------------------------------

CREATE TABLE IF NOT EXISTS index_constituents_pit (
    index_code     TEXT NOT NULL,
    member_code    TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    expiry_date    TEXT,
    PRIMARY KEY (index_code, member_code, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_const_pit_eff ON index_constituents_pit(index_code, effective_date);
CREATE INDEX IF NOT EXISTS idx_const_pit_exp ON index_constituents_pit(index_code, expiry_date);

-- Factor-research alt-data tables -------------------------------------------

CREATE TABLE IF NOT EXISTS margin_daily (
    code                   TEXT NOT NULL,
    date                   TEXT NOT NULL,
    financing_balance      REAL,
    short_balance          REAL,
    financing_buy_amount   REAL,
    financing_repay_amount REAL,
    net_financing_change   REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_margin_date ON margin_daily(date);

CREATE TABLE IF NOT EXISTS lhb_disclosure (
    code          TEXT NOT NULL,
    date          TEXT NOT NULL,
    seq           INTEGER NOT NULL,
    seat_name     TEXT NOT NULL,
    seat_type     TEXT NOT NULL,
    buy_amount    REAL,
    sell_amount   REAL,
    net_amount    REAL,
    PRIMARY KEY (code, date, seq)
);
CREATE INDEX IF NOT EXISTS idx_lhb_date ON lhb_disclosure(date);
CREATE INDEX IF NOT EXISTS idx_lhb_seat_type ON lhb_disclosure(seat_type);

CREATE TABLE IF NOT EXISTS limit_pool (
    code              TEXT NOT NULL,
    date              TEXT NOT NULL,
    direction         TEXT NOT NULL,
    consecutive_days  INTEGER,
    is_first          INTEGER,
    turnover_pct      REAL,
    PRIMARY KEY (code, date, direction)
);
CREATE INDEX IF NOT EXISTS idx_limit_date ON limit_pool(date);

CREATE TABLE IF NOT EXISTS analyst_estimates (
    code              TEXT NOT NULL,
    report_date       TEXT NOT NULL,
    source            TEXT NOT NULL,
    eps_estimate      REAL,
    revenue_estimate  REAL,
    rating            TEXT,
    target_price      REAL,
    fetched_at        TEXT NOT NULL,
    PRIMARY KEY (code, report_date, source)
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
            # Backfill columns on databases created before the schema bump
            # (fresh DBs already have them via the CREATE TABLE above).
            self._migrate_add_column(conn, "fundamentals", "operating_cash_flow_ttm", "REAL")
            self._migrate_add_column(conn, "fundamentals", "net_income_ttm", "REAL")

    @staticmethod
    def _migrate_add_column(conn: sqlite3.Connection, table: str, col: str, col_type: str) -> None:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            # Column already exists — idempotent no-op
            pass

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

    # ----- Phase 4: fundamentals + valuation + sector + northbound -----

    @staticmethod
    def _opt(v) -> float | None:
        if v is None or pd.isna(v):
            return None
        return float(v)

    def upsert_fundamentals(self, code: str, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        for _, r in df.iterrows():
            rows.append((
                code, str(r["report_date"]), str(r["announce_date"]),
                self._opt(r.get("pe_ttm")), self._opt(r.get("pb")),
                self._opt(r.get("ps_ttm")), self._opt(r.get("roe_ttm")),
                self._opt(r.get("revenue_yoy")), self._opt(r.get("net_profit_yoy")),
                self._opt(r.get("eps_ttm")),
                self._opt(r.get("operating_cash_flow_ttm")),
                self._opt(r.get("net_income_ttm")),
            ))
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO fundamentals "
                "(code, report_date, announce_date, pe_ttm, pb, ps_ttm, roe_ttm, "
                "revenue_yoy, net_profit_yoy, eps_ttm, "
                "operating_cash_flow_ttm, net_income_ttm) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def get_fundamentals(self, code: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        """Return fundamentals ordered by announce_date (point-in-time)."""
        sql = (
            "SELECT report_date, announce_date, pe_ttm, pb, ps_ttm, roe_ttm, "
            "revenue_yoy, net_profit_yoy, eps_ttm, "
            "operating_cash_flow_ttm, net_income_ttm "
            "FROM fundamentals WHERE code = ?"
        )
        params: list = [code]
        if start:
            sql += " AND announce_date >= ?"
            params.append(start)
        if end:
            sql += " AND announce_date <= ?"
            params.append(end)
        sql += " ORDER BY announce_date"
        with self._conn() as conn:
            df = pd.read_sql_query(sql, conn, params=tuple(params))
        if not df.empty:
            df["announce_date"] = pd.to_datetime(df["announce_date"])
            df["report_date"] = pd.to_datetime(df["report_date"])
        return df

    def upsert_valuation_daily(self, code: str, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        for _, r in df.iterrows():
            rows.append((
                code, str(r["date"]),
                self._opt(r.get("pe_ttm")), self._opt(r.get("pb")),
                self._opt(r.get("ps_ttm")), self._opt(r.get("mkt_cap")),
                self._opt(r.get("float_cap")),
            ))
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO valuation_daily "
                "(code, date, pe_ttm, pb, ps_ttm, mkt_cap, float_cap) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def get_valuation_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT date, pe_ttm, pb, ps_ttm, mkt_cap, float_cap "
                "FROM valuation_daily WHERE code = ? AND date BETWEEN ? AND ? "
                "ORDER BY date",
                conn,
                params=(code, start, end),
            )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def latest_market_cap(self, code: str) -> float | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mkt_cap FROM valuation_daily WHERE code = ? "
                "ORDER BY date DESC LIMIT 1",
                (code,),
            ).fetchone()
        return float(row["mkt_cap"]) if row and row["mkt_cap"] is not None else None

    def upsert_sector(
        self, code: str, sw_l1_name: str,
        sw_l1_code: str | None = None,
        sw_l2_name: str | None = None,
        sw_l2_code: str | None = None,
        snapshot_date: str | None = None,
    ) -> None:
        snapshot = snapshot_date or datetime.utcnow().strftime("%Y-%m-%d")
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sector_classification "
                "(code, sw_l1_code, sw_l1_name, sw_l2_code, sw_l2_name, snapshot_date) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code, sw_l1_code, sw_l1_name, sw_l2_code, sw_l2_name, snapshot),
            )

    def get_sectors(self, codes: list[str]) -> dict[str, dict]:
        """Return {code: {sw_l1_name, sw_l1_code, sw_l2_name, sw_l2_code}} for latest snapshot."""
        if not codes:
            return {}
        placeholders = ",".join("?" * len(codes))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT code, sw_l1_code, sw_l1_name, sw_l2_code, sw_l2_name, snapshot_date "
                f"FROM sector_classification WHERE code IN ({placeholders}) "
                f"ORDER BY code, snapshot_date DESC",
                codes,
            ).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            if r["code"] not in out:
                out[r["code"]] = {
                    "sw_l1_code": r["sw_l1_code"],
                    "sw_l1_name": r["sw_l1_name"],
                    "sw_l2_code": r["sw_l2_code"],
                    "sw_l2_name": r["sw_l2_name"],
                }
        return out

    def distinct_sectors(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT sw_l1_name FROM sector_classification "
                "WHERE sw_l1_name IS NOT NULL ORDER BY sw_l1_name"
            ).fetchall()
        return [r["sw_l1_name"] for r in rows]

    def upsert_northbound(self, code: str, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        for _, r in df.iterrows():
            rows.append((
                code, str(r["date"]),
                self._opt(r.get("holding_shares")), self._opt(r.get("holding_value")),
                self._opt(r.get("holding_pct")),
                self._opt(r.get("net_buy_shares")), self._opt(r.get("net_buy_value")),
            ))
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO northbound_daily "
                "(code, date, holding_shares, holding_value, holding_pct, "
                "net_buy_shares, net_buy_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def get_northbound(self, code: str, start: str, end: str) -> pd.DataFrame:
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT date, holding_shares, holding_value, holding_pct, "
                "net_buy_shares, net_buy_value FROM northbound_daily "
                "WHERE code = ? AND date BETWEEN ? AND ? ORDER BY date",
                conn,
                params=(code, start, end),
            )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    # ----- Phase 5: point-in-time index membership ------------------------

    def upsert_index_member(
        self,
        index_code: str,
        member_code: str,
        effective_date: str,
        expiry_date: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO index_constituents_pit "
                "(index_code, member_code, effective_date, expiry_date) "
                "VALUES (?, ?, ?, ?)",
                (index_code, member_code, effective_date, expiry_date),
            )

    def upsert_index_members(
        self, index_code: str, rows: list[tuple[str, str, str | None]]
    ) -> int:
        """Bulk insert. rows = list of (member_code, effective_date, expiry_date)."""
        if not rows:
            return 0
        payload = [(index_code, c, eff, exp) for c, eff, exp in rows]
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO index_constituents_pit "
                "(index_code, member_code, effective_date, expiry_date) "
                "VALUES (?, ?, ?, ?)",
                payload,
            )
        return len(payload)

    def get_index_constituents_as_of(
        self, index_code: str, as_of_date: str
    ) -> list[str]:
        """Codes where effective_date <= as_of_date < (expiry_date OR ∞)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT member_code FROM index_constituents_pit "
                "WHERE index_code = ? AND effective_date <= ? "
                "AND (expiry_date IS NULL OR expiry_date > ?) "
                "ORDER BY member_code",
                (index_code, as_of_date, as_of_date),
            ).fetchall()
        return [r["member_code"] for r in rows]

    def get_index_members_ever(self, index_code: str) -> list[str]:
        """All codes that were ever in the index (union over time)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT member_code FROM index_constituents_pit "
                "WHERE index_code = ? ORDER BY member_code",
                (index_code,),
            ).fetchall()
        return [r["member_code"] for r in rows]

    def get_index_member_history(self, index_code: str) -> pd.DataFrame:
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT member_code, effective_date, expiry_date "
                "FROM index_constituents_pit WHERE index_code = ? "
                "ORDER BY effective_date, member_code",
                conn,
                params=(index_code,),
            )
        return df

    def all_meta_codes(self) -> list[str]:
        """All stock codes with metadata cached. Used by /health and as a fallback universe."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT code FROM stock_meta WHERE board != 'index' ORDER BY code"
            ).fetchall()
        return [r["code"] for r in rows]

    def bars_as_of(
        self, code: str, as_of: str, lookback_days: int = 60,
    ) -> pd.DataFrame:
        """
        OHLCV bars strictly BEFORE as_of, indexed by date ascending.

        Used by technical factors that need a trailing price window. PIT
        discipline: factor on day t looks at close[<t].
        """
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT date, open, high, low, close, volume, amount, pct_change, turnover "
                "FROM daily_bars WHERE code = ? AND date < ? "
                "AND date >= date(?, '-' || ? || ' days') ORDER BY date",
                conn,
                params=(code, as_of, as_of, lookback_days),
            )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def fundamentals_as_of(self, code: str, as_of: str) -> dict | None:
        """Most recent fundamentals row with announce_date < as_of."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT report_date, announce_date, pe_ttm, pb, ps_ttm, roe_ttm, "
                "revenue_yoy, net_profit_yoy, eps_ttm, "
                "operating_cash_flow_ttm, net_income_ttm "
                "FROM fundamentals WHERE code = ? AND announce_date < ? "
                "ORDER BY announce_date DESC LIMIT 1",
                (code, as_of),
            ).fetchone()
        return dict(row) if row else None

    def recent_fundamentals_as_of(
        self, code: str, as_of: str, k: int = 2,
    ) -> pd.DataFrame:
        """Last `k` fundamentals rows with announce_date < as_of, DESC by announce_date."""
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT report_date, announce_date, pe_ttm, pb, ps_ttm, roe_ttm, "
                "revenue_yoy, net_profit_yoy, eps_ttm, "
                "operating_cash_flow_ttm, net_income_ttm "
                "FROM fundamentals WHERE code = ? AND announce_date < ? "
                "ORDER BY announce_date DESC LIMIT ?",
                conn,
                params=(code, as_of, k),
            )
        if not df.empty:
            df["announce_date"] = pd.to_datetime(df["announce_date"])
            df["report_date"] = pd.to_datetime(df["report_date"])
        return df

    def valuation_history_as_of(
        self, code: str, as_of: str, lookback_days: int = 756,
    ) -> pd.DataFrame:
        """
        Valuation rows strictly BEFORE as_of, ascending. Default ~3 trading years.
        Used by valuation-percentile factors.
        """
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT date, pe_ttm, pb, ps_ttm, mkt_cap, float_cap "
                "FROM valuation_daily WHERE code = ? AND date < ? "
                "AND date >= date(?, '-' || ? || ' days') ORDER BY date",
                conn,
                params=(code, as_of, as_of, lookback_days),
            )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def northbound_as_of(
        self, code: str, as_of: str, lookback_days: int = 30,
    ) -> pd.DataFrame:
        """
        Per-stock northbound history strictly BEFORE as_of (point-in-time).

        Used by factors that look at a trailing window of flow. The factor sees
        rows with date < as_of and date >= as_of - lookback_days. Returned in
        ascending date order.
        """
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT date, holding_shares, holding_value, holding_pct, "
                "net_buy_shares, net_buy_value FROM northbound_daily "
                "WHERE code = ? AND date < ? AND date >= date(?, '-' || ? || ' days') "
                "ORDER BY date",
                conn,
                params=(code, as_of, as_of, lookback_days),
            )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def valuation_as_of(self, code: str, as_of: str) -> dict | None:
        """Most recent valuation row strictly BEFORE as_of."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT date, pe_ttm, pb, ps_ttm, mkt_cap, float_cap FROM valuation_daily "
                "WHERE code = ? AND date < ? ORDER BY date DESC LIMIT 1",
                (code, as_of),
            ).fetchone()
        return dict(row) if row else None

    def cross_sectional_valuation_as_of(
        self, codes: list[str], as_of: str,
    ) -> pd.DataFrame:
        """
        For each code, the latest valuation_daily row with date < as_of.

        Returns DataFrame indexed by code with columns pe_ttm, pb, ps_ttm,
        mkt_cap, float_cap. Missing codes are simply absent from the result.
        """
        if not codes:
            return pd.DataFrame()
        placeholders = ",".join("?" * len(codes))
        with self._conn() as conn:
            df = pd.read_sql_query(
                f"""
                SELECT v.code AS code, v.pe_ttm, v.pb, v.ps_ttm, v.mkt_cap, v.float_cap
                FROM valuation_daily v
                JOIN (
                    SELECT code, MAX(date) AS max_date
                    FROM valuation_daily
                    WHERE code IN ({placeholders}) AND date < ?
                    GROUP BY code
                ) latest ON v.code = latest.code AND v.date = latest.max_date
                """,
                conn,
                params=(*codes, as_of),
            )
        if df.empty:
            return df
        return df.set_index("code")

    def upsert_margin_daily(self, code: str, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        for _, r in df.iterrows():
            rows.append((
                code, str(r["date"]),
                self._opt(r.get("financing_balance")),
                self._opt(r.get("short_balance")),
                self._opt(r.get("financing_buy_amount")),
                self._opt(r.get("financing_repay_amount")),
                self._opt(r.get("net_financing_change")),
            ))
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO margin_daily "
                "(code, date, financing_balance, short_balance, financing_buy_amount, "
                "financing_repay_amount, net_financing_change) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def get_margin_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        with self._conn() as conn:
            df = pd.read_sql_query(
                "SELECT date, financing_balance, short_balance, financing_buy_amount, "
                "financing_repay_amount, net_financing_change FROM margin_daily "
                "WHERE code = ? AND date BETWEEN ? AND ? ORDER BY date",
                conn,
                params=(code, start, end),
            )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def upsert_lhb_rows(self, rows: list[dict]) -> int:
        """Bulk insert 龙虎榜 disclosure rows. Each dict needs: code, date, seq, seat_name, seat_type, buy_amount, sell_amount, net_amount."""
        if not rows:
            return 0
        payload = [
            (
                r["code"], str(r["date"]), int(r["seq"]),
                r["seat_name"], r["seat_type"],
                self._opt(r.get("buy_amount")),
                self._opt(r.get("sell_amount")),
                self._opt(r.get("net_amount")),
            )
            for r in rows
        ]
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO lhb_disclosure "
                "(code, date, seq, seat_name, seat_type, buy_amount, sell_amount, net_amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                payload,
            )
        return len(payload)

    def get_lhb(
        self, code: str, start: str, end: str, seat_type: str | None = None,
    ) -> pd.DataFrame:
        sql = (
            "SELECT date, seq, seat_name, seat_type, buy_amount, sell_amount, net_amount "
            "FROM lhb_disclosure WHERE code = ? AND date BETWEEN ? AND ?"
        )
        params: list = [code, start, end]
        if seat_type:
            sql += " AND seat_type = ?"
            params.append(seat_type)
        sql += " ORDER BY date, seq"
        with self._conn() as conn:
            df = pd.read_sql_query(sql, conn, params=tuple(params))
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def upsert_limit_pool_rows(self, rows: list[dict]) -> int:
        """Bulk insert limit-up/down pool rows. Each dict: code, date, direction, consecutive_days, is_first, turnover_pct."""
        if not rows:
            return 0
        payload = [
            (
                r["code"], str(r["date"]), r["direction"],
                int(r["consecutive_days"]) if r.get("consecutive_days") is not None else None,
                int(bool(r.get("is_first"))) if r.get("is_first") is not None else None,
                self._opt(r.get("turnover_pct")),
            )
            for r in rows
        ]
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO limit_pool "
                "(code, date, direction, consecutive_days, is_first, turnover_pct) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                payload,
            )
        return len(payload)

    def get_limit_pool(
        self, start: str, end: str, direction: str | None = None,
    ) -> pd.DataFrame:
        sql = (
            "SELECT code, date, direction, consecutive_days, is_first, turnover_pct "
            "FROM limit_pool WHERE date BETWEEN ? AND ?"
        )
        params: list = [start, end]
        if direction:
            sql += " AND direction = ?"
            params.append(direction)
        sql += " ORDER BY date, code"
        with self._conn() as conn:
            df = pd.read_sql_query(sql, conn, params=tuple(params))
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def upsert_analyst_estimates(self, code: str, source: str, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        now = datetime.utcnow().isoformat()
        rows = []
        for _, r in df.iterrows():
            rows.append((
                code, str(r["report_date"]), source,
                self._opt(r.get("eps_estimate")),
                self._opt(r.get("revenue_estimate")),
                r.get("rating"),
                self._opt(r.get("target_price")),
                now,
            ))
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO analyst_estimates "
                "(code, report_date, source, eps_estimate, revenue_estimate, rating, "
                "target_price, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def query_universe(
        self,
        boards: list[str] | None = None,
        exclude_st: bool = True,
        market_cap_min: float | None = None,
        market_cap_max: float | None = None,
        sectors_l1: list[str] | None = None,
        only_codes: list[str] | None = None,
    ) -> list[str]:
        """Filter the universe by metadata + latest market cap + sector."""
        clauses = ["1=1"]
        params: list = []
        if boards:
            clauses.append("m.board IN (" + ",".join("?" * len(boards)) + ")")
            params.extend(boards)
        if exclude_st:
            clauses.append("m.is_st = 0")
        if only_codes:
            clauses.append("m.code IN (" + ",".join("?" * len(only_codes)) + ")")
            params.extend(only_codes)
        if sectors_l1:
            clauses.append(
                "m.code IN (SELECT code FROM sector_classification WHERE sw_l1_name IN ("
                + ",".join("?" * len(sectors_l1)) + "))"
            )
            params.extend(sectors_l1)
        # Latest market cap per code
        if market_cap_min is not None or market_cap_max is not None:
            mc_clauses = []
            mc_params: list = []
            if market_cap_min is not None:
                mc_clauses.append("v.mkt_cap >= ?")
                mc_params.append(market_cap_min)
            if market_cap_max is not None:
                mc_clauses.append("v.mkt_cap <= ?")
                mc_params.append(market_cap_max)
            clauses.append(
                "m.code IN (SELECT code FROM valuation_daily v WHERE "
                + " AND ".join(mc_clauses)
                + " AND date = (SELECT MAX(date) FROM valuation_daily v2 WHERE v2.code = v.code))"
            )
            params.extend(mc_params)
        sql = (
            "SELECT DISTINCT m.code FROM stock_meta m WHERE "
            + " AND ".join(clauses)
            + " ORDER BY m.code"
        )
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [r["code"] for r in rows]
