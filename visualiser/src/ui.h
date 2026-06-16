#pragma once
#include "db.h"
#include <string>
#include <unordered_map>
#include <vector>

// ─── Parsed option / index record ───────────────────────────────────────────

struct ParsedInstrument {
    std::string key;
    std::string display;     // full name from DB
    std::string underlying;  // "NIFTY", "BANKNIFTY", "SENSEX", …
    std::string expiry;      // "02 JUN 26"
    double      strike = 0;
    int         otype  = 0;  // 0=unknown, 1=CE, 2=PE, 3=index
};

// ─── Chart interactive tools ────────────────────────────────────────────────

struct ChartTools {
    enum class Mode { None, DrawHLine, DrawTrade } mode = Mode::None;
    bool trade_buy = true;   // true=buy, false=sell within DrawTrade

    std::vector<double> hlines;   // placed horizontal price levels (shared across panels)

    // LTP chart rectangle
    bool   rect_active  = false;
    bool   rect_visible = false;
    double rx0 = 0, ry0 = 0;
    double rx1 = 0, ry1 = 0;

    // OB viz panel rectangle (independent coordinates)
    bool   ob_rect_active  = false;
    bool   ob_rect_visible = false;
    double ob_rx0 = 0, ob_ry0 = 0;
    double ob_rx1 = 0, ob_ry1 = 0;

    bool hover_details = true;    // shared hover toggle
};

// ─── Trade tool ─────────────────────────────────────────────────────────────

struct TradeSetup {
    // Settings
    float  capital   = 100000.f;   // base capital (INR)
    float  leverage  = 5.f;

    // Placed trade (recalculated whenever entry_price changes)
    bool   placed    = false;
    bool   buy_mode  = true;
    double entry     = 0;
    int    shares    = 0;
    double charges   = 0;          // total round-trip charges
    double breakeven = 0;

    bool   show      = false;      // settings panel visibility
};

// ─── Panel visibility ───────────────────────────────────────────────────────

struct PanelFlags {
    bool instruments = true;
    bool chart       = true;
    bool stats       = true;
    bool depth       = true;
    bool ob_viz      = false;   // hidden by default; add via View menu
    bool backtest    = false;   // hidden by default; add via View menu

    void hide_all() { instruments = chart = stats = depth = ob_viz = backtest = false; }
    void show_all() { instruments = chart = stats = depth = ob_viz = backtest = true;  }
};

// ─── Order-book visualisation state ─────────────────────────────────────────

struct ObVizState {
    bool log_mode      = true;   // true = log, false = linear volume → saturation
    bool needs_rebuild = false;  // set true when mode changes mid-session
    bool fit_pending   = true;   // refit axes once after instrument change (not after load)

    static constexpr int BINS = 200;          // price axis discretisation
    std::vector<double> bid_grid;             // [BINS × nticks], normalised [0,1]
    std::vector<double> ask_grid;
    double  pmin = 0, pmax = 1;
    int64_t id_min = 0, id_max = 1;    // DB id range — for demand-load queries
    double  time_min = 0, time_max = 1; // Unix epoch range — X axis / heatmap bounds
    int     nticks = 0;

    // Rebuild the normalised grids from raw tick depth data.
    void rebuild(const std::vector<Tick>& history);
};

// ─── Theme ──────────────────────────────────────────────────────────────────

struct ThemeSettings {
    // Base preset
    int   preset        = 0;     // 0=Dark  1=Light  2=Classic

    // ImGui palette
    float accent[4]     = {0.30f, 0.80f, 1.00f, 1.00f};
    float win_bg[4]     = {0.08f, 0.08f, 0.10f, 1.00f};
    float frame_bg[4]   = {0.14f, 0.14f, 0.18f, 1.00f};
    float popup_bg[4]   = {0.10f, 0.10f, 0.13f, 1.00f};
    float text_col[4]   = {0.90f, 0.90f, 0.90f, 1.00f};

    // Shape & spacing
    float rounding      = 4.f;
    float border_sz     = 0.f;   // window/frame border (0=none)
    float item_spacing  = 4.f;   // ItemSpacing.y

    // Panel-specific colours (used directly, not via ImGui style)
    float chart_line[4] = {0.30f, 0.80f, 1.00f, 1.00f};
    float close_line[4] = {1.00f, 0.80f, 0.00f, 0.60f};
    float bid_col[4]    = {0.12f, 0.63f, 0.12f, 0.39f};
    float ask_col[4]    = {0.63f, 0.12f, 0.12f, 0.39f};

    bool  show          = false;

    void apply() const;
    void save(const char* path) const;
    bool load(const char* path);
};

// ─── Backtest panel state ────────────────────────────────────────────────────

struct BacktestPanelState {
    std::vector<BacktestRun>   runs;
    int                        selected_run = -1;   // index into `runs`

    // Loaded for selected_run
    std::vector<double>        eq_x;   // Unix epoch timestamps
    std::vector<double>        eq_y;   // equity values
    std::vector<BacktestTrade> trades;

    bool runs_loaded = false;   // fetched at least once
};

// ─── Layout manager ─────────────────────────────────────────────────────────

struct LayoutManager {
    std::vector<std::string> names;
    char   buf[128]       = {};
    bool   show_modal     = false;
    std::string pending_load;

    void scan();
    void save_current(const char* name);
    void load(const char* name);
};

// ─── App state ──────────────────────────────────────────────────────────────

struct AppState {
    DB          db;
    BacktestDB  bkdb;

    std::vector<std::string> instruments;
    std::unordered_map<std::string, std::string> names;   // key → display name (loaded once)
    std::unordered_map<std::string, double>       ltp_map; // key → latest ltp (incremental)
    std::vector<ParsedInstrument> parsed;                  // parsed + sorted list
    int64_t ltp_since_id = 0;                             // highest id consumed by ltp_map

    int   selected_idx = 0;
    std::string selected_instrument;

    // Instrument panel filter: "" = All, "INDEX" = indices only, else underlying name
    std::string inst_filter;

    void rebuild_parsed();

    static constexpr int MAX_POINTS = 2000;
    // LTP chart data (populated by poll / load_older / load_newer)
    std::vector<double>      chart_x;   // Unix epoch timestamps (X axis)
    std::vector<double>      chart_y;
    std::vector<std::string> chart_ts;
    int64_t chart_id_min = 0, chart_id_max = 0;  // DB id boundaries for demand loading

    // OB viz data — completely independent of LTP chart
    std::vector<Tick>        ob_history;
    double                   ob_load_after_time = 0;

    Tick latest;
    bool has_latest = false;

    double last_poll_time = -1e9;
    static constexpr double POLL_INTERVAL = 0.5;

    // Shared X-axis limits for synced pan/zoom across chart panes
    double view_x_min = 0, view_x_max = 1;

    bool   live_mode        = false;  // false = load once, then freeze
    bool   needs_load       = true;   // triggers one load in offline mode (or after select)
    bool   chart_fit_pending = true;  // refit chart axes once after instrument change
    double load_after_time  = 0;      // throttle for on-demand loads (ImGui time)
    static constexpr int LOAD_CHUNK  = 500; // ticks per on-demand fetch

    void load_older();      // LTP chart: prepend older chunk
    void load_newer();      // LTP chart: append newer chunk
    void ob_load_older();   // OB viz: prepend older chunk (independent)
    void ob_load_newer();   // OB viz: append newer chunk (independent)

    bool spotlight_open = false;
    char spotlight_buf[128] = {};

    TradeSetup          trade;
    ChartTools          chart_tools;
    ObVizState          ob_viz;
    PanelFlags          panels;
    ThemeSettings       theme;
    LayoutManager       layouts;
    BacktestPanelState  backtest_panel;
    std::string         bkdb_path;

    void init(const std::string& db_path);
    void poll(double now);
    void select_instrument(const std::string& key);

    // Persist panel visibility, trade settings, live mode, etc.
    void save_settings(const char* path) const;
    void load_settings(const char* path);
};

void render_ui(AppState& state);
