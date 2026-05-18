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

    def __init__(self, request_sleep: float = 0.7):
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

    def get_daily_ohlcv(
        self,
        code: str,
        start: str,
        end: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        Daily OHLCV for a single stock, forward-adjusted by default.
        start/end accept YYYY-MM-DD or YYYYMMDD.
        Returns columns: date (str YYYY-MM-DD), open, high, low, close, volume, amount, pct_change, turnover.
        """
        start_compact = start.replace("-", "")
        end_compact = end.replace("-", "")

        self._sleep()
        df = self._call_with_retry(
            self._ak.stock_zh_a_hist,
            symbol=code,
            period="daily",
            start_date=start_compact,
            end_date=end_compact,
            adjust=adjust,
        )

        df = df.rename(columns=_OHLCV_RENAME)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        keep = ["date", "open", "high", "low", "close", "volume", "amount", "pct_change", "turnover"]
        df = df[[c for c in keep if c in df.columns]].copy()
        return df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
