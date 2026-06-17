#include "db.h"
#include <cstdio>
#include <cstring>
#include <ctime>

static double col_real(sqlite3_stmt* s, int i) {
    return sqlite3_column_type(s, i) == SQLITE_NULL
        ? 0.0
        : sqlite3_column_double(s, i);
}

static std::string col_text(sqlite3_stmt* s, int i) {
    const char* p = reinterpret_cast<const char*>(sqlite3_column_text(s, i));
    return p ? p : "";
}

bool DB::open(const std::string& path) {
    int rc = sqlite3_open_v2(path.c_str(), &handle,
        SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX, nullptr);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "DB open error: %s\n", sqlite3_errmsg(handle));
        return false;
    }
    sqlite3_exec(handle, "PRAGMA journal_mode=WAL", nullptr, nullptr, nullptr);
    sqlite3_exec(handle, "PRAGMA query_only=1",     nullptr, nullptr, nullptr);
    return true;
}

void DB::close() {
    if (handle) { sqlite3_close(handle); handle = nullptr; }
}

std::vector<std::string> DB::instruments() {
    std::vector<std::string> out;
    sqlite3_stmt* s = nullptr;
    const char* sql = "SELECT DISTINCT instrument_key FROM market_data ORDER BY instrument_key";
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return out;
    while (sqlite3_step(s) == SQLITE_ROW)
        out.push_back(col_text(s, 0));
    sqlite3_finalize(s);
    return out;
}

// Column order must match TICK_COLS below exactly (id is col 0)
void DB::fill_tick(sqlite3_stmt* s, Tick& t) const {
    t.id        = sqlite3_column_int64(s,  0);
    t.timestamp = col_text(s,  1);
    t.ltp       = col_real(s,  2);
    t.cp        = col_real(s,  3);
    t.atp       = col_real(s,  4);
    t.vtt       = col_real(s,  5);
    t.oi        = col_real(s,  6);
    t.iv        = col_real(s,  7);
    t.tbq       = col_real(s,  8);
    t.tsq       = col_real(s,  9);
    t.open      = col_real(s, 10);
    t.high      = col_real(s, 11);
    t.low       = col_real(s, 12);
    t.close     = col_real(s, 13);
    for (int i = 0; i < 5; ++i) {
        t.bid_p[i] = col_real(s, 14 + i * 4 + 0);
        t.bid_q[i] = col_real(s, 14 + i * 4 + 1);
        t.ask_p[i] = col_real(s, 14 + i * 4 + 2);
        t.ask_q[i] = col_real(s, 14 + i * 4 + 3);
    }
}

static const char* TICK_COLS =
    "id, timestamp, ltp, cp, atp, vtt, oi, iv, tbq, tsq, "
    "open, high, low, close, "
    "bid1_p, bid1_q, ask1_p, ask1_q, "
    "bid2_p, bid2_q, ask2_p, ask2_q, "
    "bid3_p, bid3_q, ask3_p, ask3_q, "
    "bid4_p, bid4_q, ask4_p, ask4_q, "
    "bid5_p, bid5_q, ask5_p, ask5_q";

std::vector<Tick> DB::recent_ticks(const std::string& instrument, int limit) {
    std::vector<Tick> out;

    char sql[512];
    snprintf(sql, sizeof(sql),
        "SELECT %s FROM market_data "
        "WHERE instrument_key = ? AND ltp IS NOT NULL "
        "ORDER BY id DESC LIMIT %d",
        TICK_COLS, limit);

    sqlite3_stmt* s = nullptr;
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return out;
    sqlite3_bind_text(s, 1, instrument.c_str(), -1, SQLITE_STATIC);

    while (sqlite3_step(s) == SQLITE_ROW) {
        Tick t;
        fill_tick(s, t);
        out.push_back(t);
    }
    sqlite3_finalize(s);

    // reverse so oldest is first (chart left→right)
    std::reverse(out.begin(), out.end());
    return out;
}

std::unordered_map<std::string, std::string> DB::name_map() {
    std::unordered_map<std::string, std::string> out;
    sqlite3_stmt* s = nullptr;
    // Table may not exist on old DBs — silently return empty map if so
    const char* sql = "SELECT instrument_key, display_name FROM instrument_names";
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return out;
    while (sqlite3_step(s) == SQLITE_ROW)
        out[col_text(s, 0)] = col_text(s, 1);
    sqlite3_finalize(s);
    return out;
}

void DB::update_ltp_map(std::unordered_map<std::string, double>& map, int64_t& since_id) {
    // Read only rows added since last call — primary-key range scan, always fast.
    const char* sql =
        "SELECT id, instrument_key, ltp FROM market_data "
        "WHERE id > ? AND ltp IS NOT NULL ORDER BY id ASC";
    sqlite3_stmt* s = nullptr;
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return;
    sqlite3_bind_int64(s, 1, since_id);
    while (sqlite3_step(s) == SQLITE_ROW) {
        int64_t id = sqlite3_column_int64(s, 0);
        map[col_text(s, 1)] = sqlite3_column_double(s, 2);
        if (id > since_id) since_id = id;
    }
    sqlite3_finalize(s);
}

std::vector<Tick> DB::ticks_before(const std::string& instrument,
                                   int64_t before_id, int limit) {
    std::vector<Tick> out;
    char sql[512];
    snprintf(sql, sizeof(sql),
        "SELECT %s FROM market_data "
        "WHERE instrument_key = ? AND id < ? AND ltp IS NOT NULL "
        "ORDER BY id DESC LIMIT %d",
        TICK_COLS, limit);
    sqlite3_stmt* s = nullptr;
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return out;
    sqlite3_bind_text (s, 1, instrument.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_int64(s, 2, before_id);
    while (sqlite3_step(s) == SQLITE_ROW) { Tick t; fill_tick(s, t); out.push_back(t); }
    sqlite3_finalize(s);
    std::reverse(out.begin(), out.end());   // oldest first
    return out;
}

std::vector<Tick> DB::ticks_after(const std::string& instrument,
                                  int64_t after_id, int limit) {
    std::vector<Tick> out;
    char sql[512];
    snprintf(sql, sizeof(sql),
        "SELECT %s FROM market_data "
        "WHERE instrument_key = ? AND id > ? AND ltp IS NOT NULL "
        "ORDER BY id ASC LIMIT %d",
        TICK_COLS, limit);
    sqlite3_stmt* s = nullptr;
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return out;
    sqlite3_bind_text (s, 1, instrument.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_int64(s, 2, after_id);
    while (sqlite3_step(s) == SQLITE_ROW) { Tick t; fill_tick(s, t); out.push_back(t); }
    sqlite3_finalize(s);
    return out;
}

bool DB::latest_tick(const std::string& instrument, Tick& out) {
    char sql[512];
    snprintf(sql, sizeof(sql),
        "SELECT %s FROM market_data "
        "WHERE instrument_key = ? AND ltp IS NOT NULL "
        "ORDER BY id DESC LIMIT 1",
        TICK_COLS);

    sqlite3_stmt* s = nullptr;
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return false;
    sqlite3_bind_text(s, 1, instrument.c_str(), -1, SQLITE_STATIC);

    bool found = (sqlite3_step(s) == SQLITE_ROW);
    if (found) fill_tick(s, out);
    sqlite3_finalize(s);
    return found;
}

// ── BacktestDB ───────────────────────────────────────────────────────────────

bool BacktestDB::open(const std::string& path) {
    // Silently skip if file does not exist — results DB is optional
    FILE* probe = fopen(path.c_str(), "rb");
    if (!probe) return false;
    fclose(probe);

    int rc = sqlite3_open_v2(path.c_str(), &handle,
        SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX, nullptr);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "BacktestDB open error: %s\n", sqlite3_errmsg(handle));
        sqlite3_close(handle);
        handle = nullptr;
        return false;
    }
    sqlite3_exec(handle, "PRAGMA query_only=1", nullptr, nullptr, nullptr);
    return true;
}

void BacktestDB::close() {
    if (handle) { sqlite3_close(handle); handle = nullptr; }
}

double BacktestDB::parse_iso(const std::string& ts) {
    if (ts.size() < 19) return 0.0;
    std::tm t = {};
    sscanf(ts.c_str(), "%d-%d-%d%*c%d:%d:%d",
           &t.tm_year, &t.tm_mon, &t.tm_mday,
           &t.tm_hour, &t.tm_min, &t.tm_sec);
    t.tm_year -= 1900;
    t.tm_mon  -= 1;
    time_t epoch = _mkgmtime(&t);
    if (epoch < 0) return 0.0;
    const char* dot = strchr(ts.c_str() + 11, '.');
    return (double)epoch + (dot ? atof(dot) : 0.0);
}

std::vector<BacktestRun> BacktestDB::list_runs() {
    std::vector<BacktestRun> out;
    if (!handle) return out;
    const char* sql =
        "SELECT run_id, strategy, run_time, summary "
        "FROM backtest_runs ORDER BY run_id DESC";
    sqlite3_stmt* s = nullptr;
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return out;
    while (sqlite3_step(s) == SQLITE_ROW) {
        BacktestRun r;
        r.run_id       = sqlite3_column_int(s, 0);
        r.strategy     = col_text(s, 1);
        r.run_time     = col_text(s, 2);
        r.summary_json = col_text(s, 3);
        out.push_back(r);
    }
    sqlite3_finalize(s);
    return out;
}

std::vector<InstrumentEquity> BacktestDB::instrument_equity(int run_id) {
    std::vector<InstrumentEquity> out;
    if (!handle) return out;
    const char* sql =
        "SELECT instrument_key, timestamp, equity "
        "FROM backtest_equity WHERE run_id=? ORDER BY instrument_key, id ASC";
    sqlite3_stmt* s = nullptr;
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return out;
    sqlite3_bind_int(s, 1, run_id);
    std::string cur;
    while (sqlite3_step(s) == SQLITE_ROW) {
        std::string key = col_text(s, 0);
        if (key != cur) { out.push_back({key, {}, {}}); cur = key; }
        out.back().x.push_back(parse_iso(col_text(s, 1)));
        out.back().y.push_back(sqlite3_column_double(s, 2));
    }
    sqlite3_finalize(s);
    return out;
}

std::vector<BacktestInstrumentStat> BacktestDB::instrument_stats(int run_id) {
    std::vector<BacktestInstrumentStat> out;
    if (!handle) return out;
    const char* sql =
        "SELECT instrument_key, sharpe, max_drawdown_pct, n_trades, "
        "       final_return_pct, win_rate_pct "
        "FROM backtest_instrument_stats WHERE run_id=? "
        "ORDER BY final_return_pct DESC";
    sqlite3_stmt* s = nullptr;
    if (sqlite3_prepare_v2(handle, sql, -1, &s, nullptr) != SQLITE_OK) return out;
    sqlite3_bind_int(s, 1, run_id);
    while (sqlite3_step(s) == SQLITE_ROW) {
        BacktestInstrumentStat st;
        st.instrument_key    = col_text(s, 0);
        st.sharpe            = sqlite3_column_double(s, 1);
        st.max_drawdown_pct  = sqlite3_column_double(s, 2);
        st.n_trades          = sqlite3_column_int(s, 3);
        st.final_return_pct  = sqlite3_column_double(s, 4);
        st.win_rate_pct      = sqlite3_column_double(s, 5);
        out.push_back(st);
    }
    sqlite3_finalize(s);
    return out;
}
