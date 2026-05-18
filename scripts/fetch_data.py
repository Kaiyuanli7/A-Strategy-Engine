"""
Prime the SQLite cache with 3 years of daily OHLCV for the demo universe.

By default tries real AKShare first; if all stocks fail (e.g., remote sandbox
without access to Chinese financial sites), falls back to synthetic data with
a loud warning. Pass --synthetic to skip the AKShare attempt entirely.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from astrategy.config import classify_board, is_st_name
from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader
from astrategy.data.synthetic import generate_synthetic_ohlcv
from astrategy.data.universe import DEMO_UNIVERSE


def _prime_synthetic(start: str, end: str) -> dict[str, int]:
    print(">>> SYNTHETIC DATA MODE — these are NOT real prices. <<<")
    cache = SQLiteCache()
    results: dict[str, int] = {}
    snapshot = datetime.utcnow().strftime("%Y-%m-%d")

    for code, name in DEMO_UNIVERSE:
        cache.upsert_stock_meta(code, name, classify_board(code), is_st_name(name))
        df = generate_synthetic_ohlcv(code, start, end)
        cache.delete_bars(code)
        n = cache.upsert_daily_bars(code, df)
        cache.record_fetch(code, start, end, n)
        results[code] = n
        print(f"  synth  {code} {name}  {n} rows")

    cache.upsert_index_constituents("DEMO", [c for c, _ in DEMO_UNIVERSE], snapshot)

    # Also prime fundamentals / valuation / sector / northbound (Phase 4 deps)
    from astrategy.data.loader import DataLoader
    loader = DataLoader(cache=cache)
    extras = loader.prime_extras_synthetic(
        [c for c, _ in DEMO_UNIVERSE], start, end,
    )
    if extras:
        sample = next(iter(extras.values()))
        print(f"  extras per stock: {sample}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true",
                        help="Skip AKShare and use synthetic data (for offline / sandboxed envs)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    start = "2023-05-18"
    end = "2026-05-18"
    print(f"Priming cache for {len(DEMO_UNIVERSE)} stocks, {start} → {end}")

    if args.synthetic:
        results = _prime_synthetic(start, end)
    else:
        loader = DataLoader()
        results = loader.prime_cache(DEMO_UNIVERSE, start=start, end=end)
        if all(n == 0 for n in results.values()):
            print("\nAll AKShare fetches failed (likely network policy blocking eastmoney/sina).")
            print("Falling back to synthetic data so the engine can be demonstrated.\n")
            results = _prime_synthetic(start, end)

    print("\n=== Fetch summary ===")
    total = 0
    for code, n in results.items():
        marker = "OK " if n > 100 else "!! "
        print(f"  {marker} {code}  {n:>5} rows")
        total += n
    print(f"\nTotal rows cached: {total}")
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
