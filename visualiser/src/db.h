#pragma once
#include <set>
#include <string>
#include <unordered_map>
#include <vector>
#include <sqlite3.h>
#include <cstdint>

struct Tick {
    int64_t     id = 0;
    std::string timestamp;   // ISO-ish string; always populated regardless of source column
    double      ltp  = 0;
    double      cp   = 0;
    double      atp  = 0;
    double      vtt  = 0;
    double      oi   = 0;    // 0 when column absent (stocks)
    double      iv   = 0;    // 0 when column absent (stocks)
    double      tbq  = 0;
    double      tsq  = 0;
    double      open = 0, high = 0, low = 0, close = 0;
    double bid_p[5] = {}, bid_q[5] = {};
    double ask_p[5] = {}, ask_q[5] = {};
};

struct DB {
    sqlite3*    handle    = nullptr;

    // Schema flags set at open() — drive dynamic SQL and fill_tick()
    bool        has_timestamp = false;  // 'timestamp' TEXT column (options DB)
    bool        has_ltt       = false;  // 'ltt' INTEGER ms-epoch column (stock DB)
    bool        has_oi        = false;
    bool        has_iv        = false;
    std::string tick_cols;              // built once; used in every SELECT

    bool open(const std::string& path);
    void close();

    std::vector<std::string> instruments();
    std::vector<Tick> recent_ticks(const std::string& instrument, int limit = 500);
    std::vector<Tick> ticks_before(const std::string& instrument, int64_t before_id, int limit);
    std::vector<Tick> ticks_after (const std::string& instrument, int64_t after_id,  int limit);
    bool latest_tick(const std::string& instrument, Tick& out);
    std::unordered_map<std::string, std::string> name_map();
    void update_ltp_map(std::unordered_map<std::string, double>& map, int64_t& since_id);

private:
    void detect_schema();
    void fill_tick(sqlite3_stmt* s, Tick& t) const;
};

// ── Backtest results DB (backtest_results.db) ────────────────────────────────

struct BacktestRun {
    int         run_id = 0;
    std::string strategy;
    std::string run_time;
    std::string summary_json;
};

struct BacktestInstrumentStat {
    std::string instrument_key;
    double      sharpe           = 0;
    double      max_drawdown_pct = 0;
    int         n_trades         = 0;
    double      final_return_pct = 0;
    double      win_rate_pct     = 0;
};

struct InstrumentEquity {
    std::string         key;
    std::vector<double> x;   // Unix epoch
    std::vector<double> y;   // equity
};

struct BacktestDB {
    sqlite3* handle = nullptr;

    bool open(const std::string& path);
    void close();
    bool is_open() const { return handle != nullptr; }

    std::vector<BacktestRun>            list_runs();
    std::vector<InstrumentEquity>       instrument_equity(int run_id);
    std::vector<BacktestInstrumentStat> instrument_stats(int run_id);

private:
    static double parse_iso(const std::string& ts);
};
