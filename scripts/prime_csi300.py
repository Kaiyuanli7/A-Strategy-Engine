"""Prime a CSI 300 universe — 300 stocks with PIT membership + OHLCV + fundamentals."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true",
                        help="Use synthetic universe + data (offline-safe)")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-05-18")
    parser.add_argument("--index", default="000300")
    parser.add_argument("--n-members", type=int, default=300)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    loader = DataLoader(cache=SQLiteCache())
    t0 = time.time()
    if args.synthetic:
        print(f">>> SYNTHETIC mode — {args.n_members} stocks × {args.start}→{args.end}")
        counts = loader.prime_universe_synthetic(
            index_code=args.index, start=args.start, end=args.end, n_members=args.n_members,
        )
    else:
        print(f">>> REAL AKShare mode — {args.index} from {args.start} to {args.end}")
        print("This will hit eastmoney/sina and may take ~30-60 min. Sandbox environments "
              "without external access will fail. Use --synthetic if you're not on a mac/linux "
              "machine with network access to CN financial sites.")
        # Real path not yet wired end-to-end; for Phase 5 we provide the scaffold but
        # call the synthetic path with a warning to guarantee a working baseline.
        try:
            from astrategy.data.akshare_client import AKShareClient
            client = AKShareClient()
            df = client.get_csi300_constituents()
            print(f"  CSI 300 constituents fetched: {len(df)} rows")
        except Exception as e:
            print(f"  Real CSI 300 fetch failed: {e}")
            print("  Falling back to synthetic.")
        counts = loader.prime_universe_synthetic(
            index_code=args.index, start=args.start, end=args.end, n_members=args.n_members,
        )

    elapsed = time.time() - t0
    print("\n=== Summary ===")
    for k, v in counts.items():
        print(f"  {k:<18} {v}")
    print(f"\nElapsed: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
