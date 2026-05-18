"""High-level data loader — cache-first, fetches from AKShare on miss."""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
from tqdm import tqdm

from astrategy.config import classify_board, is_st_name
from astrategy.data.akshare_client import AKShareClient
from astrategy.data.cache import SQLiteCache
from astrategy.data.universes import KNOWN_INDICES as KNOWN_INDEX_NAME

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

    def prime_index_ohlcv(
        self,
        index_code: str,
        start: str,
        end: str,
        synthetic: bool = False,
    ) -> int:
        """Cache OHLCV for a market index (e.g. 000300). Synthetic or real."""
        if synthetic:
            from astrategy.data.synthetic import generate_synthetic_market_index
            df = generate_synthetic_market_index(index_code, start, end)
        else:
            try:
                df = self.client.get_daily_ohlcv(index_code, start, end, adjust="qfq")
            except Exception as e:
                log.error("real index OHLCV fetch failed for %s: %s; falling back to synthetic", index_code, e)
                from astrategy.data.synthetic import generate_synthetic_market_index
                df = generate_synthetic_market_index(index_code, start, end)

        # Reuse stock_meta with a sentinel board
        self.cache.upsert_stock_meta(index_code, KNOWN_INDEX_NAME.get(index_code, index_code), "index", False)
        self.cache.delete_bars(index_code)
        n = self.cache.upsert_daily_bars(index_code, df)
        self.cache.record_fetch(index_code, start, end, n)
        return n

    def prime_universe_synthetic(
        self,
        index_code: str = "000300",
        start: str = "2021-01-01",
        end: str = "2026-05-18",
        n_members: int = 300,
    ) -> dict[str, int]:
        """
        Populate a synthetic CSI-300-style universe end-to-end:
            - simulated quarterly turnover index membership
            - OHLCV + fundamentals + valuation + northbound for ALL members ever
            - market index OHLCV (`000300` by default)
        Returns {table: row count} for verification.
        """
        from astrategy.config import classify_board, is_st_name
        from astrategy.data.synthetic import (
            generate_synthetic_fundamentals,
            generate_synthetic_index_history,
            generate_synthetic_northbound,
            generate_synthetic_ohlcv,
            generate_synthetic_valuation_daily,
            synthetic_anchor_for,
            synthetic_sector_for,
        )

        # 1. Build PIT membership table
        history = generate_synthetic_index_history(index_code, start, end, n_members=n_members)
        rows = list(history[["member_code", "effective_date", "expiry_date"]].itertuples(index=False, name=None))
        # Replace pd.NA with None for SQLite
        rows = [(c, eff, None if pd.isna(exp) else exp) for (c, eff, exp) in rows]
        self.cache.upsert_index_members(index_code, rows)

        all_members = sorted({c for c, _, _ in rows})
        log.info("synthetic universe: %d unique members ever in %s", len(all_members), index_code)

        counts = {"members": len(all_members), "bars": 0, "fundamentals": 0,
                  "valuation": 0, "northbound": 0, "sectors": 0}

        # 2. Per-member: OHLCV + fundamentals + valuation + northbound + sector + meta
        for code in tqdm(all_members, desc="Priming synth universe", unit="stock"):
            # Synthetic name; classify_board fails for non-numeric codes — use "main_sh" as default
            board = classify_board(code) if code.isdigit() else "synth"
            self.cache.upsert_stock_meta(code, code, board, False)

            anchor = synthetic_anchor_for(code)
            # Vary start_price by anchor's mkt_cap / 1e9 → keeps shares roughly stable
            ohlcv = generate_synthetic_ohlcv(
                code, start, end,
                start_price=float(max(5.0, min(200.0, anchor["mkt_cap"] / 1e10))),
            )
            self.cache.delete_bars(code)
            counts["bars"] += self.cache.upsert_daily_bars(code, ohlcv)

            counts["fundamentals"] += self.cache.upsert_fundamentals(
                code, generate_synthetic_fundamentals(code, start, end)
            )
            ohlcv_str = ohlcv.assign(date=ohlcv["date"].astype(str))
            counts["valuation"] += self.cache.upsert_valuation_daily(
                code, generate_synthetic_valuation_daily(code, start, end, ohlcv_str)
            )
            counts["northbound"] += self.cache.upsert_northbound(
                code, generate_synthetic_northbound(code, start, end)
            )

            sec = synthetic_sector_for(code)
            self.cache.upsert_sector(
                code, sw_l1_name=sec["sw_l1_name"], sw_l1_code=sec.get("sw_l1_code"),
            )
            counts["sectors"] += 1

        # 3. Market index
        counts["index_bars"] = self.prime_index_ohlcv(index_code, start, end, synthetic=True)

        return counts

    def prime_extras_synthetic(
        self,
        codes: list[str],
        start: str,
        end: str,
    ) -> dict[str, dict[str, int]]:
        """
        Populate fundamentals + valuation + sector + northbound with synthetic
        data. Used in sandboxed envs where AKShare is unreachable.

        Returns {code: {table_name: row_count}} for verification.
        """
        from astrategy.data.synthetic import (
            generate_synthetic_fundamentals,
            generate_synthetic_northbound,
            generate_synthetic_sector,
            generate_synthetic_valuation_daily,
        )
        results: dict[str, dict[str, int]] = {}
        for code in codes:
            ohlcv = self.cache.get_daily_bars(code, start, end)
            ohlcv_for_val = (
                ohlcv.assign(date=ohlcv["date"].astype(str)) if not ohlcv.empty else None
            )

            f = generate_synthetic_fundamentals(code, start, end)
            v = generate_synthetic_valuation_daily(code, start, end, ohlcv_for_val)
            n = generate_synthetic_northbound(code, start, end)
            sec = generate_synthetic_sector(code)

            self.cache.upsert_fundamentals(code, f)
            self.cache.upsert_valuation_daily(code, v)
            self.cache.upsert_northbound(code, n)
            self.cache.upsert_sector(
                code,
                sw_l1_name=sec["sw_l1_name"],
                sw_l1_code=sec.get("sw_l1_code"),
            )
            results[code] = {
                "fundamentals": len(f),
                "valuation_daily": len(v),
                "northbound_daily": len(n),
                "sector": 1,
            }
        return results
