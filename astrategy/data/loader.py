"""High-level data loader — cache-first, fetches from AKShare on miss."""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
from tqdm import tqdm

from astrategy.config import classify_board, is_st_name
from astrategy.data.akshare_client import AKShareClient
from astrategy.data.cache import SQLiteCache

log = logging.getLogger(__name__)


class DataLoader:
    def __init__(
        self,
        client: AKShareClient | None = None,
        cache: SQLiteCache | None = None,
    ):
        self.client = client or AKShareClient()
        self.cache = cache or SQLiteCache()

    def prime_cache(
        self,
        codes_with_names: list[tuple[str, str]],
        start: str,
        end: str,
        force_refresh: bool = False,
    ) -> dict[str, int]:
        """
        Fetch and cache OHLCV + metadata for the given list of (code, name) pairs.
        Returns dict mapping code -> row count fetched.
        """
        snapshot = datetime.utcnow().strftime("%Y-%m-%d")
        results: dict[str, int] = {}

        for code, name in tqdm(codes_with_names, desc="Fetching OHLCV", unit="stock"):
            board = classify_board(code)
            st = is_st_name(name)
            self.cache.upsert_stock_meta(code, name, board, st)

            existing = self.cache.get_daily_bars(code, start, end)
            if not force_refresh and not existing.empty and len(existing) >= 100:
                log.info("cache hit %s (%d rows)", code, len(existing))
                results[code] = len(existing)
                continue

            try:
                df = self.client.get_daily_ohlcv(code, start, end, adjust="qfq")
            except Exception as e:
                log.error("fetch failed for %s: %s", code, e)
                results[code] = 0
                continue

            # qfq prices drift over time — always overwrite the full range
            self.cache.delete_bars(code)
            n = self.cache.upsert_daily_bars(code, df)
            self.cache.record_fetch(code, start, end, n)
            results[code] = n
            log.info("fetched %s: %d rows", code, n)

        all_codes = [c for c, _ in codes_with_names]
        self.cache.upsert_index_constituents("DEMO", all_codes, snapshot)

        return results

    def load_bars(
        self, codes: list[str], start: str, end: str
    ) -> dict[str, pd.DataFrame]:
        """Load cached bars for multiple stocks. Returns {code: DataFrame indexed by date}."""
        out: dict[str, pd.DataFrame] = {}
        for code in codes:
            df = self.cache.get_daily_bars(code, start, end)
            if df.empty:
                log.warning("no cached bars for %s in %s..%s", code, start, end)
                continue
            df = df.set_index("date").sort_index()
            out[code] = df
        return out

    def load_meta(self, codes: list[str]) -> dict[str, dict]:
        return {c: self.cache.get_stock_meta(c) for c in codes if self.cache.get_stock_meta(c)}
