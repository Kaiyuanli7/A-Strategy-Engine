"""
Validate the real AKShare path against production endpoints.

Run locally on a Mac with network access to eastmoney/sina. Reports which
endpoints work and which need fallback adjustment. This sandbox environment
typically returns 403 from push2his.eastmoney.com — this script will fail
loudly there, which is the entire point of running it locally.

Exit 0 if all CRITICAL endpoints succeed; 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


SAMPLE_STOCKS = ["600519", "300750", "601398", "000858", "002594"]
CRITICAL_CHECKS = {"csi300_constituents", "daily_ohlcv", "market_index_ohlcv"}


def fmt(ok: bool) -> str:
    return "\033[32m PASS \033[0m" if ok else "\033[31m FAIL \033[0m"


def check(name: str, fn) -> dict:
    print(f"\n=== {name} ===", flush=True)
    t0 = time.time()
    try:
        info = fn()
        elapsed = time.time() - t0
        ok = info.get("ok", True)
        print(f"  {fmt(ok)} ({elapsed:.1f}s) {info.get('summary', '')}")
        if "sample" in info:
            print(f"    sample: {info['sample']}")
        return {"name": name, "ok": ok, **info}
    except Exception as e:  # noqa: BLE001
        elapsed = time.time() - t0
        print(f"  {fmt(False)} ({elapsed:.1f}s) {type(e).__name__}: {e}")
        return {"name": name, "ok": False, "error": str(e), "exception": type(e).__name__}


def csi300_constituents(client) -> dict:
    df = client.get_csi300_constituents()
    return {
        "ok": not df.empty and len(df) > 250,
        "summary": f"{len(df)} rows; columns={list(df.columns)}",
        "sample": df.head(3).to_dict("records") if not df.empty else None,
    }


def daily_ohlcv(client) -> dict:
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    rows_per_stock = {}
    for code in SAMPLE_STOCKS:
        df = client.get_daily_ohlcv(code, start, end, adjust="qfq")
        rows_per_stock[code] = len(df)
    total = sum(rows_per_stock.values())
    ok = all(n > 100 for n in rows_per_stock.values())
    return {
        "ok": ok,
        "summary": f"total {total} rows across {len(SAMPLE_STOCKS)} stocks: {rows_per_stock}",
    }


def financial_indicators(client) -> dict:
    """Optional; best-effort."""
    try:
        # Try common AKShare endpoints; one of these typically exists
        import akshare as ak
        attempts = ["stock_financial_abstract", "stock_financial_analysis_indicator"]
        for fn_name in attempts:
            fn = getattr(ak, fn_name, None)
            if fn is None:
                continue
            try:
                df = fn(symbol=SAMPLE_STOCKS[0])
                return {
                    "ok": df is not None and len(df) > 0,
                    "summary": f"via {fn_name}: {len(df)} rows, cols={list(df.columns)[:6]}",
                }
            except Exception as e:
                continue
        return {"ok": False, "summary": "no working financial-indicator endpoint"}
    except Exception as e:
        return {"ok": False, "summary": f"akshare missing: {e}"}


def market_index_ohlcv(client) -> dict:
    """Daily index OHLCV for 沪深300 (code 000300). Tries multiple endpoints."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    s_compact = start.replace("-", "")
    e_compact = end.replace("-", "")
    try:
        import akshare as ak
        # Each entry: (function name, callable with correct signature, label).
        attempts = [
            ("index_zh_a_hist",
                lambda: ak.index_zh_a_hist(symbol="000300", period="daily",
                                            start_date=s_compact, end_date=e_compact)),
            ("stock_zh_index_daily_em",
                lambda: ak.stock_zh_index_daily_em(symbol="csi000300",
                                                    start_date=s_compact, end_date=e_compact)),
            ("stock_zh_index_daily_tx",
                lambda: ak.stock_zh_index_daily_tx(symbol="sh000300",
                                                    start_date=s_compact, end_date=e_compact)),
            ("stock_zh_index_daily",
                lambda: ak.stock_zh_index_daily(symbol="sh000300")),
        ]
        for fn_name, call in attempts:
            fn = getattr(ak, fn_name, None)
            if fn is None:
                continue
            try:
                df = call()
                if df is None or len(df) == 0:
                    continue
                return {
                    "ok": len(df) > 100,
                    "summary": f"via {fn_name}: {len(df)} rows",
                }
            except Exception as e:
                # Keep trying the next endpoint, but surface the last error if all fail.
                last_err = e
                continue
        return {"ok": False, "summary": f"no working market-index endpoint; last error: {last_err}"}
    except Exception as e:
        return {"ok": False, "summary": f"akshare error: {e}"}


def sector_classification(client) -> dict:
    try:
        import akshare as ak
        for fn_name in ("sw_index_first_info", "stock_board_industry_name_em"):
            fn = getattr(ak, fn_name, None)
            if fn is None:
                continue
            try:
                df = fn()
                if df is None or len(df) == 0:
                    continue
                return {
                    "ok": len(df) > 10,
                    "summary": f"via {fn_name}: {len(df)} sectors",
                }
            except Exception:
                continue
        return {"ok": False, "summary": "no working sector endpoint"}
    except Exception as e:
        return {"ok": False, "summary": f"akshare error: {e}"}


def northbound_flow(client) -> dict:
    try:
        import akshare as ak
        for fn_name in ("stock_hsgt_individual_em", "stock_hk_hold_em"):
            fn = getattr(ak, fn_name, None)
            if fn is None:
                continue
            try:
                df = fn(stock=SAMPLE_STOCKS[0]) if fn_name == "stock_hsgt_individual_em" else fn(symbol=SAMPLE_STOCKS[0])
                if df is None or len(df) == 0:
                    continue
                return {
                    "ok": len(df) > 0,
                    "summary": f"via {fn_name}: {len(df)} rows",
                }
            except Exception:
                continue
        return {"ok": False, "summary": "no working northbound endpoint"}
    except Exception as e:
        return {"ok": False, "summary": f"akshare error: {e}"}


def northbound_per_stock(client) -> dict:
    """Verify AKShareClient.get_northbound_holdings() returns usable rows."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    df = client.get_northbound_holdings(SAMPLE_STOCKS[0], start, end)
    return {
        "ok": not df.empty,
        "summary": f"{len(df)} northbound rows for {SAMPLE_STOCKS[0]}",
    }


def margin_per_stock(client) -> dict:
    """Verify get_margin_detail() returns usable rows."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    df = client.get_margin_detail(SAMPLE_STOCKS[0], start, end)
    return {
        "ok": not df.empty,
        "summary": f"{len(df)} margin rows for {SAMPLE_STOCKS[0]}",
    }


def lhb_disclosure(client) -> dict:
    """Verify get_lhb_disclosure() returns rows for a recent business day."""
    # Walk back up to 14 days looking for a date with data
    for offset in range(1, 15):
        d = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        df = client.get_lhb_disclosure(d)
        if not df.empty:
            return {"ok": True, "summary": f"{len(df)} rows on {d}"}
    return {"ok": False, "summary": "no recent date returned 龙虎榜 data"}


def limit_pool(client) -> dict:
    """Verify get_limit_pool() returns rows for a recent date."""
    for offset in range(1, 15):
        d = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        df = client.get_limit_pool(d, direction="up")
        if not df.empty:
            return {"ok": True, "summary": f"{len(df)} 涨停 rows on {d}"}
    return {"ok": False, "summary": "no recent date returned limit-up data"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path", default=None, help="optional: write results JSON to file")
    args = parser.parse_args()

    from astrategy.data.akshare_client import AKShareClient
    client = AKShareClient()

    print("Validating real AKShare endpoints. Sandbox envs will fail at the network layer.")
    print(f"Sample stocks: {SAMPLE_STOCKS}")

    results = [
        check("csi300_constituents", lambda: csi300_constituents(client)),
        check("daily_ohlcv", lambda: daily_ohlcv(client)),
        check("market_index_ohlcv", lambda: market_index_ohlcv(client)),
        check("financial_indicators", lambda: financial_indicators(client)),
        check("sector_classification", lambda: sector_classification(client)),
        check("northbound_flow", lambda: northbound_flow(client)),
        # Factor-research alt-data
        check("northbound_per_stock", lambda: northbound_per_stock(client)),
        check("margin_per_stock", lambda: margin_per_stock(client)),
        check("lhb_disclosure", lambda: lhb_disclosure(client)),
        check("limit_pool", lambda: limit_pool(client)),
    ]

    print("\n=== Summary ===")
    critical_failures = []
    for r in results:
        icon = "✓" if r["ok"] else "✗"
        marker = " [CRITICAL]" if r["name"] in CRITICAL_CHECKS else ""
        print(f"  {icon} {r['name']}{marker}")
        if not r["ok"] and r["name"] in CRITICAL_CHECKS:
            critical_failures.append(r["name"])

    if args.report_path:
        import json
        Path(args.report_path).write_text(json.dumps(results, indent=2, default=str))
        print(f"\nWrote report to {args.report_path}")

    if critical_failures:
        print(f"\nCRITICAL FAILURES: {critical_failures}")
        print("Paste this output in the PR thread; fallback chains will be updated.")
        return 1
    print("\nAll critical endpoints OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
