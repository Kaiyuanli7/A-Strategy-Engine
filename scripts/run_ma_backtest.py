"""Phase 1 deliverable: dual-MA crossover backtest on the demo universe."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from astrategy.data.loader import DataLoader
from astrategy.data.universe import DEMO_UNIVERSE
from astrategy.engine.backtest import Backtester, BacktestConfig
from astrategy.strategies.ma_cross import DualMACrossStrategy


def _format_metrics(s: dict, period: tuple[str, str], universe_n: int) -> str:
    def pct(x: float) -> str:
        return f"{x*100:.2f}%"

    def money(x: float) -> str:
        return f"¥{x:,.0f}"

    mdd_peak = s["max_drawdown_peak"]
    mdd_trough = s["max_drawdown_trough"]
    mdd_dates = ""
    if mdd_peak is not None and mdd_trough is not None:
        mdd_dates = f" (peak {mdd_peak.date()} → trough {mdd_trough.date()})"

    return "\n".join([
        "=" * 60,
        "Dual MA Crossover Backtest — Phase 1 Deliverable",
        "=" * 60,
        f"Period:            {period[0]} → {period[1]}",
        f"Universe:          {universe_n} stocks (CSI 300 subset)",
        f"Initial Capital:   {money(s['initial_equity'])}",
        f"Final Equity:      {money(s['final_equity'])}",
        f"Total Return:      {pct(s['total_return'])}",
        f"Annualized Return: {pct(s['annualized_return'])}",
        f"Annualized Vol:    {pct(s['annualized_vol'])}",
        f"Sharpe (rf=2%):    {s['sharpe']:.2f}",
        f"Max Drawdown:      {pct(s['max_drawdown'])}{mdd_dates}",
        f"Calmar:            {s['calmar']:.2f}",
        f"Win Rate:          {pct(s['win_rate'])} ({s['n_trips']} closed trades)",
        f"Avg Hold Days:     {s['avg_hold_days']:.1f}",
        f"Turnover (annual): {s['turnover']:.2f}x",
        f"Fills:             {s['n_fills']} (rejections: {s['n_rejections']})",
        "=" * 60,
    ])


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    start, end = "2023-05-18", "2026-05-18"
    codes = [c for c, _ in DEMO_UNIVERSE]

    print("Loading cached bars...")
    loader = DataLoader()
    data = loader.load_bars(codes, start, end)
    meta = loader.load_meta(codes)
    if not data:
        print("ERROR: no cached data. Run `python scripts/fetch_data.py` first.")
        return 1
    print(f"Loaded {len(data)} stocks, "
          f"{sum(len(df) for df in data.values())} total bars")

    strategy = DualMACrossStrategy(fast=5, slow=20, position_size_pct=0.05, max_positions=10)
    config = BacktestConfig(start=start, end=end, initial_cash=1_000_000.0)

    print(f"Running backtest: {strategy.name}")
    bt = Backtester(config, strategy, data, meta)
    result = bt.run()

    print()
    print(_format_metrics(result.summary, (start, end), len(data)))

    # Rejection breakdown
    if result.rejections:
        from collections import Counter
        reasons = Counter(r.rejected_reason for r in result.rejections)
        print("\nRejection breakdown:")
        for reason, n in reasons.most_common():
            print(f"  {reason:<20} {n}")

    # First few fills as a sanity check
    if result.fills:
        print(f"\nFirst 5 fills:")
        for f in result.fills[:5]:
            print(f"  {f.timestamp.date()}  {f.side.value:<4}  {f.code}  "
                  f"{f.shares:>5}sh @ ¥{f.price:>8.2f}  cost ¥{f.cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
