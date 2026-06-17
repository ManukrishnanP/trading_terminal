"""
Backtesting engine.

Run a backtest
--------------
    python run_backtest.py \
        --strategy strategies/example.py \
        --db stock_data.db \
        --date-from 2026-01-01 \
        --date-to   2026-06-01 \
        --capital   100000 \
        --out       backtest_results.db

Key flags:
  --strategy      path to .py file containing a Strategy subclass
  --db            market_data.db or stock_data.db
  --date-from/to  YYYY-MM-DD inclusive range (omit for all data)
  --capital       starting capital (default 100000)
  --position-pct  % of capital per trade (default 20)
  --brokerage     % per leg (default 0.03)
  --slippage      % adverse slip per leg (default 0.01)
  --workers       parallel workers; 1 = sequential (default: cpu count)
  --out           output SQLite path (default backtest_results.db)

Per-instrument flow
-------------------
1. Load all ticks from DB for the instrument (within date range).
2. Skip if fewer than strategy.lookback ticks.
3. Slide a rolling window of `lookback` rows across the data, calling
   strategy.on_data() at each step.
4. Convert signal transitions to trades; apply slippage + brokerage.
5. Compute equity curve and per-run summary stats.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import math
import multiprocessing as mp
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import pandas as pd

from backtest.strategy import Strategy


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Trade:
    instrument_key: str
    direction: str          # "LONG" or "SHORT"
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    quantity: int
    pnl: float              # after slippage + brokerage


@dataclass
class InstrumentResult:
    instrument_key: str
    n_ticks: int
    trades: List[Trade]
    equity: List[tuple]     # list of (timestamp_str, equity_float)
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class BacktestConfig:
    db_path: str
    strategy: Strategy
    instruments: Optional[List[str]] = None   # None = all; supports fnmatch globs
    date_from: Optional[str] = None           # "YYYY-MM-DD" inclusive
    date_to: Optional[str] = None             # "YYYY-MM-DD" inclusive
    initial_capital: float = 100_000.0
    position_size_pct: float = 20.0           # % of capital per trade
    brokerage_pct: float = 0.03               # % of trade value each leg
    slippage_pct: float = 0.01                # % adverse slip per leg
    min_ticks: int = 1                        # skip if fewer useful ticks after warmup
    n_workers: int = 0                        # 0 = os.cpu_count(); 1 = sequential
    # Required for multiprocessing on Windows (spawn); set by run_backtest.py
    strategy_file: str = ""                   # abs path to strategy .py
    strategy_class_name: str = ""             # class name within that file


# ── Helpers ───────────────────────────────────────────────────────────────────

_COLS = (
    "timestamp, ltp, open, high, low, close, atp, vtt, oi, tbq, tsq, "
    "bid1_p, bid1_q, ask1_p, ask1_q, "
    "bid2_p, bid2_q, ask2_p, ask2_q, "
    "bid3_p, bid3_q, ask3_p, ask3_q, "
    "bid4_p, bid4_q, ask4_p, ask4_q, "
    "bid5_p, bid5_q, ask5_p, ask5_q"
)


def _load_ticks(conn: sqlite3.Connection, key: str,
                date_from: Optional[str], date_to: Optional[str]) -> pd.DataFrame:
    where = "instrument_key = ? AND ltp IS NOT NULL"
    params: list = [key]

    if date_from:
        where += " AND timestamp >= ?"
        params.append(date_from)
    if date_to:
        # timestamp is "YYYY-MM-DDThh:mm:ss…" so lexicographic < "YYYY-MM-DDU" covers full day
        where += " AND timestamp < (? || 'U')"
        params.append(date_to)

    sql = f"SELECT {_COLS} FROM market_data WHERE {where} ORDER BY rowid ASC"
    df = pd.read_sql_query(sql, conn, params=params)
    return df


def _simulate(df: pd.DataFrame, strategy: Strategy, cfg: BacktestConfig,
              instrument_key: str,
              tick_cb: Optional[Callable[[int, int], None]] = None) -> InstrumentResult:
    lb = strategy.lookback
    n = len(df)

    if n < lb + cfg.min_ticks:
        return InstrumentResult(
            instrument_key=instrument_key,
            n_ticks=n,
            trades=[],
            equity=[],
            skipped=True,
            skip_reason=f"only {n} ticks, need {lb + cfg.min_ticks}",
        )

    trades: List[Trade] = []
    capital = cfg.initial_capital
    equity_pts: List[tuple] = [(df.iloc[lb - 1]["timestamp"], capital)]

    position = 0        # 0=flat, 1=long, -1=short
    entry_price = 0.0
    entry_time = ""
    qty = 0

    sl = cfg.slippage_pct / 100.0
    br = cfg.brokerage_pct / 100.0

    tick_total = n - lb + 1
    step = max(1, tick_total // 200)   # at most 200 redraws per instrument

    for i in range(lb - 1, n):
        tick_i = i - lb + 1
        if tick_cb and tick_i % step == 0:
            tick_cb(tick_i, tick_total)
        window = df.iloc[i - lb + 1 : i + 1].reset_index(drop=True)
        signal = strategy.on_data(window)
        price = df.iloc[i]["ltp"]
        ts = df.iloc[i]["timestamp"]

        if position == 0:
            if signal == 1:
                ep = price * (1 + sl)
                qty = max(1, int(capital * cfg.position_size_pct / 100.0 / ep))
                entry_price, entry_time, position = ep, ts, 1
            elif signal == -1:
                ep = price * (1 - sl)
                qty = max(1, int(capital * cfg.position_size_pct / 100.0 / ep))
                entry_price, entry_time, position = ep, ts, -1

        elif position == 1 and signal != 1:
            xp = price * (1 - sl)
            cost = (entry_price + xp) * qty * br
            pnl = (xp - entry_price) * qty - cost
            capital += pnl
            trades.append(Trade(instrument_key, "LONG", entry_time, entry_price,
                                ts, xp, qty, pnl))
            equity_pts.append((ts, capital))
            position = 0

            # Immediately reverse if signal == -1
            if signal == -1:
                ep = price * (1 - sl)
                qty = max(1, int(capital * cfg.position_size_pct / 100.0 / ep))
                entry_price, entry_time, position = ep, ts, -1

        elif position == -1 and signal != -1:
            xp = price * (1 + sl)
            cost = (entry_price + xp) * qty * br
            pnl = (entry_price - xp) * qty - cost
            capital += pnl
            trades.append(Trade(instrument_key, "SHORT", entry_time, entry_price,
                                ts, xp, qty, pnl))
            equity_pts.append((ts, capital))
            position = 0

            if signal == 1:
                ep = price * (1 + sl)
                qty = max(1, int(capital * cfg.position_size_pct / 100.0 / ep))
                entry_price, entry_time, position = ep, ts, 1

    # Force-close any open position at last tick
    if position != 0:
        last = df.iloc[-1]
        price, ts = last["ltp"], last["timestamp"]
        if position == 1:
            xp = price * (1 - sl)
            cost = (entry_price + xp) * qty * br
            pnl = (xp - entry_price) * qty - cost
            trades.append(Trade(instrument_key, "LONG", entry_time, entry_price,
                                ts, xp, qty, pnl))
        else:
            xp = price * (1 + sl)
            cost = (entry_price + xp) * qty * br
            pnl = (entry_price - xp) * qty - cost
            trades.append(Trade(instrument_key, "SHORT", entry_time, entry_price,
                                ts, xp, qty, pnl))
        capital += pnl
        equity_pts.append((ts, capital))

    return InstrumentResult(
        instrument_key=instrument_key,
        n_ticks=n,
        trades=trades,
        equity=equity_pts,
    )


# ── Two-line progress display ─────────────────────────────────────────────────

class _Progress:
    """Maintains two in-place progress bars (instruments + ticks / workers)."""

    W = 32  # bar fill width

    def __init__(self, total: int):
        self.total = total
        self._drawn = False

    def _bar(self, done: int, total: int) -> str:
        filled = int(self.W * done / total) if total else self.W
        return "#" * filled + "-" * (self.W - filled)

    def _render(self, line1: str, line2: str):
        if self._drawn:
            sys.stdout.write("\x1b[2A\r")
        sys.stdout.write(f"{line1:<72}\n{line2:<72}\n")
        sys.stdout.flush()
        self._drawn = True

    def update(self, inst_i: int, inst_key: str, tick_i: int, tick_total: int):
        """Sequential mode — shows instrument + tick bars."""
        label = inst_key.split("|")[-1][:24]
        line1 = (f"  Instruments  [{self._bar(inst_i + 1, self.total)}]"
                 f"  {inst_i + 1}/{self.total}  {label:<24}")
        line2 = (f"  Ticks        [{self._bar(tick_i, tick_total)}]"
                 f"  {tick_i}/{tick_total}  ")
        self._render(line1, line2)

    def update_parallel(self, done: int, n_workers: int, last_key: str):
        """Parallel mode — shows instrument bar + active-worker count."""
        label = last_key.split("|")[-1][:24] if last_key else ""
        line1 = (f"  Instruments  [{self._bar(done, self.total)}]"
                 f"  {done}/{self.total}  {label:<24}")
        line2 = f"  Workers      {n_workers} parallel  "
        self._render(line1, line2)

    def finish(self):
        if self._drawn:
            sys.stdout.write("\n")
            sys.stdout.flush()


# ── Parallel worker ───────────────────────────────────────────────────────────

_worker_cfg: Optional[BacktestConfig] = None   # set per-process by pool initializer


def _init_worker(db_path: str, strategy_file: str, strategy_class_name: str,
                 date_from: Optional[str], date_to: Optional[str],
                 initial_capital: float, position_size_pct: float,
                 brokerage_pct: float, slippage_pct: float, min_ticks: int):
    """
    Runs once in each worker process at pool startup.
    All args are plain primitives so they pickle cleanly on Windows (spawn).
    Reloads the strategy from the source file rather than unpickling the class.
    """
    global _worker_cfg

    parent = os.path.dirname(strategy_file)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    mod_name = os.path.splitext(os.path.basename(strategy_file))[0]
    spec = importlib.util.spec_from_file_location(mod_name, strategy_file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    strategy = getattr(mod, strategy_class_name)()

    _worker_cfg = BacktestConfig(
        db_path=db_path,
        strategy=strategy,
        date_from=date_from,
        date_to=date_to,
        initial_capital=initial_capital,
        position_size_pct=position_size_pct,
        brokerage_pct=brokerage_pct,
        slippage_pct=slippage_pct,
        min_ticks=min_ticks,
    )


def _run_instrument(key: str) -> InstrumentResult:
    """Runs in a child process."""
    cfg = _worker_cfg
    conn = sqlite3.connect(cfg.db_path)
    conn.execute("PRAGMA query_only=1")
    df = _load_ticks(conn, key, cfg.date_from, cfg.date_to)
    conn.close()
    return _simulate(df, cfg.strategy, cfg, key)


# ── Public API ────────────────────────────────────────────────────────────────

def _resolve_keys(cfg: BacktestConfig) -> List[str]:
    conn = sqlite3.connect(cfg.db_path)
    conn.execute("PRAGMA query_only=1")
    all_keys: List[str] = [
        row[0] for row in
        conn.execute("SELECT DISTINCT instrument_key FROM market_data ORDER BY instrument_key")
    ]
    conn.close()

    if not cfg.instruments:
        return all_keys

    selected = []
    for pattern in cfg.instruments:
        selected.extend(k for k in all_keys if fnmatch.fnmatch(k, pattern) or pattern in k)
    seen: set = set()
    return [k for k in selected if not (k in seen or seen.add(k))]


def run(cfg: BacktestConfig) -> List[InstrumentResult]:
    """Run the backtest. Returns one InstrumentResult per instrument processed."""
    keys = _resolve_keys(cfg)
    n_workers = cfg.n_workers or os.cpu_count() or 1
    progress = _Progress(len(keys))

    results: List[InstrumentResult] = []

    if n_workers == 1:
        # ── Sequential — two-bar display ──────────────────────────────────
        conn = sqlite3.connect(cfg.db_path)
        conn.execute("PRAGMA query_only=1")

        for i, key in enumerate(keys):
            df = _load_ticks(conn, key, cfg.date_from, cfg.date_to)

            def _cb(tick_i: int, tick_total: int, _i=i, _key=key):
                progress.update(_i, _key, tick_i, tick_total)

            result = _simulate(df, cfg.strategy, cfg, key, tick_cb=_cb)
            results.append(result)
            progress.update(i, key, result.n_ticks, result.n_ticks)

        conn.close()

    else:
        # ── Parallel — outer bar only ──────────────────────────────────────
        if not cfg.strategy_file:
            print("  Warning: strategy_file not set — falling back to sequential")
            n_workers = 1
            # re-enter sequential branch
            conn = sqlite3.connect(cfg.db_path)
            conn.execute("PRAGMA query_only=1")
            for i, key in enumerate(keys):
                df = _load_ticks(conn, key, cfg.date_from, cfg.date_to)
                def _cb(tick_i, tick_total, _i=i, _key=key):
                    progress.update(_i, _key, tick_i, tick_total)
                result = _simulate(df, cfg.strategy, cfg, key, tick_cb=_cb)
                results.append(result)
                progress.update(i, key, result.n_ticks, result.n_ticks)
            conn.close()
        else:
            progress.update_parallel(0, n_workers, "")
            init_args = (
                cfg.db_path, cfg.strategy_file, cfg.strategy_class_name,
                cfg.date_from, cfg.date_to,
                cfg.initial_capital, cfg.position_size_pct,
                cfg.brokerage_pct, cfg.slippage_pct, cfg.min_ticks,
            )
            with mp.Pool(n_workers, initializer=_init_worker,
                         initargs=init_args) as pool:
                for result in pool.imap_unordered(_run_instrument, keys):
                    results.append(result)
                    progress.update_parallel(len(results), n_workers,
                                             result.instrument_key)

    progress.finish()
    return results


# ── Summary stats ──────────────────────────────────────────────────────────────

def compute_instrument_stats(result: InstrumentResult,
                             initial_capital: float) -> "dict | None":
    """Per-instrument metrics. Returns None if skipped or no trades."""
    if result.skipped or not result.trades:
        return None

    trades = result.trades
    n = len(trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    pnls = [t.pnl for t in trades]
    avg_pnl = sum(pnls) / n

    if n > 1:
        variance = sum((p - avg_pnl) ** 2 for p in pnls) / (n - 1)
        std_p = math.sqrt(variance)
        sharpe = (avg_pnl / std_p * math.sqrt(n)) if std_p > 0 else 0.0
    else:
        sharpe = 0.0

    final_cap = result.equity[-1][1] if result.equity else initial_capital
    final_return_pct = (final_cap - initial_capital) / initial_capital * 100.0

    peak = initial_capital
    max_dd = 0.0
    for _, eq in result.equity:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    return {
        "instrument_key":  result.instrument_key,
        "sharpe":          round(sharpe, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "n_trades":        n,
        "n_wins":          wins,
        "final_return_pct": round(final_return_pct, 4),
        "win_rate_pct":    round(wins / n * 100.0, 2),
    }


def compute_summary(results: List[InstrumentResult],
                    initial_capital: float) -> dict:
    """Aggregate stats across all non-skipped instruments."""
    all_trades = [t for r in results if not r.skipped for t in r.trades]

    if not all_trades:
        return {
            "total_return_pct": 0.0,
            "n_trades": 0,
            "win_rate_pct": 0.0,
            "avg_pnl": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
        }

    total_pnl = sum(t.pnl for t in all_trades)
    total_return_pct = total_pnl / initial_capital * 100.0
    n = len(all_trades)
    wins = sum(1 for t in all_trades if t.pnl > 0)
    win_rate = wins / n * 100.0
    avg_pnl = total_pnl / n

    pnls = [t.pnl for t in all_trades]
    mean_p = avg_pnl
    if n > 1:
        variance = sum((p - mean_p) ** 2 for p in pnls) / (n - 1)
        std_p = math.sqrt(variance)
        sharpe = (mean_p / std_p * math.sqrt(n)) if std_p > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown from combined equity curve across all instruments
    equity = initial_capital
    peak = initial_capital
    max_dd = 0.0
    for r in results:
        if r.skipped:
            continue
        for _, eq in r.equity[1:]:  # skip the seed point
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        equity = r.equity[-1][1] if r.equity else equity

    return {
        "total_return_pct": round(total_return_pct, 4),
        "n_trades": n,
        "win_rate_pct": round(win_rate, 2),
        "avg_pnl": round(avg_pnl, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe": round(sharpe, 4),
    }
