#!/usr/bin/env python3
"""
Backtesting CLI.

Usage
-----
python run_backtest.py --strategy strategies/example.py --db stock_data.db
python run_backtest.py --strategy strategies/example.py --db stock_data.db \\
    --filter "NSE_EQ|RELIANCE,NSE_EQ|TCS" \\
    --date-from 2026-01-01 --date-to 2026-06-01 \\
    --capital 100000 --position-pct 20 \\
    --brokerage 0.03 --slippage 0.01 \\
    --out backtest_results.db

The strategy file must define a class that subclasses Strategy.  The first
such class found in the module is used automatically.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import os
import sys
from datetime import datetime

from backtest.engine import BacktestConfig, run, compute_summary
from backtest.results import write
from backtest.strategy import Strategy


# ── Load strategy from file ───────────────────────────────────────────────────

def load_strategy(path: str):
    """Returns (strategy_instance, abs_path, class_name)."""
    path = os.path.abspath(path)
    mod_name = os.path.splitext(os.path.basename(path))[0]

    # Register under the real module name so multiprocessing workers can re-import it
    parent = os.path.dirname(path)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)

    candidates = [
        cls for _, cls in inspect.getmembers(mod, inspect.isclass)
        if issubclass(cls, Strategy) and cls is not Strategy
    ]
    if not candidates:
        print(f"ERROR: no Strategy subclass found in {path}", file=sys.stderr)
        sys.exit(1)

    cls = candidates[0]
    return cls(), path, cls.__name__


# ── Pretty-print helpers ──────────────────────────────────────────────────────

def _row(label: str, value: str, width: int = 26):
    print(f"  {label:<{width}} {value}")


def _print_per_instrument(results, initial_capital: float):
    header = f"{'Instrument':<40} {'Ticks':>7} {'Trades':>7} {'Win%':>7} {'PnL':>12} {'Return%':>9}"
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        if r.skipped:
            short = r.instrument_key.split("|")[-1]
            print(f"  {short:<38} {'SKIP: ' + r.skip_reason}")
            continue
        short = r.instrument_key.split("|")[-1]
        n = len(r.trades)
        wins = sum(1 for t in r.trades if t.pnl > 0)
        win_pct = wins / n * 100 if n else 0
        total_pnl = sum(t.pnl for t in r.trades)
        ret_pct = total_pnl / initial_capital * 100
        print(f"  {short:<38} {r.n_ticks:>7} {n:>7} {win_pct:>6.1f}% "
              f"{total_pnl:>12,.2f} {ret_pct:>8.2f}%")


def _print_summary(summary: dict, initial_capital: float, run_id: int, out_db: str):
    print("\n" + "=" * 50)
    print("  SUMMARY")
    print("=" * 50)
    _row("Initial capital:", f"₹{initial_capital:,.0f}")
    _row("Total return:",    f"{summary['total_return_pct']:+.2f}%")
    _row("Trades:",          str(summary['n_trades']))
    _row("Win rate:",        f"{summary['win_rate_pct']:.1f}%")
    _row("Avg PnL/trade:",   f"₹{summary['avg_pnl']:,.2f}")
    _row("Max drawdown:",    f"{summary['max_drawdown_pct']:.2f}%")
    _row("Sharpe (raw):",    f"{summary['sharpe']:.3f}")
    print("=" * 50)
    print(f"\n  Results saved → {out_db}  (run_id={run_id})\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Run a backtest on stock_data.db tick data")
    p.add_argument("--strategy",     required=True,  help="Path to strategy .py file")
    p.add_argument("--db",           default="stock_data.db", help="Source DB path")
    p.add_argument("--filter",       default=None,
                   help="Comma-separated instrument keys or substrings, e.g. 'RELIANCE,TCS'")
    p.add_argument("--date-from",    default=None, dest="date_from", help="YYYY-MM-DD")
    p.add_argument("--date-to",      default=None, dest="date_to",   help="YYYY-MM-DD")
    p.add_argument("--capital",      type=float, default=100_000.0)
    p.add_argument("--position-pct", type=float, default=20.0,
                   dest="position_pct", help="% of capital per trade")
    p.add_argument("--brokerage",    type=float, default=0.03,
                   help="Brokerage % per leg")
    p.add_argument("--slippage",     type=float, default=0.01,
                   help="Slippage % per leg")
    p.add_argument("--min-ticks",    type=int,   default=1, dest="min_ticks",
                   help="Skip instruments with fewer ticks (after warmup)")
    p.add_argument("--workers",      type=int,   default=0,
                   help="Parallel workers (0 = os.cpu_count(), 1 = sequential)")
    p.add_argument("--out",          default="backtest_results.db",
                   help="Output DB path")
    args = p.parse_args()

    strategy, strategy_file, strategy_class_name = load_strategy(args.strategy)

    instruments = None
    if args.filter:
        instruments = [s.strip() for s in args.filter.split(",") if s.strip()]

    cfg = BacktestConfig(
        db_path=args.db,
        strategy=strategy,
        instruments=instruments,
        date_from=args.date_from,
        date_to=args.date_to,
        initial_capital=args.capital,
        position_size_pct=args.position_pct,
        brokerage_pct=args.brokerage,
        slippage_pct=args.slippage,
        min_ticks=args.min_ticks,
        n_workers=args.workers,
        strategy_file=strategy_file,
        strategy_class_name=strategy_class_name,
    )

    import os as _os
    workers = args.workers or _os.cpu_count() or 1
    print(f"\nRunning '{strategy.name}'  lookback={strategy.lookback}  "
          f"workers={workers}  db={args.db}")

    run_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    results = run(cfg)

    _print_per_instrument(results, args.capital)

    summary = compute_summary(results, args.capital)
    run_id = write(results, cfg, run_time, args.out)

    _print_summary(summary, args.capital, run_id, args.out)


if __name__ == "__main__":
    main()
