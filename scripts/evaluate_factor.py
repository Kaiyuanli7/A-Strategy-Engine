"""End-to-end factor evaluation CLI.

Usage:
    python scripts/evaluate_factor.py \\
        --factor northbound_momentum \\
        --start 2023-05-01 --end 2025-12-31 \\
        --universe 000300 --horizon 20 --rebalance weekly \\
        --lookback 5

If the cache is empty, the script primes a synthetic CSI 300 universe so the
pipeline can be exercised offline. Pass --no-prime-if-empty to disable.

Outputs a JSON report under `data/evaluations/{factor}_{timestamp}.json` and
prints a one-screen summary (IC mean / IR / hit rate / quintile spread).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from astrategy.data.cache import SQLiteCache
from astrategy.data.loader import DataLoader
from astrategy.evaluation.runner import EvaluationConfig, evaluate_factor
from astrategy.factors import get_factor, list_factors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factor", required=True, help="Factor name (e.g. northbound_momentum)")
    parser.add_argument("--start", default="2023-05-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--universe", default="000300", help="Index code or 'all_cached'")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--rebalance", default="weekly", choices=["daily", "weekly", "monthly"])
    parser.add_argument("--lookback", type=int, default=None,
                        help="Override factor's default lookback (param)")
    parser.add_argument("--n-quintiles", type=int, default=5)
    parser.add_argument("--no-prime-if-empty", action="store_true",
                        help="Don't auto-prime synthetic universe when cache is empty")
    parser.add_argument("--n-members", type=int, default=120,
                        help="Synthetic universe size when auto-priming")
    parser.add_argument("--out-dir", default="data/evaluations")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cache = SQLiteCache()
    loader = DataLoader(cache=cache)

    if cache.all_meta_codes() == [] and not args.no_prime_if_empty:
        print(f"Cache is empty. Priming synthetic universe ({args.n_members} stocks, "
              f"{args.start} → {args.end}) — this is OFFLINE demo data, NOT real prices.")
        loader.prime_universe_synthetic(
            index_code=args.universe if args.universe.isdigit() else "000300",
            start=args.start,
            end=args.end,
            n_members=args.n_members,
        )

    factor_cls = get_factor(args.factor)
    if factor_cls is None:
        print(f"Unknown factor '{args.factor}'. Available:")
        for n in list_factors():
            print(f"  - {n}")
        return 2

    params: dict = {}
    if args.lookback is not None:
        params["lookback"] = args.lookback
    factor = factor_cls(**params)

    config = EvaluationConfig(
        start=args.start, end=args.end,
        universe=args.universe,
        horizon=args.horizon,
        rebalance=args.rebalance,
        n_quintiles=args.n_quintiles,
    )

    print(f"\nEvaluating {factor.name} (params={factor.params})")
    print(f"  universe={args.universe}  range={args.start} → {args.end}")
    print(f"  rebalance={args.rebalance}  horizon={args.horizon}")
    t0 = time.time()
    result = evaluate_factor(factor, cache, config)
    elapsed = time.time() - t0

    print(f"\n=== Result (computed in {elapsed:.1f}s) ===")
    print(f"  n_dates           {result.n_dates}")
    print(f"  n_stocks_avg      {result.n_stocks_avg:.1f}")
    print(f"  IC mean           {result.ic_summary['mean']:+.4f}")
    print(f"  IC std            {result.ic_summary['std']:.4f}")
    print(f"  IC IR             {result.ic_summary['ir']:+.3f}")
    print(f"  IC hit rate       {result.ic_summary['hit_rate'] * 100:.1f}%")
    print(f"  IC t-stat         {result.ic_summary['t_stat']:+.2f}  (n={result.ic_summary['n']})")
    print(f"  Long-short mean   {result.quintile_summary['long_short_mean']:+.4f}")
    print(f"  Long-short sharpe {result.quintile_summary['long_short_sharpe']:+.3f}")
    print(f"  LS total return   {result.quintile_summary['long_short_total_return']:+.2%}")
    print(f"  Monotonicity      {result.quintile_summary['monotonicity']:+.3f}")
    print(f"  Avg turnover      {result.quintile_summary['avg_turnover']:.2%}")
    print(f"  Decay (IC by horizon):")
    for _, row in result.decay.iterrows():
        print(f"    h={int(row['horizon']):>3}d   IC={row['ic_mean']:+.4f}   IR={row['ic_ir']:+.3f}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    out_path = out_dir / f"{factor.name}_{timestamp}.json"
    payload = {
        "factor": factor.name,
        "params": factor.params,
        "config": config.to_dict(),
        "n_dates": result.n_dates,
        "n_stocks_avg": result.n_stocks_avg,
        "ic_series": result.ic_series_dicts(),
        "ic_summary": result.ic_summary,
        "quintile_cum": result.quintile_cum_dicts(),
        "quintile_summary": result.quintile_summary,
        "decay": result.decay_dicts(),
    }
    out_path.write_text(json.dumps(payload, default=str, indent=2))
    print(f"\n  → wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
