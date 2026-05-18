"""Fit composite weights via Optuna with optional walk-forward OOS evaluation.

Usage
-----
Single-window fit (no OOS check):

    python scripts/optimize_weights.py \\
        --factors northbound_momentum,earnings_quality,momentum_skip \\
        --start 2022-01-01 --end 2024-12-31 \\
        --universe 000300 --rebalance weekly --horizon 20 \\
        --n-trials 100 --l2-lambda 0.5

Walk-forward (IS fit per window → OOS evaluate):

    python scripts/optimize_weights.py \\
        --factors northbound_momentum,earnings_quality,momentum_skip \\
        --start 2022-01-01 --end 2024-12-31 \\
        --walk-forward --train-months 12 --test-months 3 \\
        --n-trials 100 --l2-lambda 0.5

The walk-forward variant satisfies CLAUDE.md §3 hard rule #2 (NEVER optimize
in-sample only). It dumps a JSON report to `data/walk_forward/` with per-window
IS Sharpe, OOS Sharpe, and the IS-OOS gap for overfitting detection.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from astrategy.composites.optuna_fit import (
    _composite_long_short_returns,
    _sharpe,
    fit_composite_weights_optuna,
)
from astrategy.data.cache import SQLiteCache
from astrategy.data.universes import load_universe
from astrategy.evaluation.runner import (
    EvaluationConfig,
    _forward_returns,
    _load_bars,
    _rebalance_dates,
    _resolve_universe,
)
from astrategy.factors import get_factor, list_factors
from astrategy.factors.base import FactorContext


def _compute_per_factor_scores_and_returns(
    factor_specs: list[tuple[str, dict]],
    cache: SQLiteCache,
    start: str,
    end: str,
    universe: str,
    rebalance: str,
    horizon: int,
) -> tuple[dict, dict]:
    """Pre-compute factor scores + forward returns for an IS window."""
    config = EvaluationConfig(
        start=start, end=end, universe=universe,
        horizon=horizon, rebalance=rebalance,
    )
    rebalance_dates = _rebalance_dates(start, end, rebalance)

    # Load bars wide enough for forward returns
    bars_end = (pd.Timestamp(end) + pd.Timedelta(days=horizon * 2 + 14)).strftime("%Y-%m-%d")
    bars_by_code = _load_bars(cache, start, bars_end)

    per_factor: dict = {}
    forward_by_date: dict = {}

    for name, params in factor_specs:
        factor_cls = get_factor(name)
        if factor_cls is None:
            raise ValueError(f"unknown factor: {name}")
        valid = {p.name for p in factor_cls.param_specs()}
        params = {k: v for k, v in params.items() if k in valid}
        factor = factor_cls(**params)
        per_factor[name] = {}
        for d in rebalance_dates:
            universe_codes = _resolve_universe(cache, universe, d.strftime("%Y-%m-%d"))
            if not universe_codes:
                continue
            ctx = FactorContext(cache=cache, universe=universe_codes, as_of=d)
            scores = factor.compute(ctx)
            if scores is not None and not scores.empty:
                per_factor[name][d] = scores
            if d not in forward_by_date:
                fwd = _forward_returns(bars_by_code, universe_codes, d, horizon)
                if not fwd.empty:
                    forward_by_date[d] = fwd
    return per_factor, forward_by_date


def _parse_factors_arg(s: str) -> list[tuple[str, dict]]:
    """`name1,name2:param=val,name3` → list of (name, params)."""
    out: list[tuple[str, dict]] = []
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            name, rest = chunk.split(":", 1)
            params: dict = {}
            for kv in rest.split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    try:
                        params[k.strip()] = int(v)
                    except ValueError:
                        try:
                            params[k.strip()] = float(v)
                        except ValueError:
                            params[k.strip()] = v.strip()
            out.append((name, params))
        else:
            out.append((chunk, {}))
    return out


def _format_window(idx, train_s, train_e, test_s, test_e, is_sharpe, oos_sharpe, weights):
    gap = is_sharpe - oos_sharpe
    flag = "⚠ OVERFIT" if abs(gap) > 0.5 else "ok"
    return (
        f"  Window {idx:>2}: train {train_s}→{train_e}, test {test_s}→{test_e}\n"
        f"    IS Sharpe = {is_sharpe:+.3f},  OOS Sharpe = {oos_sharpe:+.3f},  "
        f"gap = {gap:+.3f}  [{flag}]\n"
        f"    weights = "
        + ", ".join(f"{n}={w:+.3f}" for n, w in weights.items())
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factors", required=True,
                        help="Comma-separated factor names. Add params with "
                             "factor:param=val;param=val notation.")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--universe", default="000300")
    parser.add_argument("--rebalance", default="weekly", choices=["daily", "weekly", "monthly"])
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--n-trials", type=int, default=100)
    parser.add_argument("--l2-lambda", type=float, default=0.5)
    parser.add_argument("--max-weight-abs", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--walk-forward", action="store_true",
                        help="Fit per-window with OOS evaluation.")
    parser.add_argument("--train-months", type=int, default=12)
    parser.add_argument("--test-months", type=int, default=3)
    parser.add_argument("--out-dir", default="data/walk_forward")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    factor_specs = _parse_factors_arg(args.factors)
    if not factor_specs:
        parser.error("--factors yielded no factors")

    cache = SQLiteCache()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.walk_forward:
        # Single-window fit
        print(f"\nFitting composite weights on {args.start} → {args.end}")
        print(f"  factors: {[n for n, _ in factor_specs]}")
        print(f"  universe={args.universe}  rebalance={args.rebalance}  horizon={args.horizon}")
        print(f"  n_trials={args.n_trials}  l2_lambda={args.l2_lambda}  max_weight_abs={args.max_weight_abs}\n")
        t0 = time.time()
        per_factor, forward = _compute_per_factor_scores_and_returns(
            factor_specs, cache, args.start, args.end,
            args.universe, args.rebalance, args.horizon,
        )
        print(f"  Pre-computed in {time.time() - t0:.1f}s "
              f"({sum(len(s) for s in per_factor.values())} factor-date scores)")
        fit = fit_composite_weights_optuna(
            per_factor, forward,
            n_trials=args.n_trials, l2_lambda=args.l2_lambda,
            max_weight_abs=args.max_weight_abs, seed=args.seed,
        )
        print(f"\n=== Result ===")
        print(f"  IS Long-Short Sharpe: {fit.is_sharpe:+.3f}")
        print(f"  weights:")
        for name, w in fit.weights.items():
            print(f"    {name:30s} {w:+.4f}")
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        out_path = out_dir / f"fit_{timestamp}.json"
        out_path.write_text(json.dumps({
            **asdict(fit),
            "factors": factor_specs,
            "config": vars(args),
        }, indent=2))
        print(f"\n  → wrote {out_path}")
        return 0

    # Walk-forward
    print(f"\nWalk-forward optimization on {args.start} → {args.end}")
    print(f"  factors: {[n for n, _ in factor_specs]}")
    print(f"  train_months={args.train_months}  test_months={args.test_months}\n")

    # Build rolling windows
    s = pd.Timestamp(args.start)
    e = pd.Timestamp(args.end)
    windows: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    cur = s
    while True:
        train_end = cur + pd.DateOffset(months=args.train_months)
        test_end = train_end + pd.DateOffset(months=args.test_months)
        if test_end > e + pd.DateOffset(days=1):
            break
        windows.append((cur, train_end, train_end, test_end))
        cur = cur + pd.DateOffset(months=args.test_months)
    if not windows:
        print("  No windows fit. Widen --start/--end or shrink --train/--test months.")
        return 1
    print(f"  {len(windows)} windows\n")

    results = []
    for i, (train_s, train_e, test_s, test_e) in enumerate(windows):
        ts, te = train_s.strftime("%Y-%m-%d"), train_e.strftime("%Y-%m-%d")
        os_s, os_e = test_s.strftime("%Y-%m-%d"), test_e.strftime("%Y-%m-%d")

        per_factor_is, fwd_is = _compute_per_factor_scores_and_returns(
            factor_specs, cache, ts, te, args.universe, args.rebalance, args.horizon,
        )
        if not per_factor_is or not fwd_is:
            print(f"  Window {i}: insufficient IS data; skipping.")
            continue
        fit = fit_composite_weights_optuna(
            per_factor_is, fwd_is,
            n_trials=args.n_trials, l2_lambda=args.l2_lambda,
            max_weight_abs=args.max_weight_abs, seed=args.seed,
        )

        # OOS: re-evaluate composite on OOS scores with the fitted weights
        per_factor_oos, fwd_oos = _compute_per_factor_scores_and_returns(
            factor_specs, cache, os_s, os_e,
            args.universe, args.rebalance, args.horizon,
        )
        if per_factor_oos and fwd_oos:
            ls_oos = _composite_long_short_returns(
                fit.weights, per_factor_oos, fwd_oos,
            )
            oos_sharpe = _sharpe(ls_oos)
        else:
            oos_sharpe = float("nan")

        print(_format_window(i, ts, te, os_s, os_e, fit.is_sharpe, oos_sharpe, fit.weights))
        results.append({
            "window_idx": i,
            "train_start": ts, "train_end": te,
            "test_start": os_s, "test_end": os_e,
            "is_sharpe": fit.is_sharpe,
            "oos_sharpe": float(oos_sharpe) if np.isfinite(oos_sharpe) else None,
            "weights": fit.weights,
        })

    # Aggregate
    is_avg = np.mean([r["is_sharpe"] for r in results]) if results else 0.0
    oos_vals = [r["oos_sharpe"] for r in results if r["oos_sharpe"] is not None]
    oos_avg = float(np.mean(oos_vals)) if oos_vals else 0.0
    gap = is_avg - oos_avg
    print(f"\n=== Aggregate ===")
    print(f"  avg IS Sharpe:  {is_avg:+.3f}")
    print(f"  avg OOS Sharpe: {oos_avg:+.3f}")
    print(f"  IS - OOS gap:   {gap:+.3f}  ({'OVERFIT' if abs(gap) > 0.5 else 'OK'})")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    payload = {
        "config": vars(args),
        "factors": factor_specs,
        "windows": results,
        "aggregate": {
            "is_sharpe": is_avg,
            "oos_sharpe": oos_avg,
            "is_oos_gap": gap,
            "overfit": bool(abs(gap) > 0.5),
        },
    }
    out_path = out_dir / f"walkforward_{timestamp}.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  → wrote {out_path}")

    # Also persist to SQLite so the frontend /walkforward page can read it.
    try:
        from astrategy.api.storage import RunStorage
        storage = RunStorage()
        run_id = storage.new_walk_forward_run({"factors": factor_specs, "args": vars(args)})
        storage.save_walk_forward_result(run_id, payload)
        print(f"  → persisted to DB as run_id={run_id}")
    except Exception as e:
        print(f"  (DB persistence skipped: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
