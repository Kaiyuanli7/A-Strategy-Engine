"""Prime a CSI 300 universe — real OHLCV + alt-data, synthetic fallback when needed.

Default (real mode) fetches the live CSI 300 constituents from AKShare, then
primes real qfq OHLCV for each member, and best-effort real northbound per
stock. Fundamentals + valuation + sector are STILL synthetic — their real
fetchers aren't wired yet. The script labels which tables hold real vs
synthetic data so nothing gets mistaken for actual signal.

`--synthetic` skips AKShare entirely (offline mode).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from astrategy.config import classify_board, is_st_name
from astrategy.data.akshare_client import AKShareClient
from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader


def _prime_real(loader: DataLoader, args) -> dict:
    """
    Real-data path.
    - REAL: CSI 300 constituents, daily OHLCV (qfq), northbound per stock
            (best-effort, falls back per-code on failure)
    - SYNTHETIC (no real fetcher wired yet): fundamentals, valuation_daily,
            sector_classification

    Returns a counts dict labeling each table as 'real' or 'synthetic'.
    """
    print(f">>> REAL AKShare mode — {args.index} from {args.start} to {args.end}")
    print("  Network calls to eastmoney/sina. ~30-60 min depending on bandwidth.")
    print("  --synthetic skips this entirely if you're offline.\n")

    client = AKShareClient()

    # 1. Real constituents
    try:
        members_df = client.get_csi300_constituents()
    except Exception as e:
        print(f"  CSI 300 constituents fetch failed: {e}")
        print("  Aborting real-mode prime — re-run with --synthetic if you need a working cache.")
        return {"members": 0}
    codes_with_names = list(zip(members_df["code"].tolist(), members_df["name"].tolist()))
    print(f"  ✓ Constituents: {len(codes_with_names)} stocks (real)\n")

    counts = {"members": len(codes_with_names)}

    # 2. PIT membership: current snapshot only — historical add/drop history is a
    #    Sprint-5+ deliverable. effective_date = args.start so backtests starting
    #    from then see today's roster as the entire universe.
    pit_rows = [(c, args.start, None) for c, _ in codes_with_names]
    n_pit = loader.cache.upsert_index_members(args.index, pit_rows)
    counts["pit_rows"] = n_pit
    print(f"  ✓ PIT membership: upserted {n_pit} rows (effective_date={args.start}, expiry=None)")

    # 3. Real OHLCV via cache-first prime_cache
    print(f"\n  → Priming real OHLCV for {len(codes_with_names)} stocks "
          f"({args.start} → {args.end})...")
    ohlcv_results = loader.prime_cache(
        codes_with_names, start=args.start, end=args.end,
    )
    rows_total = sum(ohlcv_results.values())
    n_ok = sum(1 for n in ohlcv_results.values() if n > 100)
    counts["bars_total"] = rows_total
    counts["bars_ok_stocks"] = n_ok
    counts["bars_failed_stocks"] = len(codes_with_names) - n_ok
    print(f"  ✓ OHLCV: {rows_total} rows across {n_ok}/{len(codes_with_names)} stocks (real)")

    # 4. Best-effort real northbound per stock
    print(f"\n  → Priming real northbound per stock (best-effort)...")
    nb_results = loader.prime_northbound_individual(
        codes=[c for c, _ in codes_with_names],
        start=args.start, end=args.end,
    )
    nb_rows = sum(nb_results.values())
    nb_ok = sum(1 for n in nb_results.values() if n > 30)
    counts["northbound_total"] = nb_rows
    counts["northbound_ok_stocks"] = nb_ok
    real_nb = nb_ok > 0
    print(f"  {'✓' if real_nb else '✗'} Northbound: {nb_rows} rows across "
          f"{nb_ok}/{len(codes_with_names)} stocks ({'real' if real_nb else 'synthetic fallback below'})")

    # 5. Real fundamentals via AKShare stock_financial_abstract
    print(f"\n  → Priming real quarterly fundamentals...")
    codes_only = [c for c, _ in codes_with_names]
    fund_results = loader.prime_fundamentals(codes_only)
    fund_total = sum(fund_results.values())
    fund_ok = sum(1 for n in fund_results.values() if n >= 4)
    counts["fundamentals_real_total"] = fund_total
    counts["fundamentals_real_ok_stocks"] = fund_ok
    real_fund = fund_ok > len(codes_only) * 0.5
    print(f"  {'✓' if real_fund else '✗'} Fundamentals: {fund_total} rows across "
          f"{fund_ok}/{len(codes_only)} stocks "
          f"({'real' if real_fund else 'partial — many stocks missing fundamentals'})")

    # 5b. Derive real daily PE / PB / PS from fundamentals + close prices
    if real_fund:
        print(f"\n  → Deriving real daily PE / PB / PS from fundamentals + bars...")
        val_results = loader.backfill_valuation_daily_from_fundamentals(
            codes_only, args.start, args.end,
        )
        val_total = sum(val_results.values())
        val_ok = sum(1 for n in val_results.values() if n > 100)
        counts["valuation_real_total"] = val_total
        counts["valuation_real_ok_stocks"] = val_ok
        real_val = val_ok > len(codes_only) * 0.3
        print(f"  {'✓' if real_val else '⚠'} Daily PE/PB/PS: {val_total} rows across "
              f"{val_ok}/{len(codes_only)} stocks ({'real' if real_val else 'partial'})")
    else:
        real_val = False

    # 6. Synthetic fill-in for tables without a real fetcher yet.
    # Skip tables we've already populated with real data so we don't clobber.
    skip = {"fundamentals"}
    if real_nb:
        skip.add("northbound_daily")
    if real_val:
        skip.add("valuation_daily")
    print(f"\n  → Filling in synthetic data for the remaining tables...")
    extras = loader.prime_extras_synthetic(
        codes_only, args.start, args.end, skip_tables=frozenset(skip),
    )
    counts["sector_synth"] = sum(e["sector"] for e in extras.values())
    if not real_val:
        counts["valuation_synth"] = sum(e["valuation_daily"] for e in extras.values())
        print(f"  ⚠ valuation_daily is SYNTHETIC (real derivation needs fundamentals).")
    else:
        print(f"  ✓ valuation_daily was derived from real fundamentals + close.")
    print(f"  ⚠ sector classification still SYNTHETIC (real fetcher in Sprint 5+).")

    # 6. Index OHLCV (real)
    try:
        n_idx = loader.prime_index_ohlcv(args.index, args.start, args.end, synthetic=False)
        counts["index_bars_real"] = n_idx
        print(f"\n  ✓ Index OHLCV ({args.index}): {n_idx} rows (real)")
    except Exception as e:
        print(f"\n  ✗ Index OHLCV fetch failed: {e}; using synthetic.")
        n_idx = loader.prime_index_ohlcv(args.index, args.start, args.end, synthetic=True)
        counts["index_bars_synth"] = n_idx

    return counts


def _prime_synthetic(loader: DataLoader, args) -> dict:
    print(f">>> SYNTHETIC mode — {args.n_members} stocks × {args.start} → {args.end}")
    print("  No AKShare calls. Cache is populated with deterministic seed-based data.")
    print("  These numbers are MEANINGLESS as factor evaluation — for engine testing only.\n")
    return loader.prime_universe_synthetic(
        index_code=args.index, start=args.start, end=args.end, n_members=args.n_members,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true",
                        help="Skip AKShare entirely; deterministic synthetic data only.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--index", default="000300")
    parser.add_argument("--n-members", type=int, default=300,
                        help="Synthetic-mode only: number of stocks to generate.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    loader = DataLoader(cache=SQLiteCache())
    t0 = time.time()
    counts = _prime_synthetic(loader, args) if args.synthetic else _prime_real(loader, args)
    elapsed = time.time() - t0

    print("\n=== Summary ===")
    for k, v in counts.items():
        print(f"  {k:<24} {v}")
    print(f"\nElapsed: {elapsed:.1f}s")

    # Hard fail-fast: if we are in real mode but got no real OHLCV at all,
    # exit non-zero so the user notices.
    if not args.synthetic and counts.get("bars_total", 0) == 0:
        print("\nNo real OHLCV cached. Check network access to eastmoney/sina; "
              "or use --synthetic for offline mode.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
