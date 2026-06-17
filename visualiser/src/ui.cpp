#include "ui.h"
#include "imgui.h"
#include "imgui_internal.h"   // DockBuilder API
#include "implot.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

// ─── Helpers ────────────────────────────────────────────────────────────────

static std::string display_name(const std::string& key, const AppState& state) {
    auto it = state.names.find(key);
    if (it != state.names.end()) return it->second;
    // Fallback: strip exchange prefix (e.g. "NSE_INDEX|Nifty 50" → "Nifty 50")
    auto p = key.find('|');
    return (p != std::string::npos) ? key.substr(p + 1) : key;
}

static void colored_text(double val, double ref, const char* fmt) {
    ImVec4 col = (val >= ref)
        ? ImVec4(0.2f, 0.9f, 0.3f, 1.f)
        : ImVec4(0.9f, 0.2f, 0.2f, 1.f);
    ImGui::TextColored(col, fmt, val);
}

static ImVec4 to_imvec4(const float c[4]) { return {c[0], c[1], c[2], c[3]}; }

// ─── ThemeSettings ──────────────────────────────────────────────────────────

void ThemeSettings::apply() const {
    switch (preset) {
        case 1:  ImGui::StyleColorsLight();   break;
        case 2:  ImGui::StyleColorsClassic(); break;
        default: ImGui::StyleColorsDark();    break;
    }
    ImGuiStyle& s = ImGui::GetStyle();
    s.WindowRounding     = rounding;
    s.FrameRounding      = rounding * 0.75f;
    s.ScrollbarRounding  = rounding * 0.75f;
    s.GrabRounding       = rounding * 0.75f;
    s.TabRounding        = rounding * 0.75f;
    s.PopupRounding      = rounding * 0.75f;
    s.WindowBorderSize   = border_sz;
    s.FrameBorderSize    = border_sz;
    s.ItemSpacing.y      = item_spacing;

    auto a = [&](float mul = 1.f, float a_mul = 1.f) {
        return ImVec4(accent[0]*mul, accent[1]*mul, accent[2]*mul, accent[3]*a_mul);
    };
    s.Colors[ImGuiCol_Text]             = to_imvec4(text_col);
    s.Colors[ImGuiCol_WindowBg]         = to_imvec4(win_bg);
    s.Colors[ImGuiCol_ChildBg]          = to_imvec4(win_bg);
    s.Colors[ImGuiCol_FrameBg]          = to_imvec4(frame_bg);
    s.Colors[ImGuiCol_FrameBgHovered]   = {frame_bg[0]+0.06f, frame_bg[1]+0.06f, frame_bg[2]+0.06f, 1.f};
    s.Colors[ImGuiCol_FrameBgActive]    = {frame_bg[0]+0.12f, frame_bg[1]+0.12f, frame_bg[2]+0.12f, 1.f};
    s.Colors[ImGuiCol_PopupBg]          = to_imvec4(popup_bg);
    s.Colors[ImGuiCol_TitleBgActive]    = a(0.35f);
    s.Colors[ImGuiCol_MenuBarBg]        = {win_bg[0]+0.04f, win_bg[1]+0.04f, win_bg[2]+0.04f, 1.f};
    s.Colors[ImGuiCol_CheckMark]        = a();
    s.Colors[ImGuiCol_SliderGrab]       = a();
    s.Colors[ImGuiCol_SliderGrabActive] = a();
    s.Colors[ImGuiCol_Button]           = a(0.35f);
    s.Colors[ImGuiCol_ButtonHovered]    = a(0.55f);
    s.Colors[ImGuiCol_ButtonActive]     = a();
    s.Colors[ImGuiCol_Header]           = a(0.30f);
    s.Colors[ImGuiCol_HeaderHovered]    = a(0.50f);
    s.Colors[ImGuiCol_HeaderActive]     = a();
    s.Colors[ImGuiCol_SeparatorHovered] = a(1.f, 0.78f);
    s.Colors[ImGuiCol_SeparatorActive]  = a();
    s.Colors[ImGuiCol_Tab]              = a(0.25f);
    s.Colors[ImGuiCol_TabHovered]       = a(0.55f);
    s.Colors[ImGuiCol_TabSelected]      = a(0.45f);
    s.Colors[ImGuiCol_ScrollbarGrab]    = a(0.40f);
    s.Colors[ImGuiCol_ScrollbarGrabHovered] = a(0.55f);
}

void ThemeSettings::save(const char* path) const {
    FILE* f = fopen(path, "w");
    if (!f) return;
    auto wc = [&](const char* k, const float c[4]) {
        fprintf(f, "%s=%.4f,%.4f,%.4f,%.4f\n", k, c[0],c[1],c[2],c[3]);
    };
    fprintf(f, "preset=%d\n", preset);
    wc("accent",      accent);
    wc("win_bg",      win_bg);
    wc("frame_bg",    frame_bg);
    wc("popup_bg",    popup_bg);
    wc("text_col",    text_col);
    fprintf(f, "rounding=%.2f\n",     rounding);
    fprintf(f, "border_sz=%.2f\n",    border_sz);
    fprintf(f, "item_spacing=%.2f\n", item_spacing);
    wc("chart_line",  chart_line);
    wc("close_line",  close_line);
    wc("bid_col",     bid_col);
    wc("ask_col",     ask_col);
    fclose(f);
}

bool ThemeSettings::load(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) return false;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        char key[64]; float a,b,c,d;
        if (sscanf(line, "%63[^=]=%f,%f,%f,%f", key, &a,&b,&c,&d) == 5) {
            float* dst = nullptr;
            if (!strcmp(key,"accent"))     dst = accent;
            else if (!strcmp(key,"win_bg"))    dst = win_bg;
            else if (!strcmp(key,"frame_bg"))  dst = frame_bg;
            else if (!strcmp(key,"popup_bg"))  dst = popup_bg;
            else if (!strcmp(key,"text_col"))  dst = text_col;
            else if (!strcmp(key,"chart_line"))dst = chart_line;
            else if (!strcmp(key,"close_line"))dst = close_line;
            else if (!strcmp(key,"bid_col"))   dst = bid_col;
            else if (!strcmp(key,"ask_col"))   dst = ask_col;
            if (dst) { dst[0]=a; dst[1]=b; dst[2]=c; dst[3]=d; }
        } else {
            float v; char k[64];
            if (sscanf(line, "%63[^=]=%f", k, &v) == 2) {
                if      (!strcmp(k,"preset"))       preset       = (int)v;
                else if (!strcmp(k,"rounding"))     rounding     = v;
                else if (!strcmp(k,"border_sz"))    border_sz    = v;
                else if (!strcmp(k,"item_spacing")) item_spacing = v;
            }
        }
    }
    fclose(f);
    return true;
}

// ─── LayoutManager ──────────────────────────────────────────────────────────

void LayoutManager::scan() {
    names.clear();
    std::error_code ec;
    if (!fs::exists("layouts", ec)) return;
    for (const auto& e : fs::directory_iterator("layouts", ec))
        if (e.path().extension() == ".ini")
            names.push_back(e.path().stem().string());
    std::sort(names.begin(), names.end());
}

void LayoutManager::save_current(const char* name) {
    std::error_code ec;
    fs::create_directories("layouts", ec);
    std::string path = std::string("layouts/") + name + ".ini";
    ImGui::SaveIniSettingsToDisk(path.c_str());
    scan();
}

void LayoutManager::load(const char* name) {
    pending_load = std::string("layouts/") + name + ".ini";
}

// ─── Helpers ────────────────────────────────────────────────────────────────

// ISO timestamp → Unix epoch seconds (X axis values for ImPlot time scale).
static double parse_ts(const std::string& ts) {
    if (ts.size() < 19) return 0.0;
    std::tm t = {};
    sscanf(ts.c_str(), "%d-%d-%d%*c%d:%d:%d",
           &t.tm_year, &t.tm_mon, &t.tm_mday,
           &t.tm_hour, &t.tm_min, &t.tm_sec);
    t.tm_year -= 1900;
    t.tm_mon  -= 1;
    // _mkgmtime treats the struct as UTC — no local-timezone offset applied.
    // Timestamps in the DB are already IST wall-clock values; we want to
    // preserve them exactly, so we tell ImPlot to display in UTC as well.
    time_t epoch = _mkgmtime(&t);
    if (epoch < 0) return 0.0;
    const char* dot = strchr(ts.c_str() + 11, '.');
    return (double)epoch + (dot ? atof(dot) : 0.0);
}

// ─── AppState ───────────────────────────────────────────────────────────────

// ─── ObVizState::rebuild ────────────────────────────────────────────────────

void ObVizState::rebuild(const std::vector<Tick>& history) {
    nticks        = (int)history.size();
    needs_rebuild = false;
    if (nticks == 0) return;

    id_min   = history.front().id;
    id_max   = history.back().id;
    if (id_max <= id_min) id_max = id_min + 1;
    time_min = parse_ts(history.front().timestamp);
    time_max = parse_ts(history.back().timestamp);
    if (time_max <= time_min) time_max = time_min + 1.0;

    // Price range across all depth levels
    pmin = 1e18; pmax = -1e18;
    for (const auto& t : history) {
        for (int k = 0; k < 5; ++k) {
            if (t.bid_p[k] > 0) { pmin = std::min(pmin, t.bid_p[k]); pmax = std::max(pmax, t.bid_p[k]); }
            if (t.ask_p[k] > 0) { pmin = std::min(pmin, t.ask_p[k]); pmax = std::max(pmax, t.ask_p[k]); }
        }
    }
    if (pmax <= pmin) pmax = pmin + 1.0;
    double range = pmax - pmin;

    // Zero-fill grids (row = price bin, col = tick)
    bid_grid.assign(BINS * nticks, 0.0);
    ask_grid.assign(BINS * nticks, 0.0);

    // Accumulate raw quantities (max per bin per tick)
    for (int ti = 0; ti < nticks; ++ti) {
        const Tick& t = history[ti];
        for (int k = 0; k < 5; ++k) {
            auto place = [&](double price, double qty, std::vector<double>& grid) {
                if (price <= 0 || qty <= 0) return;
                // ImPlot renders row 0 at the TOP (bmax.y), so flip the bin so that
                // low prices end up in the last row (bottom) and high prices in row 0 (top).
                int bin = BINS - 1 - std::clamp(
                    (int)((price - pmin) / range * (BINS - 1)), 0, BINS - 1);
                grid[bin * nticks + ti] += qty;
            };
            place(t.bid_p[k], t.bid_q[k], bid_grid);
            place(t.ask_p[k], t.ask_q[k], ask_grid);
        }
    }

    // Normalise to [0,1] using chosen mode
    auto normalise = [&](std::vector<double>& grid) {
        double max_val = *std::max_element(grid.begin(), grid.end());
        if (max_val <= 0) return;
        if (log_mode) {
            double log_max = std::log(1.0 + max_val);
            for (auto& v : grid)
                v = (v > 0) ? std::log(1.0 + v) / log_max : 0.0;
        } else {
            for (auto& v : grid) v /= max_val;
        }
    };
    normalise(bid_grid);
    normalise(ask_grid);
}

// ─── Instrument parsing ─────────────────────────────────────────────────────

// Display name format from complete.json: "NIFTY 23400 CE 02 JUN 26" (space-separated)
// Tokens: [0]=underlying [1]=strike [2]=CE|PE [3..5]=expiry
static ParsedInstrument parse_instrument(const std::string& key, const std::string& raw_name) {
    ParsedInstrument p;
    p.key     = key;
    p.display = raw_name;

    if (key.find("INDEX") != std::string::npos) {
        p.otype = 3;
        // Best-effort underlying: strip " [SYMBOL]" suffix if present
        auto br = raw_name.find(" [");
        p.underlying = (br != std::string::npos) ? raw_name.substr(0, br) : raw_name;
        return p;
    }

    // Strip optional trailing "(SUFFIX)"
    std::string base = raw_name;
    auto lp = raw_name.rfind('(');
    if (lp != std::string::npos && lp > 0) {
        base = raw_name.substr(0, lp);
        while (!base.empty() && base.back() == ' ') base.pop_back();
    }

    std::istringstream ss(base);
    std::vector<std::string> tok;
    std::string t;
    while (ss >> t) tok.push_back(t);

    // Expect [underlying, strike, CE|PE, expiry...]
    if (tok.size() >= 3) {
        p.underlying = tok[0];
        try { p.strike = std::stod(tok[1]); } catch (...) {}
        if      (tok[2] == "CE") p.otype = 1;
        else if (tok[2] == "PE") p.otype = 2;
        if (tok.size() >= 6)
            p.expiry = tok[3] + " " + tok[4] + " " + tok[5];
    }

    // Last-resort fallback: prefer readable display name (from instrument_names);
    // only fall back to the raw key fragment if no name was resolved.
    if (p.underlying.empty()) {
        if (!p.display.empty() && p.display != key)
            p.underlying = p.display;
        else {
            auto pos = key.find('|');
            p.underlying = (pos != std::string::npos) ? key.substr(pos + 1) : key;
        }
    }

    return p;
}

void AppState::rebuild_parsed() {
    parsed.clear();
    parsed.reserve(instruments.size());
    for (const auto& key : instruments) {
        auto it = names.find(key);
        const std::string& name = (it != names.end()) ? it->second : key;
        parsed.push_back(parse_instrument(key, name));
    }
    // Stable sort: index first, then by underlying / strike / CE before PE
    std::stable_sort(parsed.begin(), parsed.end(),
        [](const ParsedInstrument& a, const ParsedInstrument& b) {
            if (a.otype == 3 && b.otype != 3) return true;
            if (a.otype != 3 && b.otype == 3) return false;
            if (a.underlying != b.underlying) return a.underlying < b.underlying;
            if (a.strike     != b.strike)     return a.strike     < b.strike;
            return a.otype < b.otype; // CE(1) before PE(2)
        });
}

// ─── AppState ───────────────────────────────────────────────────────────────

void AppState::init(const std::string& db_path) {
    if (!db.open(db_path)) return;
    instruments = db.instruments();
    names       = db.name_map();       // fetched once; static after seeding
    db.update_ltp_map(ltp_map, ltp_since_id); // initial load
    rebuild_parsed();
    layouts.scan();
    theme.load("theme.cfg");
    theme.apply();
    if (!instruments.empty())
        select_instrument(instruments[0]);
}

void AppState::save_settings(const char* path) const {
    FILE* f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "panels.instruments=%d\n", (int)panels.instruments);
    fprintf(f, "panels.chart=%d\n",       (int)panels.chart);
    fprintf(f, "panels.stats=%d\n",       (int)panels.stats);
    fprintf(f, "panels.depth=%d\n",       (int)panels.depth);
    fprintf(f, "panels.ob_viz=%d\n",      (int)panels.ob_viz);
    fprintf(f, "panels.backtest=%d\n",    (int)panels.backtest);
    fprintf(f, "trade.show=%d\n",         (int)trade.show);
    fprintf(f, "trade.capital=%.2f\n",    (double)trade.capital);
    fprintf(f, "trade.leverage=%.2f\n",   (double)trade.leverage);
    fprintf(f, "live_mode=%d\n",          (int)live_mode);
    fclose(f);
}

void AppState::load_settings(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) return;
    char line[256], key[64];
    int   ival; float fval;
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "%63[^=]=%d",  key, &ival) == 2) {
            if      (!strcmp(key, "panels.instruments")) panels.instruments = ival;
            else if (!strcmp(key, "panels.chart"))       panels.chart       = ival;
            else if (!strcmp(key, "panels.stats"))       panels.stats       = ival;
            else if (!strcmp(key, "panels.depth"))       panels.depth       = ival;
            else if (!strcmp(key, "panels.ob_viz"))      panels.ob_viz      = ival;
            else if (!strcmp(key, "panels.backtest"))    panels.backtest    = ival;
            else if (!strcmp(key, "trade.show"))         trade.show         = ival;
            else if (!strcmp(key, "live_mode"))          live_mode          = ival;
        } else if (sscanf(line, "%63[^=]=%f", key, &fval) == 2) {
            if      (!strcmp(key, "trade.capital"))  trade.capital  = fval;
            else if (!strcmp(key, "trade.leverage")) trade.leverage = fval;
        }
    }
    fclose(f);
}

void AppState::poll(double now) {
    if (live_mode) {
        if (now - last_poll_time < POLL_INTERVAL) return;
    } else {
        if (!needs_load) return;
    }
    needs_load     = false;
    last_poll_time = now;
    if (selected_instrument.empty()) return;

    // ── LTP chart ────────────────────────────────────────────────────────
    if (panels.chart) {
        if (chart_x.empty()) {
            // First load — full fetch
            auto ticks = db.recent_ticks(selected_instrument, MAX_POINTS);
            chart_x.clear(); chart_y.clear(); chart_ts.clear();
            chart_x.reserve(ticks.size());
            chart_y.reserve(ticks.size());
            chart_ts.reserve(ticks.size());
            if (!ticks.empty()) {
                for (auto& t : ticks) {
                    chart_x.push_back(parse_ts(t.timestamp));
                    chart_y.push_back(t.ltp);
                    chart_ts.push_back(t.timestamp);
                }
                latest       = ticks.back();
                has_latest   = true;
                chart_id_min = ticks.front().id;
                chart_id_max = ticks.back().id;
            }
            // Seed OB viz from same initial data
            if (panels.ob_viz && ob_history.empty()) {
                ob_history           = ticks;
                ob_viz.needs_rebuild = true;
            }
        } else if (live_mode) {
            // Incremental — only fetch rows newer than last seen
            auto newer = db.ticks_after(selected_instrument, chart_id_max, LOAD_CHUNK);
            if (!newer.empty()) {
                for (auto& t : newer) {
                    chart_x.push_back(parse_ts(t.timestamp));
                    chart_y.push_back(t.ltp);
                    chart_ts.push_back(t.timestamp);
                }
                latest       = newer.back();
                has_latest   = true;
                chart_id_max = newer.back().id;
                // Trim to MAX_POINTS from the front
                if ((int)chart_x.size() > MAX_POINTS) {
                    int trim = (int)chart_x.size() - MAX_POINTS;
                    chart_x.erase (chart_x.begin(),  chart_x.begin()  + trim);
                    chart_y.erase (chart_y.begin(),  chart_y.begin()  + trim);
                    chart_ts.erase(chart_ts.begin(), chart_ts.begin() + trim);
                    chart_id_min = (int64_t)chart_x.front();  // approx; exact not needed
                }
                // OB viz incremental
                if (panels.ob_viz && !ob_history.empty()) {
                    int64_t last_id = ob_history.back().id;
                    auto ob_newer = db.ticks_after(selected_instrument, last_id, LOAD_CHUNK);
                    if (!ob_newer.empty()) {
                        ob_history.insert(ob_history.end(), ob_newer.begin(), ob_newer.end());
                        ob_viz.needs_rebuild = true;
                    }
                }
            }
        }
    } else if (panels.ob_viz) {
        // Chart hidden but OB viz visible — fetch ticks for OB only
        if (ob_history.empty()) {
            auto ticks           = db.recent_ticks(selected_instrument, MAX_POINTS);
            ob_history           = ticks;
            ob_viz.needs_rebuild = true;
            if (!ticks.empty()) { latest = ticks.back(); has_latest = true; }
        } else if (live_mode && !ob_history.empty()) {
            int64_t last_id = ob_history.back().id;
            auto newer = db.ticks_after(selected_instrument, last_id, LOAD_CHUNK);
            if (!newer.empty()) {
                ob_history.insert(ob_history.end(), newer.begin(), newer.end());
                ob_viz.needs_rebuild = true;
                latest = ob_history.back(); has_latest = true;
            }
        }
    }

    // ── Stats / Depth need latest tick even when chart is hidden ─────────
    if (!panels.chart && !panels.ob_viz && (panels.stats || panels.depth))
        has_latest = db.latest_tick(selected_instrument, latest);
}

// ─── On-demand range loading ────────────────────────────────────────────────

// LTP chart — only touches chart_x / chart_y / chart_ts / chart_id_*
void AppState::load_older() {
    if (chart_x.empty()) return;
    double now = ImGui::GetTime();
    if (now < load_after_time) return;
    load_after_time = now + 0.4;

    auto older = db.ticks_before(selected_instrument, chart_id_min, LOAD_CHUNK);
    if (older.empty()) return;

    std::vector<double>      nx, ny;
    std::vector<std::string> nts;
    nx.reserve(older.size() + chart_x.size());
    ny.reserve(nx.capacity());
    nts.reserve(nx.capacity());
    for (auto& t : older) {
        nx.push_back(parse_ts(t.timestamp));
        ny.push_back(t.ltp);
        nts.push_back(t.timestamp);
    }
    nx.insert (nx.end(),  chart_x.begin(),  chart_x.end());
    ny.insert (ny.end(),  chart_y.begin(),  chart_y.end());
    nts.insert(nts.end(), chart_ts.begin(), chart_ts.end());
    chart_x      = std::move(nx);
    chart_y      = std::move(ny);
    chart_ts     = std::move(nts);
    chart_id_min = older.front().id;
}

void AppState::load_newer() {
    if (chart_x.empty()) return;
    double now = ImGui::GetTime();
    if (now < load_after_time) return;
    load_after_time = now + 0.4;

    auto newer = db.ticks_after(selected_instrument, chart_id_max, LOAD_CHUNK);
    if (newer.empty()) return;

    for (auto& t : newer) {
        chart_x.push_back(parse_ts(t.timestamp));
        chart_y.push_back(t.ltp);
        chart_ts.push_back(t.timestamp);
    }
    chart_id_max = newer.back().id;
}

// OB viz — only touches ob_history / ob_viz
void AppState::ob_load_older() {
    if (ob_history.empty()) return;
    double now = ImGui::GetTime();
    if (now < ob_load_after_time) return;
    ob_load_after_time = now + 0.4;

    auto older = db.ticks_before(selected_instrument,
                                  ob_history.front().id, LOAD_CHUNK);
    if (older.empty()) return;

    std::vector<Tick> nh(std::move(older));
    nh.insert(nh.end(), ob_history.begin(), ob_history.end());
    ob_history = std::move(nh);
    ob_viz.needs_rebuild = true;
}

void AppState::ob_load_newer() {
    if (ob_history.empty()) return;
    double now = ImGui::GetTime();
    if (now < ob_load_after_time) return;
    ob_load_after_time = now + 0.4;

    auto newer = db.ticks_after(selected_instrument,
                                 ob_history.back().id, LOAD_CHUNK);
    if (newer.empty()) return;

    ob_history.insert(ob_history.end(), newer.begin(), newer.end());
    ob_viz.needs_rebuild = true;
}

void AppState::select_instrument(const std::string& key) {
    selected_instrument = key;
    chart_x.clear(); chart_y.clear(); chart_ts.clear();
    ob_history.clear();
    ob_viz.nticks        = 0;
    ob_viz.needs_rebuild = true;
    ob_viz.fit_pending   = true;   // refit, but not on load_older/load_newer
    has_latest           = false;
    last_poll_time       = -1e9;
    needs_load           = true;       // load data for new instrument regardless of mode
    chart_fit_pending    = true;       // refit axes once after first data arrives
}

// ─── Panel: Instruments ──────────────────────────────────────────────────────

static ImVec4 otype_color(int otype) {
    switch (otype) {
        case 1:  return {0.35f, 1.00f, 0.50f, 1.f};
        case 2:  return {1.00f, 0.40f, 0.40f, 1.f};
        case 3:  return {1.00f, 0.85f, 0.30f, 1.f};
        default: return {0.80f, 0.80f, 0.80f, 1.f};
    }
}

// Returns true if the parsed list has any CE/PE options — i.e. is an option chain.
static bool has_options(const std::vector<ParsedInstrument>& parsed) {
    for (const auto& p : parsed)
        if (p.otype == 1 || p.otype == 2) return true;
    return false;
}

// ── Stock / flat list ────────────────────────────────────────────────────────

static void panel_instruments_flat(AppState& state) {
    // Text filter
    static char filter_buf[128] = {};
    ImGui::SetNextItemWidth(-1);
    ImGui::InputTextWithHint("##flt", "Filter...", filter_buf, sizeof(filter_buf));

    const std::string flt = [&]{
        std::string s(filter_buf);
        std::transform(s.begin(), s.end(), s.begin(), ::tolower);
        return s;
    }();

    ImGuiTableFlags tf = ImGuiTableFlags_ScrollY
                       | ImGuiTableFlags_BordersInnerV
                       | ImGuiTableFlags_RowBg
                       | ImGuiTableFlags_SizingStretchProp;

    if (ImGui::BeginTable("##flat", 1, tf, ImVec2(0, -1))) {
        ImGui::TableSetupColumn("Name", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableSetupScrollFreeze(0, 1);
        ImGui::TableHeadersRow();

        for (const auto& p : state.parsed) {
            std::string name = display_name(p.key, state);

            if (!flt.empty()) {
                std::string nl = name;
                std::transform(nl.begin(), nl.end(), nl.begin(), ::tolower);
                if (nl.find(flt) == std::string::npos) continue;
            }

            ImGui::TableNextRow();
            bool sel = (p.key == state.selected_instrument);

            ImGui::TableSetColumnIndex(0);
            std::string label = name + "##" + p.key;
            if (ImGui::Selectable(label.c_str(), sel,
                    ImGuiSelectableFlags_SpanAllColumns
                    | ImGuiSelectableFlags_AllowOverlap)) {
                state.select_instrument(p.key);
            }
            if (sel) ImGui::SetItemDefaultFocus();
        }
        ImGui::EndTable();
    }
}

// ── Option chain ─────────────────────────────────────────────────────────────

static void panel_instruments_chain(AppState& state) {
    // Collect unique underlyings
    std::vector<std::string> underlyings;
    {
        std::set<std::string> seen;
        for (const auto& p : state.parsed)
            if (p.otype != 3 && !p.underlying.empty() && seen.insert(p.underlying).second)
                underlyings.push_back(p.underlying);
        std::sort(underlyings.begin(), underlyings.end());
    }
    const bool has_idx = std::any_of(state.parsed.begin(), state.parsed.end(),
                                     [](const ParsedInstrument& p){ return p.otype == 3; });

    if (ImGui::BeginTabBar("##ul_tabs")) {
        if (ImGui::BeginTabItem("All")) {
            if (state.inst_filter != "") state.inst_filter = "";
            ImGui::EndTabItem();
        }
        for (const auto& ul : underlyings)
            if (ImGui::BeginTabItem(ul.c_str())) {
                if (state.inst_filter != ul) state.inst_filter = ul;
                ImGui::EndTabItem();
            }
        if (has_idx && ImGui::BeginTabItem("Index")) {
            if (state.inst_filter != "INDEX") state.inst_filter = "INDEX";
            ImGui::EndTabItem();
        }
        ImGui::EndTabBar();
    }

    const bool show_all   = state.inst_filter.empty();
    const bool show_index = (state.inst_filter == "INDEX");
    std::vector<const ParsedInstrument*> visible;
    visible.reserve(state.parsed.size());
    for (const auto& p : state.parsed) {
        if      (show_all)                                               visible.push_back(&p);
        else if (show_index && p.otype == 3)                             visible.push_back(&p);
        else if (!show_index && !show_all && p.otype != 3
                 && p.underlying == state.inst_filter)                   visible.push_back(&p);
    }

    const bool show_ul = show_all;
    const int  ncols   = show_ul ? 4 : 3;

    ImGuiTableFlags tf = ImGuiTableFlags_ScrollY
                       | ImGuiTableFlags_BordersInnerV
                       | ImGuiTableFlags_RowBg
                       | ImGuiTableFlags_SizingStretchProp;

    if (ImGui::BeginTable("##chain", ncols, tf, ImVec2(0, -1))) {
        if (show_ul) ImGui::TableSetupColumn("Symbol", ImGuiTableColumnFlags_WidthStretch, 2.f);
        ImGui::TableSetupColumn("Strike", ImGuiTableColumnFlags_WidthStretch, 1.5f);
        ImGui::TableSetupColumn("Type",   ImGuiTableColumnFlags_WidthFixed,   38.f);
        ImGui::TableSetupColumn("LTP",    ImGuiTableColumnFlags_WidthStretch, 1.2f);
        ImGui::TableSetupScrollFreeze(0, 1);
        ImGui::TableHeadersRow();

        for (const auto* p : visible) {
            ImGui::TableNextRow();
            bool   sel = (p->key == state.selected_instrument);
            ImVec4 col = otype_color(p->otype);

            if (show_ul) {
                ImGui::TableSetColumnIndex(0);
                ImGui::PushStyleColor(ImGuiCol_Text, col);
                ImGui::TextUnformatted((p->otype == 3 ? p->underlying : p->underlying).c_str());
                ImGui::PopStyleColor();
            }

            ImGui::TableSetColumnIndex(show_ul ? 1 : 0);
            ImGui::PushStyleColor(ImGuiCol_Text, col);
            if (p->otype == 3) ImGui::TextUnformatted("--");
            else                ImGui::Text("%.0f", p->strike);
            ImGui::PopStyleColor();

            ImGui::TableSetColumnIndex(show_ul ? 2 : 1);
            {
                const char* ts = p->otype==1?"CE": p->otype==2?"PE": p->otype==3?"IDX":"?";
                std::string lbl = std::string(ts) + "##" + p->key;
                ImGui::PushStyleColor(ImGuiCol_Text, col);
                if (ImGui::Selectable(lbl.c_str(), sel,
                        ImGuiSelectableFlags_SpanAllColumns
                        | ImGuiSelectableFlags_AllowOverlap))
                    state.select_instrument(p->key);
                ImGui::PopStyleColor();
                if (sel) ImGui::SetItemDefaultFocus();
            }

            ImGui::TableSetColumnIndex(show_ul ? 3 : 2);
            auto it = state.ltp_map.find(p->key);
            if (it != state.ltp_map.end()) {
                ImGui::PushStyleColor(ImGuiCol_Text, col);
                ImGui::Text("%.2f", it->second);
                ImGui::PopStyleColor();
            }
        }
        ImGui::EndTable();
    }
}

// ── Entry ────────────────────────────────────────────────────────────────────

static void panel_instrument_selector(AppState& state) {
    if (!state.panels.instruments) return;
    ImGui::Begin("Instruments", &state.panels.instruments);
    if (has_options(state.parsed))
        panel_instruments_chain(state);
    else
        panel_instruments_flat(state);
    ImGui::End();
}

// ─── Panel: LTP Chart ───────────────────────────────────────────────────────



// Parse HH:MM:SS from an ISO timestamp string, return total seconds since midnight.
static int ts_to_sec(const std::string& ts) {
    if (ts.size() < 19) return 0;
    int h = 0, m = 0, s = 0;
    sscanf(ts.c_str() + 11, "%d:%d:%d", &h, &m, &s);
    return h * 3600 + m * 60 + s;
}

static std::string fmt_delta(int sec) {
    sec = std::abs(sec);
    char buf[32];
    if (sec < 60)
        snprintf(buf, sizeof(buf), "%ds", sec);
    else
        snprintf(buf, sizeof(buf), "%dm %ds", sec / 60, sec % 60);
    return buf;
}

// ─── Trade charge calculator ─────────────────────────────────────────────────
// Equity Intraday, NSE (Upstox schedule, from 1 March 2026).
// Round-trip (buy + sell both at `price`, approximation for breakeven calc).
static double calc_trade_charges(double price, int shares) {
    if (shares <= 0 || price <= 0) return 0.0;
    double bt = price * shares;   // buy turnover
    double st = bt;               // sell turnover ≈ buy (BE close to entry)

    double brokerage   = std::min(20.0, bt*0.001) + std::min(20.0, st*0.001);
    double stt         = st * 0.00025;                  // 0.025% sell side
    double transaction = (bt + st) * 0.0000307;         // 0.00307% each side NSE
    double ipft        = (bt + st) * 0.000001;          // Rs0.01/crore = 1e-9/rupee? NSE IPFT
    double sebi        = (bt + st) * 0.000001;          // Rs10/crore
    double stamp       = bt * 0.00003;                  // 0.003% buy side
    double gst         = (brokerage + transaction + ipft) * 0.18;
    return brokerage + stt + transaction + ipft + sebi + stamp + gst;
}

static void update_trade(TradeSetup& tr) {
    if (!tr.placed) return;
    double wc    = (double)tr.capital * tr.leverage;
    tr.shares    = (int)(wc / tr.entry);
    tr.charges   = calc_trade_charges(tr.entry, tr.shares);
    double be_d  = (tr.shares > 0) ? tr.charges / tr.shares : 0.0;
    tr.breakeven = tr.buy_mode ? tr.entry + be_d : tr.entry - be_d;
}

static void panel_ltp_chart(AppState& state) {
    if (!state.panels.chart) return;
    ImGui::Begin("LTP Chart", &state.panels.chart);

    if (state.chart_x.empty()) {
        ImGui::TextDisabled("No data yet…");
        ImGui::End();
        return;
    }

    ChartTools& tools = state.chart_tools;
    const bool  shift = ImGui::IsKeyDown(ImGuiKey_LeftShift)
                     || ImGui::IsKeyDown(ImGuiKey_RightShift);
    if (tools.mode == ChartTools::Mode::DrawHLine)
        ImGui::TextColored({1.f, 0.6f, 0.f, 1.f},
            "H-Line  --  click to place  |  H = toggle  |  L = clear  |  Esc = cancel");
    if (tools.mode == ChartTools::Mode::DrawTrade) {
        ImVec4 tc = tools.trade_buy ? ImVec4(0.3f,1.f,0.4f,1.f) : ImVec4(1.f,0.35f,0.35f,1.f);
        ImGui::TextColored(tc, "%s  --  click to place  |  W = buy/sell  |  Esc = cancel",
            tools.trade_buy ? "BUY" : "SELL");
    }

    // ── Plot ────────────────────────────────────────────────────────────
    char title[256];
    snprintf(title, sizeof(title), "%s – LTP",
             display_name(state.selected_instrument, state).c_str());

    // Suppress ImPlot's own panning/zooming while Shift is held so our
    // rectangle drag doesn't fight with it.
    ImPlotFlags plot_flags = (shift || tools.rect_active)
                             ? ImPlotFlags_NoInputs : ImPlotFlags_None;

    if (ImPlot::BeginPlot(title, ImVec2(-1, -1), plot_flags)) {
        ImPlot::SetupAxes(nullptr, "Price");
        ImPlot::SetupAxisScale(ImAxis_X1, ImPlotScale_Time);
        ImPlot::SetupAxisLinks(ImAxis_X1, &state.view_x_min, &state.view_x_max);

        double ymin = *std::min_element(state.chart_y.begin(), state.chart_y.end());
        double ymax = *std::max_element(state.chart_y.begin(), state.chart_y.end());
        double margin = std::max((ymax - ymin) * 0.05, 1.0);

        if (state.live_mode) {
            // Live: keep X pinned to latest data so chart auto-scrolls.
            // Y fits once per instrument, then user can zoom.
            ImPlot::SetupAxisLimits(ImAxis_X1,
                state.chart_x.front(), state.chart_x.back(), ImGuiCond_Always);
            ImPlot::SetupAxisLimits(ImAxis_Y1, ymin - margin, ymax + margin, ImGuiCond_Once);
        } else {
            // Offline: fit both axes once after instrument change, then step back
            // and let the user pan/zoom freely.
            if (state.chart_fit_pending) {
                ImPlot::SetupAxisLimits(ImAxis_X1,
                    state.chart_x.front(), state.chart_x.back(), ImGuiCond_Always);
                ImPlot::SetupAxisLimits(ImAxis_Y1,
                    ymin - margin, ymax + margin, ImGuiCond_Always);
                state.chart_fit_pending = false;
            }
            // Not calling SetupAxisLimits at all lets ImPlot keep whatever the user set.
        }

        // ── Chart data ──
        if (state.has_latest && state.latest.cp > 0) {
            ImPlot::SetNextFillStyle(IMPLOT_AUTO_COL, 0.15f);
            ImPlot::PlotShaded("LTP",
                state.chart_x.data(), state.chart_y.data(),
                (int)state.chart_x.size(), state.latest.cp);
        }
        {
            const auto& cl = state.theme.chart_line;
            ImPlot::SetNextLineStyle({cl[0],cl[1],cl[2],cl[3]}, 1.5f);
            ImPlot::PlotLine("LTP",
                state.chart_x.data(), state.chart_y.data(),
                (int)state.chart_x.size());
        }
        if (state.has_latest && state.latest.cp > 0) {
            double xs[2] = {state.chart_x.front(), state.chart_x.back()};
            double ys[2] = {state.latest.cp, state.latest.cp};
            const auto& ll = state.theme.close_line;
            ImPlot::SetNextLineStyle({ll[0],ll[1],ll[2],ll[3]}, 1.f);
            ImPlot::PlotLine("Close", xs, ys, 2);
        }

        // ── Horizontal lines (draggable; right-click to remove) ──────
        {
            static const ImVec4 HL_COL = {1.f, 0.55f, 0.f, 0.9f};
            for (int i = 0; i < (int)tools.hlines.size(); ) {
                ImPlot::DragLineY(i, &tools.hlines[i], HL_COL, 1.5f);
                // Price label at the right edge
                if (!state.chart_x.empty())
                    ImPlot::Annotation(state.chart_x.back(), tools.hlines[i],
                        HL_COL, {6.f, 0.f}, true, "%.2f", tools.hlines[i]);
                // Right-click within ~8 px of this line → delete
                if (ImPlot::IsPlotHovered()
                        && ImGui::IsMouseClicked(ImGuiMouseButton_Right)) {
                    ImVec2 line_px  = ImPlot::PlotToPixels(
                        ImPlot::GetPlotMousePos().x, tools.hlines[i]);
                    if (std::abs(line_px.y - ImGui::GetMousePos().y) < 8.f) {
                        tools.hlines.erase(tools.hlines.begin() + i);
                        continue;
                    }
                }
                ++i;
            }
        }

        // ── H-Line placement mode ─────────────────────────────────────
        if (tools.mode == ChartTools::Mode::DrawHLine
                && ImPlot::IsPlotHovered()) {
            double my = ImPlot::GetPlotMousePos().y;
            // Ghost line annotation following the cursor
            ImPlot::Annotation(state.chart_x.back(), my,
                {1.f, 0.55f, 0.f, 0.45f}, {6.f, 0.f}, true, "%.2f ←click", my);
            if (ImGui::IsMouseClicked(ImGuiMouseButton_Left)) {
                tools.hlines.push_back(my);
                // Stay in mode so multiple lines can be placed
            }
        }

        // ── Trade tool placement ──────────────────────────────────────
        if (tools.mode == ChartTools::Mode::DrawTrade
                && ImPlot::IsPlotHovered()) {
            double my = ImPlot::GetPlotMousePos().y;
            bool   is_buy = tools.trade_buy;
            ImVec4 ghost  = is_buy ? ImVec4(0.3f,1.f,0.4f,0.4f) : ImVec4(1.f,0.35f,0.35f,0.4f);
            ImPlot::Annotation(!state.chart_x.empty() ? state.chart_x.back() : 0,
                my, ghost, {6.f, 0.f}, true, "%.2f  (%s) <-click", my, is_buy?"BUY":"SELL");
            if (ImGui::IsMouseClicked(ImGuiMouseButton_Left)) {
                TradeSetup& tr = state.trade;
                tr.placed   = true;
                tr.buy_mode = is_buy;
                tr.entry    = my;
                update_trade(tr);
            }
        }

        // ── Trade rendering ───────────────────────────────────────────
        if (state.trade.placed) {
            TradeSetup& tr = state.trade;
            bool  buy      = tr.buy_mode;
            ImVec4 entry_col = buy ? ImVec4(0.3f,1.f,0.4f,0.9f) : ImVec4(1.f,0.35f,0.35f,0.9f);
            ImVec4 be_col    = ImVec4(1.f,0.85f,0.2f,0.85f);

            // Entry line (draggable — user can fine-tune price)
            double ep = tr.entry;
            ImPlot::DragLineY(9999, &ep, entry_col, 2.0f);
            if (ep != tr.entry) { tr.entry = ep; update_trade(tr); }

            // Entry label
            if (!state.chart_x.empty()) {
                char elbl[128];
                snprintf(elbl, sizeof(elbl), "%s @ %.2f  x%d  chg: Rs%.2f",
                    buy?"BUY":"SELL", tr.entry, tr.shares, tr.charges);
                ImPlot::Annotation(state.chart_x.back(), tr.entry,
                    entry_col, {6.f, -4.f}, true, "%s", elbl);
            }

            // Breakeven line
            double be = tr.breakeven;
            ImPlot::SetNextLineStyle(be_col, 1.5f);
            {
                double xs[2] = { state.chart_x.empty()?0:state.chart_x.front(),
                                 state.chart_x.empty()?1:state.chart_x.back() };
                double ys[2] = { be, be };
                ImPlot::PlotLine("##be", xs, ys, 2);
            }
            if (!state.chart_x.empty()) {
                double be_dist = std::abs(tr.breakeven - tr.entry);
                ImPlot::Annotation(state.chart_x.back(), be,
                    be_col, {6.f, 4.f}, true,
                    "BE %.2f  (+%.2f)", be, be_dist);
            }
        }

        // ── Shift+drag rectangle ──────────────────────────────────────
        if (ImPlot::IsPlotHovered() && shift
                && ImGui::IsMouseClicked(ImGuiMouseButton_Left)) {
            auto mp = ImPlot::GetPlotMousePos();
            tools.rect_active  = true;
            tools.rect_visible = false;
            tools.rx0 = mp.x;  tools.ry0 = mp.y;
            tools.rx1 = mp.x;  tools.ry1 = mp.y;
        }
        if (tools.rect_active) {
            auto mp = ImPlot::GetPlotMousePos();
            tools.rx1 = mp.x;  tools.ry1 = mp.y;
            if (!ImGui::IsMouseDown(ImGuiMouseButton_Left)) {
                tools.rect_active  = false;
                tools.rect_visible = true;
            }
        }

        // ── Draw box + stats ─────────────────────────────────────────
        if (tools.rect_active || tools.rect_visible) {
            double x0 = std::min(tools.rx0, tools.rx1);
            double x1 = std::max(tools.rx0, tools.rx1);
            double y0 = std::min(tools.ry0, tools.ry1);
            double y1 = std::max(tools.ry0, tools.ry1);

            ImVec2 px0 = ImPlot::PlotToPixels(x0, y1); // top-left in screen
            ImVec2 px1 = ImPlot::PlotToPixels(x1, y0); // bottom-right

            ImDrawList* dl = ImPlot::GetPlotDrawList();
            dl->AddRectFilled(px0, px1, IM_COL32(255, 200, 0, 22));
            dl->AddRect      (px0, px1, IM_COL32(255, 200, 0, 210), 0, 0, 1.5f);

            // Stats: price change from y-anchor to y-end, ticks on x
            double price_from = tools.ry0;
            double price_to   = tools.ry1;
            double chg        = price_to - price_from;
            double chg_pct    = (price_from != 0) ? chg / std::abs(price_from) * 100.0 : 0;
            int    n_ticks    = (int)std::round(std::abs(tools.rx1 - tools.rx0));

            // Resolve tick indices to timestamps for time delta
            int i0 = std::max(0, std::min((int)std::round(std::min(tools.rx0, tools.rx1)),
                                          (int)state.chart_ts.size() - 1));
            int i1 = std::max(0, std::min((int)std::round(std::max(tools.rx0, tools.rx1)),
                                          (int)state.chart_ts.size() - 1));

            // Build single annotation with all stats
            char ann[128];
            if (!state.chart_ts.empty() && i0 != i1) {
                int delta_sec = ts_to_sec(state.chart_ts[i1]) - ts_to_sec(state.chart_ts[i0]);
                snprintf(ann, sizeof(ann), "%+.2f  (%+.2f%%)  |  %d ticks  |  %s",
                    chg, chg_pct, n_ticks, fmt_delta(delta_sec).c_str());
            } else {
                snprintf(ann, sizeof(ann), "%+.2f  (%+.2f%%)  |  %d ticks",
                    chg, chg_pct, n_ticks);
            }
            ImPlot::Annotation(x1, y1,
                {1.f, 0.8f, 0.f, 1.f}, {6.f, -4.f}, true, "%s", ann);
        }

        // ── Hover tooltip ─────────────────────────────────────────────
        if (tools.hover_details && ImPlot::IsPlotHovered() && !shift) {
            ImPlotPoint mp = ImPlot::GetPlotMousePos();
            int idx = (int)std::round(mp.x);
            if (idx >= 0 && idx < (int)state.chart_y.size()) {
                double price = state.chart_y[idx];
                double ref   = (state.has_latest && state.latest.cp > 0)
                               ? state.latest.cp : price;
                double chg     = price - ref;
                double chg_pct = (ref != 0) ? chg / ref * 100.0 : 0;

                ImGui::BeginTooltip();
                ImGui::Text("Price   %.2f", price);
                ImGui::Text("vs Prev %+.2f  (%+.2f%%)", chg, chg_pct);
                if (idx < (int)state.chart_ts.size()) {
                    // Show just HH:MM:SS from ISO timestamp
                    const auto& ts = state.chart_ts[idx];
                    ImGui::TextDisabled("%s",
                        ts.size() >= 19 ? ts.substr(11, 8).c_str() : ts.c_str());
                }
                ImGui::Text("Tick    %d / %d", idx + 1, (int)state.chart_y.size());
                ImGui::EndTooltip();
            }
        }

        // On-demand loading: only when the user has panned past the loaded boundary.
        // At default zoom xr.Min == chart_x.front() exactly, so no spurious loads.
        if (!state.live_mode && !state.chart_x.empty()) {
            ImPlotRange xr = ImPlot::GetPlotLimits().X;
            if (xr.Min < state.chart_x.front())
                state.load_older();
            if (xr.Max > state.chart_x.back())
                state.load_newer();
        }

        ImPlot::EndPlot();
    }
    ImGui::End();
}

// ─── Panel: Stats ───────────────────────────────────────────────────────────

static void panel_stats(AppState& state) {
    if (!state.panels.stats) return;
    ImGui::Begin("Stats", &state.panels.stats);
    if (!state.has_latest) { ImGui::TextDisabled("No data yet…"); ImGui::End(); return; }

    const Tick& t  = state.latest;
    double chg     = (t.cp > 0) ? (t.ltp - t.cp) : 0;
    double chg_pct = (t.cp > 0) ? (chg / t.cp * 100.0) : 0;

    ImGui::SeparatorText("Price");
    ImGui::Text("LTP  "); ImGui::SameLine(); colored_text(t.ltp, t.cp, "%.2f");
    ImGui::Text("Chg  "); ImGui::SameLine(); colored_text(chg, 0.0, "%+.2f");
    ImGui::SameLine(); ImGui::Text("("); ImGui::SameLine();
    colored_text(chg_pct, 0.0, "%+.2f%%");
    ImGui::SameLine(); ImGui::Text(")");

    ImGui::Spacing();
    ImGui::SeparatorText("OHLC");
    ImGui::Text("Open  %.2f", t.open);
    ImGui::Text("High  %.2f", t.high);
    ImGui::Text("Low   %.2f", t.low);
    ImGui::Text("Close %.2f", t.cp);

    ImGui::Spacing();
    ImGui::SeparatorText("Greeks / Stats");
    ImGui::Text("ATP   %.2f", t.atp);
    ImGui::Text("Vol   %.0f", t.vtt);
    ImGui::Text("OI    %.0f", t.oi);
    ImGui::Text("IV    %.4f", t.iv);
    ImGui::Text("TBQ   %.0f", t.tbq);
    ImGui::Text("TSQ   %.0f", t.tsq);

    ImGui::Spacing();
    ImGui::Text("Last  %s", t.timestamp.c_str());
    ImGui::End();
}

// ─── Panel: Order Book Depth ────────────────────────────────────────────────

static void panel_depth(AppState& state) {
    if (!state.panels.depth) return;
    ImGui::Begin("Order Book Depth", &state.panels.depth);
    if (!state.has_latest) { ImGui::TextDisabled("No data yet…"); ImGui::End(); return; }

    const Tick& t = state.latest;

    struct Level { double price, qty; bool is_bid; };
    std::vector<Level> levels;
    levels.reserve(10);
    for (int i = 0; i < 5; ++i) {
        if (t.ask_p[i] > 0) levels.push_back({t.ask_p[i], t.ask_q[i], false});
        if (t.bid_p[i] > 0) levels.push_back({t.bid_p[i], t.bid_q[i], true});
    }
    std::sort(levels.begin(), levels.end(), [](const Level& a, const Level& b) {
        return a.price > b.price;
    });

    double max_q = 1.0;
    for (const auto& lv : levels) max_q = std::max(max_q, lv.qty);

    double best_bid = 0, best_ask = 1e18;
    for (const auto& lv : levels) {
        if ( lv.is_bid) best_bid = std::max(best_bid, lv.price);
        if (!lv.is_bid) best_ask = std::min(best_ask, lv.price);
    }

    const float ROW_H   = ImGui::GetTextLineHeightWithSpacing();
    const float price_w = 90.f;
    ImDrawList* draw    = ImGui::GetWindowDrawList();

    const auto bid_fill = state.theme.bid_col;
    const auto ask_fill = state.theme.ask_col;
    const ImU32 bid_col = IM_COL32(
        (int)(bid_fill[0]*255), (int)(bid_fill[1]*255),
        (int)(bid_fill[2]*255), (int)(bid_fill[3]*255));
    const ImU32 ask_col = IM_COL32(
        (int)(ask_fill[0]*255), (int)(ask_fill[1]*255),
        (int)(ask_fill[2]*255), (int)(ask_fill[3]*255));

    if (ImGui::BeginTable("depth_table", 3,
            ImGuiTableFlags_BordersInnerV | ImGuiTableFlags_SizingStretchSame)) {
        ImGui::TableSetupColumn("Bid Qty", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableSetupColumn("Price",   ImGuiTableColumnFlags_WidthFixed, price_w);
        ImGui::TableSetupColumn("Ask Qty", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableHeadersRow();

        bool spread_drawn = false;
        for (const auto& lv : levels) {
            if (!spread_drawn && lv.is_bid) {
                // Spread row
                ImGui::TableNextRow();
                ImGui::TableSetColumnIndex(1);
                double spread = (best_ask < 1e17) ? best_ask - best_bid : 0.0;
                ImGui::TextDisabled("sprd %.2f", spread);
                spread_drawn = true;
            }

            ImGui::TableNextRow();

            // Bid qty (left col, right-aligned, bar grows ←)
            ImGui::TableSetColumnIndex(0);
            if (lv.is_bid) {
                ImVec2 pos = ImGui::GetCursorScreenPos();
                float  cw  = ImGui::GetContentRegionAvail().x;
                float  bw  = (float)(lv.qty / max_q) * cw;
                draw->AddRectFilled(
                    {pos.x + cw - bw, pos.y + 2}, {pos.x + cw, pos.y + ROW_H - 2},
                    bid_col);
                char buf[32]; snprintf(buf, sizeof(buf), "%.0f", lv.qty);
                ImGui::SetCursorPosX(ImGui::GetCursorPosX() + cw - ImGui::CalcTextSize(buf).x);
                ImGui::TextColored({bid_fill[0]+0.2f, bid_fill[1]+0.3f, bid_fill[2]+0.2f, 1.f},
                                   "%s", buf);
            }

            // Price (center col)
            ImGui::TableSetColumnIndex(1);
            bool hi = (lv.price == best_bid || lv.price == best_ask);
            if (hi) ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.f, 0.85f, 0.2f, 1.f));
            ImGui::Text("%.2f", lv.price);
            if (hi) ImGui::PopStyleColor();

            // Ask qty (right col, bar grows →)
            ImGui::TableSetColumnIndex(2);
            if (!lv.is_bid) {
                ImVec2 pos = ImGui::GetCursorScreenPos();
                float  cw  = ImGui::GetContentRegionAvail().x;
                float  bw  = (float)(lv.qty / max_q) * cw;
                draw->AddRectFilled(
                    {pos.x, pos.y + 2}, {pos.x + bw, pos.y + ROW_H - 2},
                    ask_col);
                ImGui::TextColored({ask_fill[0]+0.3f, ask_fill[1]+0.2f, ask_fill[2]+0.2f, 1.f},
                                   "%.0f", lv.qty);
            }
        }
        ImGui::EndTable();
    }
    ImGui::End();
}

// ─── Panel: Theme ───────────────────────────────────────────────────────────

static const char* k_presets[] = {"Dark", "Light", "Classic"};

// ─── Panel: Trade Settings ───────────────────────────────────────────────────

static void panel_trade_settings(AppState& state) {
    if (!state.trade.show) return;
    ImGui::Begin("Trade Settings", &state.trade.show,
        ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoCollapse);

    TradeSetup& tr = state.trade;

    ImGui::SeparatorText("Capital");
    ImGui::SetNextItemWidth(160);
    if (ImGui::InputFloat("Capital (Rs)", &tr.capital, 1000, 10000, "%.0f"))
        update_trade(tr);
    ImGui::SetNextItemWidth(100);
    if (ImGui::InputFloat("Leverage", &tr.leverage, 1, 5, "%.1fx"))
        update_trade(tr);

    double wc = (double)tr.capital * tr.leverage;
    ImGui::TextDisabled("Working capital: Rs %.0f", wc);

    if (tr.placed) {
        ImGui::Spacing();
        ImGui::SeparatorText("Active Trade");
        ImGui::TextColored(tr.buy_mode ? ImVec4(0.3f,1.f,0.4f,1.f) : ImVec4(1.f,0.35f,0.35f,1.f),
            "%s @ %.2f  x%d", tr.buy_mode?"BUY":"SELL", tr.entry, tr.shares);
        ImGui::Text("Breakeven   %.2f  (%.2f)", tr.breakeven, std::abs(tr.breakeven-tr.entry));

        // Charge breakdown
        ImGui::Spacing();
        ImGui::SeparatorText("Charges (round-trip)");
        double bt = tr.entry * tr.shares;
        double st = bt;
        double brokerage   = std::min(20.0,bt*0.001) + std::min(20.0,st*0.001);
        double stt         = st * 0.00025;
        double transaction = (bt+st) * 0.0000307;
        double ipft        = (bt+st) * 0.000001;
        double sebi        = (bt+st) * 0.000001;
        double stamp       = bt * 0.00003;
        double gst         = (brokerage + transaction + ipft) * 0.18;
        double total       = brokerage+stt+transaction+ipft+sebi+stamp+gst;

        auto row = [](const char* label, double val) {
            ImGui::Text("  %-18s", label);
            ImGui::SameLine(160);
            ImGui::Text("Rs %8.2f", val);
        };
        row("Brokerage",    brokerage);
        row("STT",          stt);
        row("Transaction",  transaction);
        row("IPFT",         ipft);
        row("GST (18%)",    gst);
        row("SEBI",         sebi);
        row("Stamp",        stamp);
        ImGui::Separator();
        ImGui::Text("  %-18s", "Total");
        ImGui::SameLine(160);
        ImGui::TextColored({1.f,0.8f,0.2f,1.f}, "Rs %8.2f", total);

        ImGui::Spacing();
        if (ImGui::Button("Clear trade")) tr.placed = false;
    }

    ImGui::Spacing();
    ImGui::SeparatorText("Shortcuts");
    ImGui::TextDisabled("T  = toggle trade tool (buy)");
    ImGui::TextDisabled("W  = flip buy / sell");
    ImGui::TextDisabled("Esc = cancel / clear trade");

    ImGui::End();
}

static void panel_theme(AppState& state) {
    if (!state.theme.show) return;
    ImGui::Begin("Theme", &state.theme.show,
                 ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoCollapse);

    ThemeSettings& t  = state.theme;
    bool changed      = false;

    // ── Preset ──
    ImGui::SeparatorText("Base Preset");
    for (int i = 0; i < 3; ++i) {
        if (i > 0) ImGui::SameLine();
        bool sel = (t.preset == i);
        if (sel) ImGui::PushStyleColor(ImGuiCol_Button,
                     ImGui::GetStyleColorVec4(ImGuiCol_ButtonActive));
        if (ImGui::Button(k_presets[i], {70, 0})) { t.preset = i; changed = true; }
        if (sel) ImGui::PopStyleColor();
    }

    // ── ImGui colours ──
    ImGui::Spacing();
    ImGui::SeparatorText("Colours");
    constexpr ImGuiColorEditFlags kCF = ImGuiColorEditFlags_NoAlpha
                                      | ImGuiColorEditFlags_NoOptions;
    changed |= ImGui::ColorEdit4("Accent",     t.accent,   kCF);
    changed |= ImGui::ColorEdit4("Window BG",  t.win_bg,   kCF);
    changed |= ImGui::ColorEdit4("Frame BG",   t.frame_bg, kCF);
    changed |= ImGui::ColorEdit4("Popup BG",   t.popup_bg, kCF);
    changed |= ImGui::ColorEdit4("Text",       t.text_col, kCF);

    // ── Shape & spacing ──
    ImGui::Spacing();
    ImGui::SeparatorText("Shape & Spacing");
    changed |= ImGui::SliderFloat("Rounding",     &t.rounding,    0.f, 12.f, "%.1f");
    changed |= ImGui::SliderFloat("Border Size",  &t.border_sz,   0.f, 2.f,  "%.1f");
    changed |= ImGui::SliderFloat("Item Spacing", &t.item_spacing, 0.f, 12.f, "%.0f px");

    // ── Chart colours ──
    ImGui::Spacing();
    ImGui::SeparatorText("Chart");
    changed |= ImGui::ColorEdit4("LTP Line",   t.chart_line, kCF);
    changed |= ImGui::ColorEdit4("Close Line", t.close_line, ImGuiColorEditFlags_NoOptions);

    // ── Depth colours ──
    ImGui::Spacing();
    ImGui::SeparatorText("Depth");
    changed |= ImGui::ColorEdit4("Bid Fill", t.bid_col, ImGuiColorEditFlags_NoOptions);
    changed |= ImGui::ColorEdit4("Ask Fill", t.ask_col, ImGuiColorEditFlags_NoOptions);

    if (changed) t.apply();

    // ── Persist ──
    ImGui::Spacing();
    ImGui::Separator();
    if (ImGui::Button("Save theme")) t.save("theme.cfg");
    ImGui::SameLine();
    if (ImGui::Button("Reload"))     { t.load("theme.cfg"); t.apply(); }

    ImGui::End();
}

// ─── Backtest Results panel ──────────────────────────────────────────────────

// Tiny JSON key-value extractor: finds the first occurrence of "key": value
// and returns the value as a string.  Handles strings, numbers, booleans.
static std::string json_get(const std::string& json, const char* key) {
    std::string needle = std::string("\"") + key + "\":";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos += needle.size();
    while (pos < json.size() && json[pos] == ' ') ++pos;
    if (pos >= json.size()) return "";
    if (json[pos] == '"') {
        ++pos;
        auto end = json.find('"', pos);
        return (end != std::string::npos) ? json.substr(pos, end - pos) : "";
    }
    auto end = json.find_first_of(",}", pos);
    return (end != std::string::npos) ? json.substr(pos, end - pos) : json.substr(pos);
}

static void panel_backtest(AppState& state) {
    if (!state.panels.backtest) return;

    ImGui::Begin("Backtest Results", &state.panels.backtest);
    BacktestPanelState& bp = state.backtest_panel;

    // ── Toolbar ──────────────────────────────────────────────────────────────
    if (ImGui::Button("Refresh")) {
        if (!state.bkdb.is_open()) state.bkdb.open(state.bkdb_path);
        bp.runs         = state.bkdb.list_runs();
        bp.runs_loaded  = true;
        bp.selected_run = -1;
        bp.inst_equity.clear();
        bp.inst_stats.clear();
    }
    if (!bp.runs_loaded) {
        bp.runs        = state.bkdb.list_runs();
        bp.runs_loaded = true;
    }
    if (!state.bkdb.is_open()) {
        ImGui::SameLine();
        ImGui::TextDisabled("(backtest_results.db not found)");
        ImGui::End(); return;
    }
    if (bp.runs.empty()) {
        ImGui::TextDisabled("No runs found.");
        ImGui::End(); return;
    }

    // ── Run selector ─────────────────────────────────────────────────────────
    ImGui::SeparatorText("Runs");
    float list_h = ImGui::GetTextLineHeightWithSpacing() *
                   std::min((int)bp.runs.size(), 6) + 4.f;
    ImGui::BeginChild("##bt_runs", {0.f, list_h}, true);
    for (int i = 0; i < (int)bp.runs.size(); ++i) {
        const auto& r = bp.runs[i];
        char label[128];
        snprintf(label, sizeof(label), "[%d] %s  %s",
                 r.run_id, r.strategy.c_str(), r.run_time.c_str());
        bool sel = (i == bp.selected_run);
        if (ImGui::Selectable(label, sel)) {
            bp.selected_run = i;
            bp.inst_equity  = state.bkdb.instrument_equity(r.run_id);
            bp.inst_stats   = state.bkdb.instrument_stats(r.run_id);
        }
    }
    ImGui::EndChild();

    if (bp.selected_run < 0 || bp.selected_run >= (int)bp.runs.size()) {
        ImGui::TextDisabled("Select a run above.");
        ImGui::End(); return;
    }

    const BacktestRun& run = bp.runs[bp.selected_run];

    // ── Summary stats ─────────────────────────────────────────────────────────
    ImGui::SeparatorText("Summary");
    {
        const std::string& j = run.summary_json;
        auto get = [&](const char* k) { return json_get(j, k); };
        ImGui::Columns(4, "##bt_summary", false);
        ImGui::Text("Trades:     %s",      get("n_trades").c_str());
        ImGui::NextColumn();
        ImGui::Text("Win%%:      %s%%",    get("win_rate_pct").c_str());
        ImGui::NextColumn();
        ImGui::Text("Top5%% Win: %s%%",   get("win_rate_top5pct_pct").c_str());
        ImGui::NextColumn();
        ImGui::Text("MaxDD:      %s%%",    get("max_drawdown_pct").c_str());
        ImGui::Columns(1);
    }

    // ── Top 5 instruments ────────────────────────────────────────────────────
    ImGui::SeparatorText("Top 5 Instruments");
    {
        int top5 = std::min((int)bp.inst_stats.size(), 5);
        for (int i = 0; i < top5; ++i) {
            std::string name = display_name(bp.inst_stats[i].instrument_key, state);
            if (i > 0) ImGui::SameLine(0.f, 20.f);
            ImGui::Text("%d. %s (+%.2f%%)", i + 1, name.c_str(),
                        bp.inst_stats[i].final_return_pct);
        }
    }

    // ── Equity curves (top 5 instruments) ────────────────────────────────────
    ImGui::SeparatorText("Equity Curve (Top 5)");
    if (ImPlot::BeginPlot("##bt_eq", {-1.f, 220.f})) {
        ImPlot::SetupAxes("Time", "Equity");
        ImPlot::SetupAxisScale(ImAxis_X1, ImPlotScale_Time);
        for (const auto& ie : bp.inst_equity) {
            if (ie.x.empty()) continue;
            std::string lbl = display_name(ie.key, state);
            ImPlot::PlotLine(lbl.c_str(), ie.x.data(), ie.y.data(), (int)ie.x.size());
        }
        ImPlot::EndPlot();
    }

    // ── Instrument table (top 5%ile) ─────────────────────────────────────────
    ImGui::SeparatorText("Top 5%ile Instruments");
    float avail = ImGui::GetContentRegionAvail().y;
    ImGui::BeginChild("##bt_stats", {0.f, avail}, false);
    if (ImGui::BeginTable("##bt_stat_tbl", 5,
            ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg |
            ImGuiTableFlags_ScrollY | ImGuiTableFlags_SizingStretchProp)) {
        ImGui::TableSetupScrollFreeze(0, 1);
        ImGui::TableSetupColumn("Instrument",  ImGuiTableColumnFlags_WidthStretch, 3.f);
        ImGui::TableSetupColumn("Sharpe",      ImGuiTableColumnFlags_WidthFixed,  60.f);
        ImGui::TableSetupColumn("MaxDD",       ImGuiTableColumnFlags_WidthFixed,  65.f);
        ImGui::TableSetupColumn("Trades",      ImGuiTableColumnFlags_WidthFixed,  55.f);
        ImGui::TableSetupColumn("Return",      ImGuiTableColumnFlags_WidthFixed,  70.f);
        ImGui::TableHeadersRow();

        for (const auto& st : bp.inst_stats) {
            ImGui::TableNextRow();
            std::string name = display_name(st.instrument_key, state);
            ImGui::TableSetColumnIndex(0); ImGui::TextUnformatted(name.c_str());
            ImGui::TableSetColumnIndex(1); ImGui::Text("%.2f",   st.sharpe);
            ImGui::TableSetColumnIndex(2); ImGui::Text("%.2f%%", st.max_drawdown_pct);
            ImGui::TableSetColumnIndex(3); ImGui::Text("%d",     st.n_trades);
            ImGui::TableSetColumnIndex(4);
            if (st.final_return_pct >= 0)
                ImGui::TextColored({0.2f,0.9f,0.3f,1.f}, "+%.2f%%", st.final_return_pct);
            else
                ImGui::TextColored({0.9f,0.2f,0.2f,1.f}, "%.2f%%",  st.final_return_pct);
        }
        ImGui::EndTable();
    }
    ImGui::EndChild();

    ImGui::End();
}

// ─── DockSpace host + menu bar ──────────────────────────────────────────────

static void build_default_layout(ImGuiID ds_id, ImVec2 size) {
    ImGui::DockBuilderRemoveNode(ds_id);
    ImGui::DockBuilderAddNode(ds_id, ImGuiDockNodeFlags_DockSpace);
    ImGui::DockBuilderSetNodeSize(ds_id, size);

    // Split: left strip (instruments) | rest
    ImGuiID left, rest;
    ImGui::DockBuilderSplitNode(ds_id, ImGuiDir_Left, 0.18f, &left, &rest);

    // Split rest: right strip (stats + depth) | center (chart)
    ImGuiID right, center;
    ImGui::DockBuilderSplitNode(rest, ImGuiDir_Right, 0.22f, &right, &center);

    // Split right strip: top (stats) | bottom (depth)
    ImGuiID right_top, right_bot;
    ImGui::DockBuilderSplitNode(right, ImGuiDir_Up, 0.42f, &right_top, &right_bot);

    ImGui::DockBuilderDockWindow("Instruments",      left);
    ImGui::DockBuilderDockWindow("LTP Chart",        center);
    ImGui::DockBuilderDockWindow("Stats",            right_top);
    ImGui::DockBuilderDockWindow("Order Book Depth", right_bot);
    ImGui::DockBuilderFinish(ds_id);
}

static void render_dockspace(AppState& state) {
    ImGuiViewport* vp = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(vp->WorkPos);
    ImGui::SetNextWindowSize(vp->WorkSize);
    ImGui::SetNextWindowViewport(vp->ID);

    ImGuiWindowFlags host_flags =
        ImGuiWindowFlags_NoDocking        |
        ImGuiWindowFlags_NoTitleBar       |
        ImGuiWindowFlags_NoCollapse       |
        ImGuiWindowFlags_NoResize         |
        ImGuiWindowFlags_NoMove           |
        ImGuiWindowFlags_NoBringToFrontOnFocus |
        ImGuiWindowFlags_NoNavFocus       |
        ImGuiWindowFlags_MenuBar;

    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding,   0.f);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.f);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding,    {0.f, 0.f});
    ImGui::Begin("##dock_host", nullptr, host_flags);
    ImGui::PopStyleVar(3);

    // ── Menu bar (embedded in host window) ──────────────────────────────
    if (ImGui::BeginMenuBar()) {
        if (ImGui::BeginMenu("Layout")) {
            if (ImGui::MenuItem("Save As…"))
                state.layouts.show_modal = true;
            if (ImGui::MenuItem("Reset to default")) {
                // Rebuild layout next frame
                ImGuiID ds = ImGui::GetID("MainDS");
                build_default_layout(ds, vp->WorkSize);
            }
            if (!state.layouts.names.empty()) {
                ImGui::Separator();
                for (const auto& name : state.layouts.names)
                    if (ImGui::MenuItem(name.c_str())) {
                        state.layouts.load(name.c_str());
                        // Also restore companion settings
                        std::string cfg = std::string("layouts/") + name + ".cfg";
                        state.load_settings(cfg.c_str());
                    }
            }
            ImGui::EndMenu();
        }
        if (ImGui::BeginMenu("View")) {
            ImGui::SeparatorText("Panels");
            ImGui::MenuItem("Instruments",         nullptr, &state.panels.instruments);
            ImGui::MenuItem("LTP Chart",           nullptr, &state.panels.chart);
            ImGui::MenuItem("Stats",               nullptr, &state.panels.stats);
            ImGui::MenuItem("Order Book Depth",    nullptr, &state.panels.depth);
            ImGui::MenuItem("OB Visualisation",    nullptr, &state.panels.ob_viz);
            ImGui::MenuItem("Backtest Results",    nullptr, &state.panels.backtest);
            ImGui::Separator();
            if (ImGui::MenuItem("Show All")) state.panels.show_all();
            if (ImGui::MenuItem("Hide All")) state.panels.hide_all();
            ImGui::Separator();
            ImGui::MenuItem("Trade Settings…", nullptr, &state.trade.show);
            ImGui::MenuItem("Theme…", nullptr, &state.theme.show);
            ImGui::EndMenu();
        }

        if (ImGui::BeginMenu("Help")) {
            ImGui::SeparatorText("Chart — Drawing");
            ImGui::TextDisabled("  H          Toggle H-Line draw mode");
            ImGui::TextDisabled("  Click      Place horizontal line (in H-Line mode)");
            ImGui::TextDisabled("  R-Click    Remove hovered horizontal line");
            ImGui::TextDisabled("  Shift+Drag Draw measurement box");
            ImGui::TextDisabled("  L          Clear all horizontal lines");
            ImGui::TextDisabled("  B          Clear measurement box");
            ImGui::TextDisabled("  Esc        Cancel mode / clear box");
            ImGui::Spacing();
            ImGui::SeparatorText("Chart — Display");
            ImGui::TextDisabled("  V          Toggle hover tooltip");
            ImGui::Spacing();
            ImGui::SeparatorText("Global");
            ImGui::TextDisabled("  Ctrl+L      Toggle live / offline mode");
            ImGui::TextDisabled("  Space        Spotlight search");
            ImGui::Spacing();
            ImGui::SeparatorText("Trade Tool");
            ImGui::TextDisabled("  T          Toggle trade draw mode");
            ImGui::TextDisabled("  W          Flip buy / sell");
            ImGui::TextDisabled("  Esc        Cancel mode / clear trade");
            ImGui::Spacing();
            ImGui::SeparatorText("Layout");
            ImGui::TextDisabled("  Drag title bar   Dock / undock panel");
            ImGui::TextDisabled("  Drag divider     Resize split");
            ImGui::TextDisabled("  View > Hide All  Clear all panels");
            ImGui::TextDisabled("  Layout > Save    Save current layout");
            ImGui::EndMenu();
        }

        // ── Live / Offline toggle — after Help so it's never hidden ─────
        if (state.live_mode) {
            ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(0.20f, 0.90f, 0.30f, 1.f));
            if (ImGui::MenuItem("[ LIVE ]"))
                state.live_mode = false;
            ImGui::PopStyleColor();
            if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayShort))
                ImGui::SetTooltip("Live — polling DB every 500 ms.\nClick to freeze.");
        } else {
            ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(0.55f, 0.55f, 0.55f, 1.f));
            if (ImGui::MenuItem("[ OFFLINE ]")) {
                state.live_mode  = true;
                state.needs_load = true;
            }
            ImGui::PopStyleColor();
            if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayShort))
                ImGui::SetTooltip("Offline — data frozen at last snapshot.\nClick to resume live.");
        }

        ImGui::EndMenuBar();
    }

    // ── DockSpace ────────────────────────────────────────────────────────
    ImGuiID ds_id = ImGui::GetID("MainDS");
    ImGui::DockSpace(ds_id, {0.f, 0.f}, ImGuiDockNodeFlags_None);

    // Build default layout on very first launch (no ini docking data)
    static bool layout_ready = false;
    if (!layout_ready) {
        layout_ready = true;
        if (ImGui::DockBuilderGetNode(ds_id) == nullptr)
            build_default_layout(ds_id, vp->WorkSize);
    }

    // ── Save-layout modal ────────────────────────────────────────────────
    if (state.layouts.show_modal) {
        ImGui::OpenPopup("Save Layout");
        state.layouts.show_modal = false;
    }
    if (ImGui::BeginPopupModal("Save Layout", nullptr,
                               ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::Text("Layout name:");
        ImGui::SetNextItemWidth(220.f);
        ImGui::InputText("##lname", state.layouts.buf, sizeof(state.layouts.buf));
        ImGui::Spacing();
        if (ImGui::Button("Save", {100, 0})) {
            if (state.layouts.buf[0] != '\0') {
                state.layouts.save_current(state.layouts.buf);
                // Companion cfg stores panel visibility, trade settings, mode
                std::string cfg = std::string("layouts/") + state.layouts.buf + ".cfg";
                state.save_settings(cfg.c_str());
            }
            state.layouts.buf[0] = '\0';
            ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine();
        if (ImGui::Button("Cancel", {100, 0})) {
            state.layouts.buf[0] = '\0';
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
    }

    ImGui::End();
}

// ─── Panel: Order Book Visualisation ────────────────────────────────────────

static void panel_ob_viz(AppState& state) {
    if (!state.panels.ob_viz) return;
    ImGui::Begin("OB Visualisation", &state.panels.ob_viz);

    ChartTools& tools = state.chart_tools;
    ObVizState& ob = state.ob_viz;

    if (tools.mode == ChartTools::Mode::DrawHLine)
        ImGui::TextColored({1.f, 0.6f, 0.f, 1.f},
            "H-Line  --  click to place  |  H = toggle  |  L = clear  |  Esc = cancel");

    // Register custom colormaps once (transparent → colour)
    static ImPlotColormap BID_CMAP = -1;
    static ImPlotColormap ASK_CMAP = -1;
    if (BID_CMAP < 0) {
        static const ImVec4 bid_cols[] = {{0.f, 0.f, 0.f, 0.f}, {0.15f, 0.85f, 0.25f, 1.f}};
        static const ImVec4 ask_cols[] = {{0.f, 0.f, 0.f, 0.f}, {0.90f, 0.15f, 0.15f, 1.f}};
        BID_CMAP = ImPlot::AddColormap("BidDepth", bid_cols, 2);
        ASK_CMAP = ImPlot::AddColormap("AskDepth", ask_cols, 2);
    }

    if (state.ob_history.empty()) {
        ImGui::TextDisabled("No data yet…");
        ImGui::End();
        return;
    }

    // ── Mode toggle button ───────────────────────────────────────────────
    {
        const char* label = ob.log_mode ? "Log" : "Lin";
        if (ImGui::SmallButton(label)) {
            ob.log_mode    = !ob.log_mode;
            ob.needs_rebuild = true;
        }
        if (ImGui::IsItemHovered(ImGuiHoveredFlags_DelayShort)) {
            ImGui::BeginTooltip();
            ImGui::TextUnformatted("Volume → saturation mapping");
            ImGui::Separator();
            ImGui::BulletText("Log  — compresses large spikes; reveals thin\n"
                              "       liquidity layers across all levels equally.");
            ImGui::BulletText("Lin  — raw proportional brightness; dominant\n"
                              "       levels stand out, thin ones fade to black.");
            ImGui::EndTooltip();
        }
    }

    // ── Rebuild grid if needed ───────────────────────────────────────────
    if (ob.needs_rebuild || (int)state.ob_history.size() != ob.nticks)
        ob.rebuild(state.ob_history);

    if (ob.nticks == 0 || ob.bid_grid.empty()) {
        ImGui::TextDisabled("Building…");
        ImGui::End();
        return;
    }

    // ── Plot ────────────────────────────────────────────────────────────
    char title[256];
    snprintf(title, sizeof(title), "%s – Depth",
             display_name(state.selected_instrument, state).c_str());

    const bool ob_shift = ImGui::IsKeyDown(ImGuiKey_LeftShift)
                       || ImGui::IsKeyDown(ImGuiKey_RightShift);
    ImPlotFlags plot_flags_ob = ob_shift ? ImPlotFlags_NoInputs : ImPlotFlags_None;

    if (ImPlot::BeginPlot(title, ImVec2(-1, -1), plot_flags_ob)) {
        ImPlot::SetupAxes(nullptr, "Price");
        ImPlot::SetupAxisScale(ImAxis_X1, ImPlotScale_Time);
        ImPlot::SetupAxisLinks(ImAxis_X1, &state.view_x_min, &state.view_x_max);
        if (ob.fit_pending) {
            ImPlot::SetupAxisLimits(ImAxis_X1, ob.time_min, ob.time_max, ImGuiCond_Always);
            ImPlot::SetupAxisLimits(ImAxis_Y1, ob.pmin, ob.pmax, ImGuiCond_Always);
            ob.fit_pending = false;
        }

        ImPlotPoint bmin = {ob.time_min, ob.pmin};
        ImPlotPoint bmax = {ob.time_max, ob.pmax};

        // Bid heatmap (green)
        ImPlot::PushColormap(BID_CMAP);
        ImPlot::PlotHeatmap("##bids",
            ob.bid_grid.data(), ObVizState::BINS, ob.nticks,
            0.0, 1.0, nullptr, bmin, bmax);
        ImPlot::PopColormap();

        // Ask heatmap (red) — blends on top; bids/asks occupy different prices
        ImPlot::PushColormap(ASK_CMAP);
        ImPlot::PlotHeatmap("##asks",
            ob.ask_grid.data(), ObVizState::BINS, ob.nticks,
            0.0, 1.0, nullptr, bmin, bmax);
        ImPlot::PopColormap();



        // ── Shared H-lines ───────────────────────────────────────────
        {
            static const ImVec4 HL_COL = {1.f, 0.55f, 0.f, 0.9f};
            for (int i = 0; i < (int)tools.hlines.size(); ) {
                ImPlot::DragLineY(1000 + i, &tools.hlines[i], HL_COL, 1.5f);
                ImPlot::Annotation(ob.time_max, tools.hlines[i],
                    HL_COL, {6.f, 0.f}, true, "%.2f", tools.hlines[i]);
                if (ImPlot::IsPlotHovered()
                        && ImGui::IsMouseClicked(ImGuiMouseButton_Right)) {
                    ImVec2 lpx = ImPlot::PlotToPixels(ImPlot::GetPlotMousePos().x, tools.hlines[i]);
                    if (std::abs(lpx.y - ImGui::GetMousePos().y) < 8.f) {
                        tools.hlines.erase(tools.hlines.begin() + i);
                        continue;
                    }
                }
                ++i;
            }
        }

        // ── H-Line placement mode ────────────────────────────────────
        if (tools.mode == ChartTools::Mode::DrawHLine && ImPlot::IsPlotHovered()) {
            double my = ImPlot::GetPlotMousePos().y;
            ImPlot::Annotation(ob.time_max, my,
                {1.f, 0.55f, 0.f, 0.45f}, {6.f, 0.f}, true, "%.2f <-click", my);
            if (ImGui::IsMouseClicked(ImGuiMouseButton_Left))
                tools.hlines.push_back(my);
        }

        // ── Shift+drag rectangle ─────────────────────────────────────
        if (ImPlot::IsPlotHovered() && ob_shift
                && ImGui::IsMouseClicked(ImGuiMouseButton_Left)) {
            auto mp = ImPlot::GetPlotMousePos();
            tools.ob_rect_active  = true;
            tools.ob_rect_visible = false;
            tools.ob_rx0 = mp.x;  tools.ob_ry0 = mp.y;
            tools.ob_rx1 = mp.x;  tools.ob_ry1 = mp.y;
        }
        if (tools.ob_rect_active) {
            auto mp = ImPlot::GetPlotMousePos();
            tools.ob_rx1 = mp.x;  tools.ob_ry1 = mp.y;
            if (!ImGui::IsMouseDown(ImGuiMouseButton_Left)) {
                tools.ob_rect_active  = false;
                tools.ob_rect_visible = true;
            }
        }
        if (tools.ob_rect_active || tools.ob_rect_visible) {
            double x0 = std::min(tools.ob_rx0, tools.ob_rx1);
            double x1 = std::max(tools.ob_rx0, tools.ob_rx1);
            double y0 = std::min(tools.ob_ry0, tools.ob_ry1);
            double y1 = std::max(tools.ob_ry0, tools.ob_ry1);
            ImVec2 px0 = ImPlot::PlotToPixels(x0, y1);
            ImVec2 px1 = ImPlot::PlotToPixels(x1, y0);
            ImDrawList* dl = ImPlot::GetPlotDrawList();
            dl->AddRectFilled(px0, px1, IM_COL32(255, 200, 0, 22));
            dl->AddRect      (px0, px1, IM_COL32(255, 200, 0, 210), 0, 0, 1.5f);
            double chg     = tools.ob_ry1 - tools.ob_ry0;
            double chg_pct = (tools.ob_ry0 != 0) ? chg / std::abs(tools.ob_ry0) * 100.0 : 0;
            int    n_ticks = (int)std::round(std::abs(tools.ob_rx1 - tools.ob_rx0));
            // Map DB-ID x values to tick_history indices for timestamps
            int n_th = (int)state.ob_history.size();
            int i0 = 0, i1 = 0;
            if (ob.time_max > ob.time_min && n_th > 0) {
                double span = ob.time_max - ob.time_min;
                i0 = std::clamp((int)((x0 - ob.time_min) / span * (n_th-1)), 0, n_th-1);
                i1 = std::clamp((int)((x1 - ob.time_min) / span * (n_th-1)), 0, n_th-1);
            }
            char ann[128];
            if (!state.chart_ts.empty() && i0 != i1) {
                int dsec = ts_to_sec(state.chart_ts[i1]) - ts_to_sec(state.chart_ts[i0]);
                snprintf(ann, sizeof(ann), "%+.2f (%+.2f%%) | %d ticks | %s",
                    chg, chg_pct, n_ticks, fmt_delta(dsec).c_str());
            } else {
                snprintf(ann, sizeof(ann), "%+.2f (%+.2f%%) | %d ticks",
                    chg, chg_pct, n_ticks);
            }
            ImPlot::Annotation(x1, y1, {1.f, 0.8f, 0.f, 1.f}, {6.f, -4.f}, true, "%s", ann);
        }

        // ── Hover tooltip ────────────────────────────────────────────
        if (tools.hover_details && ImPlot::IsPlotHovered() && !ob_shift) {
            ImPlotPoint mp = ImPlot::GetPlotMousePos();
            // mp.x is a DB id; map linearly to tick_history index
            int ti = 0;
            if (ob.time_max > ob.time_min && !state.ob_history.empty()) {
                double frac = (mp.x - ob.time_min) / (ob.time_max - ob.time_min);
                ti = std::clamp((int)(frac * (state.ob_history.size() - 1)),
                                0, (int)state.ob_history.size() - 1);
            }
            if (ti >= 0 && ti < (int)state.ob_history.size()) {
                const Tick& t = state.ob_history[ti];
                double price  = mp.y;
                // Find nearest bid/ask level
                double best_bid_p = 0, best_bid_q = 0;
                double best_ask_p = 0, best_ask_q = 0;
                double best_bd = 1e18, best_ad = 1e18;
                for (int k = 0; k < 5; ++k) {
                    if (t.bid_p[k] > 0) {
                        double d = std::abs(t.bid_p[k] - price);
                        if (d < best_bd) { best_bd = d; best_bid_p = t.bid_p[k]; best_bid_q = t.bid_q[k]; }
                    }
                    if (t.ask_p[k] > 0) {
                        double d = std::abs(t.ask_p[k] - price);
                        if (d < best_ad) { best_ad = d; best_ask_p = t.ask_p[k]; best_ask_q = t.ask_q[k]; }
                    }
                }
                ImGui::BeginTooltip();
                ImGui::Text("Tick  %d", ti);
                if (ti < (int)state.ob_history.size()) {
                    const std::string& ts = state.ob_history[ti].timestamp;
                    ImGui::TextDisabled("%s", ts.size() >= 19 ? ts.substr(11,8).c_str() : ts.c_str());
                }
                if (best_bid_p > 0) ImGui::TextColored({0.3f,1.f,0.3f,1.f}, "Bid  %.2f  x %.0f", best_bid_p, best_bid_q);
                if (best_ask_p > 0) ImGui::TextColored({1.f,0.3f,0.3f,1.f}, "Ask  %.2f  x %.0f", best_ask_p, best_ask_q);
                ImGui::EndTooltip();
            }
        }

        // ── OB viz independent on-demand loading ─────────────────────
        if (!state.live_mode && !state.ob_history.empty()) {
            ImPlotRange xr = ImPlot::GetPlotLimits().X;
            if (xr.Min < ob.time_min)
                state.ob_load_older();
            if (xr.Max > ob.time_max)
                state.ob_load_newer();
        }

        ImPlot::EndPlot();
    }
    ImGui::End();
}

// ─── Spotlight search ────────────────────────────────────────────────────────

static void panel_spotlight(AppState& state) {
    if (!state.spotlight_open) return;

    ImGuiIO& io = ImGui::GetIO();

    // Dim backdrop — separate window so it sits behind the spotlight
    ImGui::SetNextWindowPos({0, 0});
    ImGui::SetNextWindowSize(io.DisplaySize);
    ImGui::SetNextWindowBgAlpha(0.f);
    ImGui::Begin("##dim", nullptr,
        ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize |
        ImGuiWindowFlags_NoMove     | ImGuiWindowFlags_NoScrollbar |
        ImGuiWindowFlags_NoInputs   | ImGuiWindowFlags_NoNav |
        ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoBringToFrontOnFocus |
        ImGuiWindowFlags_NoFocusOnAppearing);
    ImGui::GetWindowDrawList()->AddRectFilled(
        {0, 0}, io.DisplaySize, IM_COL32(0, 0, 0, 150));
    ImGui::End();

    const ImVec2 BOX = {520, 420};
    ImGui::SetNextWindowPos(
        {(io.DisplaySize.x - BOX.x) * 0.5f, io.DisplaySize.y * 0.22f},
        ImGuiCond_Always);
    ImGui::SetNextWindowSize(BOX, ImGuiCond_Always);
    ImGui::SetNextWindowBgAlpha(0.96f);

    ImGuiWindowFlags wf = ImGuiWindowFlags_NoTitleBar  | ImGuiWindowFlags_NoResize
                        | ImGuiWindowFlags_NoMove      | ImGuiWindowFlags_NoScrollbar
                        | ImGuiWindowFlags_NoSavedSettings;

    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, {12, 12});
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing,   {8, 6});
    if (ImGui::Begin("##spotlight", nullptr, wf)) {

        if (ImGui::IsWindowAppearing()) {
            ImGui::SetKeyboardFocusHere();
            state.spotlight_buf[0] = '\0';
        }

        ImGui::SetNextItemWidth(-1);
        bool entered = ImGui::InputText("##sq", state.spotlight_buf,
            sizeof(state.spotlight_buf),
            ImGuiInputTextFlags_EnterReturnsTrue);

        ImGui::Separator();

        std::string q(state.spotlight_buf);
        std::transform(q.begin(), q.end(), q.begin(), ::tolower);

        const ParsedInstrument* first_match = nullptr;
        int shown = 0;

        for (const auto& p : state.parsed) {
            std::string name = display_name(p.key, state);
            if (!q.empty()) {
                std::string nl = name;
                std::transform(nl.begin(), nl.end(), nl.begin(), ::tolower);
                if (nl.find(q) == std::string::npos) continue;
            }
            if (!first_match) first_match = &p;

            bool sel = (p.key == state.selected_instrument);
            // Highlight first match
            if (first_match == &p)
                ImGui::PushStyleColor(ImGuiCol_Header,
                    ImGui::GetStyleColorVec4(ImGuiCol_HeaderHovered));
            if (ImGui::Selectable((name + "##sp" + p.key).c_str(), sel || first_match == &p)) {
                state.select_instrument(p.key);
                state.spotlight_open = false;
            }
            if (first_match == &p) ImGui::PopStyleColor();

            if (++shown >= 20) break;
        }

        if (entered && first_match) {
            state.select_instrument(first_match->key);
            state.spotlight_open = false;
        }
        if (ImGui::IsKeyPressed(ImGuiKey_Escape))
            state.spotlight_open = false;
    }
    ImGui::End();
    ImGui::PopStyleVar(2);
}

// ─── Entry point ────────────────────────────────────────────────────────────

void render_ui(AppState& state) {
    // ── Global shortcuts (fire anywhere, not inside text inputs) ─────────
    if (!ImGui::GetIO().WantTextInput) {
        if (ImGui::IsKeyPressed(ImGuiKey_Space, false))
            state.spotlight_open = !state.spotlight_open;

        if (ImGui::IsKeyDown(ImGuiKey_LeftCtrl) || ImGui::IsKeyDown(ImGuiKey_RightCtrl)) {
            if (ImGui::IsKeyPressed(ImGuiKey_L, false)) {
                state.live_mode  = !state.live_mode;
                if (state.live_mode) state.needs_load = true;
            }
        }

        ChartTools& t = state.chart_tools;

        // T: toggle trade draw mode
        if (ImGui::IsKeyPressed(ImGuiKey_T, false)) {
            if (t.mode == ChartTools::Mode::DrawTrade)
                t.mode = ChartTools::Mode::None;
            else {
                t.mode = ChartTools::Mode::DrawTrade;
            }
        }
        // W: flip buy/sell within trade mode
        if (ImGui::IsKeyPressed(ImGuiKey_W, false))
            t.trade_buy = !t.trade_buy;
        if (ImGui::IsKeyPressed(ImGuiKey_H, false))
            t.mode = (t.mode == ChartTools::Mode::DrawHLine)
                     ? ChartTools::Mode::None : ChartTools::Mode::DrawHLine;
        if (ImGui::IsKeyPressed(ImGuiKey_L, false))
            t.hlines.clear();
        if (ImGui::IsKeyPressed(ImGuiKey_B, false)) {
            t.rect_active    = t.rect_visible    = false;
            t.ob_rect_active = t.ob_rect_visible = false;
        }
        if (ImGui::IsKeyPressed(ImGuiKey_V, false))
            t.hover_details = !t.hover_details;
        if (ImGui::IsKeyPressed(ImGuiKey_Escape, false)) {
            t.mode           = ChartTools::Mode::None;
            t.rect_active    = t.rect_visible    = false;
            t.ob_rect_active = t.ob_rect_visible = false;
            state.trade.placed = false;
        }
    }

    render_dockspace(state);
    panel_instrument_selector(state);
    panel_ltp_chart(state);
    panel_stats(state);
    panel_depth(state);
    panel_ob_viz(state);
    panel_backtest(state);
    panel_trade_settings(state);
    panel_theme(state);
    panel_spotlight(state);
}
