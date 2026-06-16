"""
Write backtest results to backtest_results.db (SQLite).
Schema is created on first write; subsequent writes append new runs.
"""

from __future__ import annotations

import json
import sqlite3
from typing import List

from backtest.engine import InstrumentResult, BacktestConfig, compute_summary


_DDL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT    NOT NULL,
    run_time TEXT    NOT NULL,
    config   TEXT    NOT NULL,   -- JSON
    summary  TEXT    NOT NULL    -- JSON
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL REFERENCES backtest_runs(run_id),
    instrument_key TEXT    NOT NULL,
    direction      TEXT    NOT NULL,
    entry_time     TEXT    NOT NULL,
    entry_price    REAL    NOT NULL,
    exit_time      TEXT    NOT NULL,
    exit_price     REAL    NOT NULL,
    quantity       INTEGER NOT NULL,
    pnl            REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_equity (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL REFERENCES backtest_runs(run_id),
    timestamp TEXT    NOT NULL,
    equity    REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bt_trades_run ON backtest_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_equity_run ON backtest_equity(run_id);
"""


def write(results: List[InstrumentResult], cfg: BacktestConfig,
          run_time: str, out_db: str = "backtest_results.db") -> int:
    """
    Persist results. Returns the new run_id.

    Parameters
    ----------
    results  : output of engine.run()
    cfg      : BacktestConfig used for the run
    run_time : ISO timestamp string for when the run started
    out_db   : path to the results DB (created if absent)
    """
    summary = compute_summary(results, cfg.initial_capital)

    config_json = json.dumps({
        "db_path": cfg.db_path,
        "strategy": cfg.strategy.name,
        "lookback": cfg.strategy.lookback,
        "instruments": cfg.instruments,
        "date_from": cfg.date_from,
        "date_to": cfg.date_to,
        "initial_capital": cfg.initial_capital,
        "position_size_pct": cfg.position_size_pct,
        "brokerage_pct": cfg.brokerage_pct,
        "slippage_pct": cfg.slippage_pct,
    })

    conn = sqlite3.connect(out_db)
    conn.executescript(_DDL)

    cur = conn.execute(
        "INSERT INTO backtest_runs (strategy, run_time, config, summary) VALUES (?,?,?,?)",
        (cfg.strategy.name, run_time, config_json, json.dumps(summary)),
    )
    run_id = cur.lastrowid

    trade_rows = []
    equity_rows = []
    for r in results:
        if r.skipped:
            continue
        for t in r.trades:
            trade_rows.append((run_id, t.instrument_key, t.direction,
                               t.entry_time, t.entry_price,
                               t.exit_time, t.exit_price,
                               t.quantity, t.pnl))
        for ts, eq in r.equity:
            equity_rows.append((run_id, ts, eq))

    conn.executemany(
        "INSERT INTO backtest_trades "
        "(run_id,instrument_key,direction,entry_time,entry_price,"
        "exit_time,exit_price,quantity,pnl) VALUES (?,?,?,?,?,?,?,?,?)",
        trade_rows,
    )
    conn.executemany(
        "INSERT INTO backtest_equity (run_id,timestamp,equity) VALUES (?,?,?)",
        equity_rows,
    )

    conn.commit()
    conn.close()
    return run_id
