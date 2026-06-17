"""
Write backtest results to backtest_results.db (SQLite).

Schema (v2):
  backtest_runs            — one row per run, summary JSON
  backtest_instrument_stats — per-instrument stats, top 5%ile only
  backtest_equity          — equity curve, top 5 instruments only (instrument_key column)
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import List

from backtest.engine import InstrumentResult, BacktestConfig, compute_summary, compute_instrument_stats


_DDL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT    NOT NULL,
    run_time TEXT    NOT NULL,
    config   TEXT    NOT NULL,
    summary  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_instrument_stats (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER NOT NULL REFERENCES backtest_runs(run_id),
    instrument_key   TEXT    NOT NULL,
    sharpe           REAL    NOT NULL,
    max_drawdown_pct REAL    NOT NULL,
    n_trades         INTEGER NOT NULL,
    final_return_pct REAL    NOT NULL,
    win_rate_pct     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_equity (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL REFERENCES backtest_runs(run_id),
    instrument_key TEXT    NOT NULL,
    timestamp      TEXT    NOT NULL,
    equity         REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bt_stats_run  ON backtest_instrument_stats(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_equity_run ON backtest_equity(run_id);
"""

_TOP_N = 5          # instruments for equity curves
_TOP_PCT = 5.0      # percentile cutoff for instrument_stats table


def write(results: List[InstrumentResult], cfg: BacktestConfig,
          run_time: str, out_db: str = "backtest_results.db") -> int:
    """Persist results. Returns new run_id."""

    # Per-instrument stats (skip skipped / no-trade instruments)
    all_stats = [s for r in results if (s := compute_instrument_stats(r, cfg.initial_capital))]

    # Sort by final_return_pct descending
    all_stats.sort(key=lambda s: s["final_return_pct"], reverse=True)

    # Top 5%ile cutoff (at least 1)
    n_total = len(all_stats)
    cutoff = max(1, math.ceil(n_total * _TOP_PCT / 100.0))
    top5pct_stats = all_stats[:cutoff]

    # Top N for equity curves
    top_n_keys = {s["instrument_key"] for s in all_stats[:_TOP_N]}

    # Overall summary
    summary = compute_summary(results, cfg.initial_capital)

    # Win rate for top 5%ile instruments
    t5_trades = sum(s["n_trades"] for s in top5pct_stats)
    t5_wins   = sum(s["n_wins"]   for s in top5pct_stats)
    summary["win_rate_top5pct_pct"] = round(t5_wins / t5_trades * 100.0, 2) if t5_trades else 0.0

    config_json = json.dumps({
        "db_path":         cfg.db_path,
        "strategy":        cfg.strategy.name,
        "lookback":        cfg.strategy.lookback,
        "instruments":     cfg.instruments,
        "date_from":       cfg.date_from,
        "date_to":         cfg.date_to,
        "initial_capital": cfg.initial_capital,
        "position_size_pct": cfg.position_size_pct,
        "brokerage_pct":   cfg.brokerage_pct,
        "slippage_pct":    cfg.slippage_pct,
    })

    conn = sqlite3.connect(out_db)
    conn.executescript(_DDL)

    cur = conn.execute(
        "INSERT INTO backtest_runs (strategy, run_time, config, summary) VALUES (?,?,?,?)",
        (cfg.strategy.name, run_time, config_json, json.dumps(summary)),
    )
    run_id = cur.lastrowid

    # Instrument stats (top 5%ile)
    stat_rows = [
        (run_id, s["instrument_key"], s["sharpe"], s["max_drawdown_pct"],
         s["n_trades"], s["final_return_pct"], s["win_rate_pct"])
        for s in top5pct_stats
    ]
    conn.executemany(
        "INSERT INTO backtest_instrument_stats "
        "(run_id,instrument_key,sharpe,max_drawdown_pct,n_trades,final_return_pct,win_rate_pct) "
        "VALUES (?,?,?,?,?,?,?)",
        stat_rows,
    )

    # Equity curves (top N instruments only)
    equity_rows = []
    result_map = {r.instrument_key: r for r in results if not r.skipped}
    for key in (s["instrument_key"] for s in all_stats[:_TOP_N]):
        r = result_map.get(key)
        if r:
            for ts, eq in r.equity:
                equity_rows.append((run_id, key, ts, eq))

    conn.executemany(
        "INSERT INTO backtest_equity (run_id,instrument_key,timestamp,equity) VALUES (?,?,?,?)",
        equity_rows,
    )

    conn.commit()
    conn.close()
    return run_id
