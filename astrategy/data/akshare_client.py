"""Thin wrapper around AKShare with retries and column normalization."""

from __future__ import annotations

import logging
import time
from typing import Callable

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

log = logging.getLogger(__name__)


class AKShareError(RuntimeError):
    """Raised when AKShare returns invalid/empty data or all fallbacks fail."""


def _sina_symbol(code: str) -> str:
    """
    Some AKShare endpoints (sina/tencent) require an `sh`/`sz`/`bj` prefix
    on the 6-digit stock code. Returns e.g. 'sh600519', 'sz000001', 'bj430047'.
    """
    code = code.zfill(6)
    if code.startswith(("60", "68", "9")):
        return "sh" + code
    if code.startswith(("00", "30", "20")):
        return "sz" + code
    if code.startswith(("8", "4", "92")):
        return "bj" + code
    return "sh" + code  # default fallback


_OHLCV_RENAME = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "换手率": "turnover",
}


class AKShareClient:
    """
    Wrapper around AKShare with retry, empty-DataFrame detection,
    Chinese-to-English column renaming, and multiple fallback endpoints
    for index constituents (AKShare APIs drift across versions).
    """

    def __init__(self, request_sleep: float = 1.5):
        """
        request_sleep: pause between AKShare calls. Defaults to 1.5s — eastmoney's
        anti-bot drops mid-stream TCP connections when calls fire too rapidly.
        Drop to 0.5-0.7 only if you've confirmed your network handles burst load.
        """
        import akshare as ak
        self._ak = ak
        self._request_sleep = request_sleep

    def _sleep(self) -> None:
        if self._request_sleep > 0:
            time.sleep(self._request_sleep)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=16),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, AKShareError)),
        reraise=True,
    )
    def _call_with_retry(self, fn: Callable, *args, **kwargs) -> pd.DataFrame:
        df = fn(*args, **kwargs)
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise AKShareError(f"empty result from {fn.__name__}")
        return df

    def get_csi300_constituents(self) -> pd.DataFrame:
        """Return DataFrame with columns ['code', 'name'] for CSI 300 members."""
        attempts = [
            ("index_stock_cons_csindex", lambda: self._ak.index_stock_cons_csindex(symbol="000300")),
            ("index_stock_cons", lambda: self._ak.index_stock_cons(symbol="000300")),
            ("index_stock_cons_sina", lambda: self._ak.index_stock_cons_sina(symbol="000300")),
        ]
        last_err: Exception | None = None
        for name, fn in attempts:
            try:
                df = self._call_with_retry(fn)
                normalized = self._normalize_constituents(df)
                if not normalized.empty:
                    log.info("CSI300 constituents loaded via %s (%d rows)", name, len(normalized))
                    return normalized
            except Exception as e:
                log.warning("CSI300 endpoint %s failed: %s", name, e)
                last_err = e
                continue
        raise AKShareError(f"all CSI300 constituent endpoints failed; last error: {last_err}")

    @staticmethod
    def _normalize_constituents(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["code", "name"])

        code_candidates = ["成分券代码", "品种代码", "证券代码", "成份券代码", "code", "代码"]
        name_candidates = ["成分券名称", "品种名称", "证券名称", "成份券名称", "name", "名称"]

        code_col = next((c for c in code_candidates if c in df.columns), None)
        name_col = next((c for c in name_candidates if c in df.columns), None)
        if code_col is None or name_col is None:
            raise AKShareError(f"constituent schema unrecognized; columns {list(df.columns)}")

        out = pd.DataFrame({
            "code": df[code_col].astype(str).str.zfill(6),
            "name": df[name_col].astype(str),
        })
        return out.drop_duplicates(subset=["code"]).reset_index(drop=True)

    # ----- Alt-data sources (factor research) ------------------------------

    def get_northbound_holdings(self, code: str, start: str, end: str) -> pd.DataFrame:
        """
        Per-stock northbound (Stock Connect) holding history.

        Tries multiple AKShare endpoints because the name and signature have
        drifted across versions. Returns a tidy DataFrame with: date,
        holding_shares, holding_value, holding_pct, net_buy_shares, net_buy_value.

        Empty DataFrame if all endpoints fail; caller falls back to synthetic.
        """
        # Each tuple is (endpoint_name, callable that returns a DataFrame).
        # Signatures as of AKShare 1.18:
        #   stock_hsgt_individual_em(symbol=code) — per-stock history
        #   stock_individual_fund_flow(stock=code, market='sh'|'sz') — per-stock fund flow
        market = "sh" if code.startswith(("60", "68", "9")) else "sz"
        attempts = [
            ("stock_hsgt_individual_em",
                lambda: self._ak.stock_hsgt_individual_em(symbol=code)),
            ("stock_individual_fund_flow",
                lambda: self._ak.stock_individual_fund_flow(stock=code, market=market)),
        ]
        last_err: Exception | None = None
        for fn_name, call in attempts:
            fn = getattr(self._ak, fn_name, None)
            if fn is None:
                continue
            try:
                self._sleep()
                df = self._call_with_retry(call)
                norm = self._normalize_northbound(df, start, end)
                if not norm.empty:
                    log.info("northbound for %s via %s (%d rows)", code, fn_name, len(norm))
                    return norm
            except Exception as e:
                log.warning("northbound %s failed for %s: %s", fn_name, code, e)
                last_err = e
        log.warning("all northbound endpoints failed for %s; last err: %s", code, last_err)
        return pd.DataFrame(columns=[
            "date", "holding_shares", "holding_value", "holding_pct",
            "net_buy_shares", "net_buy_value",
        ])

    @staticmethod
    def _normalize_northbound(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        """Normalize AKShare's varying column schemas into our canonical layout."""
        if df is None or df.empty:
            return pd.DataFrame()
        renames = {
            "日期": "date", "持股日期": "date", "trade_date": "date",
            "持股数量": "holding_shares", "持股股数": "holding_shares",
            "持股市值": "holding_value", "持股市值（元）": "holding_value",
            "持股比例": "holding_pct", "占总股本比例": "holding_pct",
            "净买入金额": "net_buy_value", "净买入": "net_buy_value",
            "净买入股数": "net_buy_shares",
        }
        df = df.rename(columns=renames)
        if "date" not in df.columns:
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df[(df["date"] >= start) & (df["date"] <= end)].copy()
        for col in ("holding_shares", "holding_value", "holding_pct",
                    "net_buy_shares", "net_buy_value"):
            if col not in df.columns:
                df[col] = pd.NA
        keep = ["date", "holding_shares", "holding_value", "holding_pct",
                "net_buy_shares", "net_buy_value"]
        return df[keep].drop_duplicates("date").sort_values("date").reset_index(drop=True)

    def get_margin_detail(self, code: str, start: str, end: str) -> pd.DataFrame:
        """
        Per-stock margin (融资融券) detail for a single trading day.

        IMPORTANT: AKShare's SSE / SZSE margin endpoints return ALL stocks for
        ONE date, not one stock for a date range. To build a per-stock history
        you need to call this once per trading day in the desired range and
        filter to `code` each time. The current Sprint-2 factor library
        doesn't use margin data — Factor 1.3 (Margin Sentiment Divergence)
        lands in Sprint 2+, and the loader will be refactored then to do
        date-driven priming instead of per-stock.

        For now this returns a single-day snapshot from `start` so the smoke
        script can validate connectivity. Walk back up to 14 days looking
        for a date that actually has data (non-trading days return empty).

        Returns tidy DataFrame: date, financing_balance, short_balance,
        financing_buy_amount, financing_repay_amount, net_financing_change.
        """
        from datetime import datetime as _dt, timedelta as _td
        if code.startswith(("60", "68")):
            fn_name = "stock_margin_detail_sse"
        elif code.startswith(("00", "30")):
            fn_name = "stock_margin_detail_szse"
        else:
            log.info("margin: skipping non-SH/SZ code %s", code)
            return pd.DataFrame()
        fn = getattr(self._ak, fn_name, None)
        if fn is None:
            log.warning("margin: AKShare missing %s", fn_name)
            return pd.DataFrame()

        # Walk back up to 14 calendar days from `start` looking for a working
        # trading day. SSE/SZSE return empty / malformed dataframes on holidays.
        cur = _dt.strptime(start, "%Y-%m-%d").date()
        for _ in range(14):
            cur_str = cur.strftime("%Y%m%d")
            try:
                self._sleep()
                raw = fn(date=cur_str)
                norm = self._normalize_margin(raw, code,
                                              cur.strftime("%Y-%m-%d"),
                                              cur.strftime("%Y-%m-%d"))
                if not norm.empty:
                    return norm
            except Exception as e:
                log.debug("margin %s @ %s: %s", fn_name, cur_str, e)
            cur -= _td(days=1)
        log.warning("margin: no trading day with data in 14 days back from %s", start)
        return pd.DataFrame()

    @staticmethod
    def _normalize_margin(df: pd.DataFrame, code: str, start: str, end: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        renames = {
            "信用交易日期": "date", "日期": "date",
            "证券代码": "code", "标的证券代码": "code",
            "融资余额": "financing_balance",
            "融券余额": "short_balance",
            "融资买入额": "financing_buy_amount",
            "融资偿还额": "financing_repay_amount",
        }
        df = df.rename(columns=renames)
        if "code" in df.columns:
            df["code"] = df["code"].astype(str).str.zfill(6)
            df = df[df["code"] == code]
        if "date" not in df.columns or df.empty:
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df[(df["date"] >= start) & (df["date"] <= end)].copy()
        for c in ("financing_balance", "short_balance",
                  "financing_buy_amount", "financing_repay_amount"):
            if c not in df.columns:
                df[c] = pd.NA
        df["net_financing_change"] = df["financing_buy_amount"].astype(float) - df["financing_repay_amount"].astype(float)
        keep = ["date", "financing_balance", "short_balance",
                "financing_buy_amount", "financing_repay_amount",
                "net_financing_change"]
        return df[keep].drop_duplicates("date").sort_values("date").reset_index(drop=True)

    def get_lhb_disclosure(self, date: str) -> pd.DataFrame:
        """
        龙虎榜 (top buyer/seller seats) disclosure for a single date.

        Returns tidy DataFrame: code, date, seq, seat_name, seat_type,
        buy_amount, sell_amount, net_amount.

        Signature notes (AKShare 1.18):
        - stock_lhb_detail_em(start_date=, end_date=) — accepts a date range.
        - stock_lhb_jgstatistic_em(symbol='近一月'|'近三月'|...) — period only,
          no date range. Not used as a daily-disclosure fallback.
        """
        fn = getattr(self._ak, "stock_lhb_detail_em", None)
        if fn is None:
            log.warning("lhb: AKShare missing stock_lhb_detail_em")
            return pd.DataFrame()
        try:
            self._sleep()
            df = self._call_with_retry(
                lambda: fn(
                    start_date=date.replace("-", ""),
                    end_date=date.replace("-", ""),
                )
            )
            return self._normalize_lhb(df)
        except Exception as e:
            log.warning("lhb stock_lhb_detail_em failed for %s: %s", date, e)
            return pd.DataFrame(columns=[
                "code", "date", "seq", "seat_name", "seat_type",
                "buy_amount", "sell_amount", "net_amount",
            ])

    @staticmethod
    def _normalize_lhb(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        renames = {
            "代码": "code", "证券代码": "code",
            "上榜日": "date", "交易日期": "date",
            "营业部名称": "seat_name", "机构名称": "seat_name",
            "买入金额": "buy_amount", "买入额": "buy_amount",
            "卖出金额": "sell_amount", "卖出额": "sell_amount",
            "净买额": "net_amount", "净买入额": "net_amount",
        }
        df = df.rename(columns=renames)
        if "code" not in df.columns or "date" not in df.columns:
            return pd.DataFrame()
        df["code"] = df["code"].astype(str).str.zfill(6)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        for c in ("buy_amount", "sell_amount", "net_amount"):
            if c not in df.columns:
                df[c] = pd.NA
        if "seat_name" not in df.columns:
            df["seat_name"] = "unknown"
        # Heuristic seat-type classification
        def classify(name: str) -> str:
            if pd.isna(name):
                return "retail"
            s = str(name)
            if "机构专用" in s or "QFII" in s or "RQFII" in s:
                return "institutional"
            if "营业部" in s or "证券" in s:
                return "hot_money"
            return "retail"
        df["seat_type"] = df["seat_name"].apply(classify)
        # Sequence per (code, date)
        df = df.sort_values(["code", "date", "net_amount"], ascending=[True, True, False])
        df["seq"] = df.groupby(["code", "date"]).cumcount()
        keep = ["code", "date", "seq", "seat_name", "seat_type",
                "buy_amount", "sell_amount", "net_amount"]
        return df[keep].reset_index(drop=True)

    def get_limit_pool(self, date: str, direction: str = "up") -> pd.DataFrame:
        """
        Limit-up (`zt_pool`) or limit-down (`dt_pool`) stocks for a date.

        Returns tidy DataFrame: code, date, direction, consecutive_days,
        is_first, turnover_pct.
        """
        fn_name = "stock_zt_pool_em" if direction == "up" else "stock_dt_pool_em"
        fn = getattr(self._ak, fn_name, None)
        if fn is None:
            log.warning("limit pool: AKShare missing %s", fn_name)
            return pd.DataFrame()
        try:
            self._sleep()
            df = self._call_with_retry(fn, date=date.replace("-", ""))
        except Exception as e:
            log.warning("limit pool %s failed: %s", fn_name, e)
            return pd.DataFrame()
        return self._normalize_limit_pool(df, date, direction)

    @staticmethod
    def _normalize_limit_pool(df: pd.DataFrame, date: str, direction: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        renames = {
            "代码": "code", "股票代码": "code",
            "连板数": "consecutive_days", "几天几板": "consecutive_days",
            "换手率": "turnover_pct",
            "首次封板时间": "first_seal_time",
        }
        df = df.rename(columns=renames)
        if "code" not in df.columns:
            return pd.DataFrame()
        df["code"] = df["code"].astype(str).str.zfill(6)
        df["date"] = date
        df["direction"] = direction
        if "consecutive_days" not in df.columns:
            df["consecutive_days"] = 1
        df["is_first"] = (df["consecutive_days"] <= 1).astype(int)
        if "turnover_pct" not in df.columns:
            df["turnover_pct"] = pd.NA
        keep = ["code", "date", "direction", "consecutive_days", "is_first", "turnover_pct"]
        return df[keep].reset_index(drop=True)

    def get_analyst_ratings(self, code: str) -> pd.DataFrame:
        """Analyst rating snapshot. Best-effort; returns empty DataFrame on failure."""
        fn = getattr(self._ak, "stock_analyst_rank_em", None)
        if fn is None:
            return pd.DataFrame()
        try:
            self._sleep()
            df = self._call_with_retry(fn, symbol=code)
        except Exception as e:
            log.warning("analyst ratings failed for %s: %s", code, e)
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        renames = {"日期": "report_date", "评级": "rating", "目标价": "target_price",
                   "EPS预测": "eps_estimate", "营收预测": "revenue_estimate"}
        df = df.rename(columns=renames)
        if "report_date" not in df.columns:
            return pd.DataFrame()
        df["report_date"] = pd.to_datetime(df["report_date"]).dt.strftime("%Y-%m-%d")
        for c in ("rating", "target_price", "eps_estimate", "revenue_estimate"):
            if c not in df.columns:
                df[c] = pd.NA
        return df[["report_date", "rating", "target_price", "eps_estimate", "revenue_estimate"]].copy()

    def get_quarterly_fundamentals(self, code: str) -> pd.DataFrame:
        """
        Quarterly fundamentals via AKShare's `stock_financial_abstract`.

        AKShare returns indicator-wide format:
            选项 | 指标         | 20260331 | 20251231 | 20250930 | ...
            --- | ------------ | -------- | -------- | -------- | ---
            盈利能力 | 净资产收益率 | 15.2    | 14.8    | 14.5    | ...

        We pivot to long format (one row per (code, report_date)) and rename
        a curated subset of indicators to our schema columns. announce_date
        is estimated as report_date + 45 days (AKShare doesn't surface the
        actual announce date per stock; 45 days is a conservative buffer).

        Returns columns:
            report_date, announce_date, roe_ttm, eps_ttm,
            operating_cash_flow_ttm, net_income_ttm, revenue_yoy, net_profit_yoy.
        PE/PB/PS columns are NOT populated (the endpoint doesn't expose them);
        upsert_fundamentals tolerates missing values.

        Returns empty DataFrame if the fetch fails or the response is unrecognized.
        """
        try:
            self._sleep()
            df = self._call_with_retry(self._ak.stock_financial_abstract, symbol=code)
        except Exception as e:
            log.warning("fundamentals fetch failed for %s: %s", code, e)
            return pd.DataFrame()
        return self._normalize_quarterly_fundamentals(df)

    # Map of Chinese 指标 → our schema column. We accept multiple aliases
    # for ROE since some AKShare versions use "(摊薄)" while others use
    # "(加权)" or have no suffix at all.
    _FUNDAMENTALS_INDICATOR_MAP: dict[str, str] = {
        "净资产收益率": "roe_ttm",
        "净资产收益率(摊薄)": "roe_ttm",
        "净资产收益率(加权)": "roe_ttm",
        "净资产收益率-摊薄": "roe_ttm",
        "净资产收益率-加权": "roe_ttm",
        "摊薄每股收益": "eps_ttm",
        "基本每股收益": "eps_ttm",
        "每股收益": "eps_ttm",
        "经营活动产生的现金流量净额": "operating_cash_flow_ttm",
        "经营现金流量净额": "operating_cash_flow_ttm",
        "归属于母公司股东的净利润": "net_income_ttm",
        "归属母公司股东净利润": "net_income_ttm",
        "净利润": "net_income_ttm",
        "营业总收入同比增长": "revenue_yoy",
        "营业收入同比增长率": "revenue_yoy",
        "营业总收入同比增长率": "revenue_yoy",
        "归属于母公司股东的净利润同比增长": "net_profit_yoy",
        "归属母公司股东的净利润同比": "net_profit_yoy",
        "净利润同比增长率": "net_profit_yoy",
    }

    @classmethod
    def _normalize_quarterly_fundamentals(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Pivot AKShare's indicator-wide format to one row per quarter."""
        if df is None or df.empty:
            return pd.DataFrame()
        if "指标" not in df.columns:
            log.warning("fundamentals: unrecognized response shape; columns=%s",
                        list(df.columns)[:8])
            return pd.DataFrame()
        # Date columns are anything matching YYYYMMDD (8 digits).
        date_cols = [c for c in df.columns
                     if isinstance(c, str) and len(c) == 8 and c.isdigit()]
        if not date_cols:
            log.warning("fundamentals: no YYYYMMDD date columns in response")
            return pd.DataFrame()

        # Aggregate by indicator: keep the FIRST row per indicator that
        # matches our schema (the endpoint sometimes ships duplicate indicator
        # names across 选项 categories).
        wanted = cls._FUNDAMENTALS_INDICATOR_MAP
        per_indicator: dict[str, pd.Series] = {}
        for _, row in df.iterrows():
            ind = str(row["指标"]).strip()
            schema_col = wanted.get(ind)
            if schema_col is None or schema_col in per_indicator:
                continue
            per_indicator[schema_col] = row[date_cols]

        if not per_indicator:
            return pd.DataFrame()

        # Pivot: rows = report dates (parsed from YYYYMMDD), cols = our schema
        wide = pd.DataFrame(per_indicator)
        wide.index = pd.to_datetime(wide.index, format="%Y%m%d", errors="coerce")
        wide = wide[wide.index.notna()].sort_index()
        wide.index.name = "report_date"
        out = wide.reset_index()
        out["report_date"] = out["report_date"].dt.strftime("%Y-%m-%d")
        out["announce_date"] = (
            pd.to_datetime(out["report_date"]) + pd.Timedelta(days=45)
        ).dt.strftime("%Y-%m-%d")
        # Ensure all schema cols exist even if missing in this stock's response
        for col in ("roe_ttm", "eps_ttm", "operating_cash_flow_ttm",
                    "net_income_ttm", "revenue_yoy", "net_profit_yoy"):
            if col not in out.columns:
                out[col] = pd.NA
        keep = ["report_date", "announce_date", "roe_ttm", "eps_ttm",
                "operating_cash_flow_ttm", "net_income_ttm",
                "revenue_yoy", "net_profit_yoy"]
        return out[keep].reset_index(drop=True)

    def get_daily_ohlcv(
        self,
        code: str,
        start: str,
        end: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        Daily OHLCV for a single stock, forward-adjusted by default.

        Tries multiple AKShare endpoints in order because eastmoney's anti-bot
        sometimes drops the TCP mid-stream (RemoteDisconnected). Order is:
        1. `stock_zh_a_hist` — eastmoney (richest columns)
        2. `stock_zh_a_hist_tx` — Tencent (works when eastmoney 403s)
        3. `stock_zh_a_daily` — sina (last resort; needs sh/sz/bj prefix)

        Returns columns: date (str YYYY-MM-DD), open, high, low, close, volume,
        amount, pct_change, turnover. Some columns may be missing on
        non-primary endpoints; downstream code uses .get(col) so this is fine.
        """
        start_compact = start.replace("-", "")
        end_compact = end.replace("-", "")
        last_err: Exception | None = None

        attempts: list[tuple[str, callable]] = [
            ("stock_zh_a_hist", lambda: self._ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_compact, end_date=end_compact, adjust=adjust,
            )),
            ("stock_zh_a_hist_tx", lambda: self._ak.stock_zh_a_hist_tx(
                symbol=_sina_symbol(code),
                start_date=start_compact, end_date=end_compact, adjust=adjust,
            )),
            ("stock_zh_a_daily", lambda: self._ak.stock_zh_a_daily(
                symbol=_sina_symbol(code),
                start_date=start_compact, end_date=end_compact, adjust=adjust,
            )),
        ]

        for name, call in attempts:
            fn = getattr(self._ak, name, None)
            if fn is None:
                continue
            try:
                self._sleep()
                df = self._call_with_retry(call)
                # Sina returns date as the index; reset it before renaming.
                if "date" not in df.columns and df.index.name in ("date", None):
                    df = df.reset_index().rename(columns={df.index.name or "index": "date"})
                df = df.rename(columns=_OHLCV_RENAME)
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

                # Different endpoints return different columns:
                #   eastmoney: open, high, low, close, volume, amount, pct_change, turnover
                #   tencent:   open, high, low, close, amount        (NO volume)
                #   sina:      open, high, low, close, volume, amount, turnover
                # When volume is missing but amount + close are present, derive
                # volume ≈ amount / close. Rough (real VWAP ≠ close) but good
                # enough to keep downstream suspension detection from firing
                # on every cell.
                if "volume" not in df.columns and "amount" in df.columns and "close" in df.columns:
                    df["volume"] = (df["amount"].astype(float)
                                    / df["close"].astype(float).where(df["close"] > 0, other=pd.NA))
                if "amount" not in df.columns and "volume" in df.columns and "close" in df.columns:
                    df["amount"] = df["volume"].astype(float) * df["close"].astype(float)

                keep = ["date", "open", "high", "low", "close", "volume",
                        "amount", "pct_change", "turnover"]
                df = df[[c for c in keep if c in df.columns]].copy()
                return df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
            except Exception as e:
                log.warning("OHLCV via %s failed for %s: %s", name, code, e)
                last_err = e
        raise AKShareError(f"all OHLCV endpoints failed for {code}; last error: {last_err}")
