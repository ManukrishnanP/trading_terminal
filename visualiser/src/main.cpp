#include <cstdio>
#include <string>
#include <filesystem>

#include "GLFW/glfw3.h"
#include "imgui.h"
#include "imgui_impl_glfw.h"
#include "imgui_impl_opengl3.h"
#include "implot.h"

#include "db.h"
#include "ui.h"

namespace fs = std::filesystem;

static void glfw_error_cb(int err, const char* desc) {
    fprintf(stderr, "GLFW error %d: %s\n", err, desc);
}

// Probe common locations for market_data.db relative to CWD.
static std::string find_db(int argc, char** argv) {
    if (argc > 1) return argv[1];
    for (const char* c : {
        "market_data.db",
        "../market_data.db",
        "../../market_data.db",
        "../../../market_data.db"
    }) {
        std::error_code ec;
        if (fs::exists(c, ec)) return c;
    }
    return "market_data.db";  // fallback; DB::open will report the error
}

int main(int argc, char** argv) {
    std::string db_path = find_db(argc, argv);

    // ── GLFW ──────────────────────────────────────────────────────────────
    glfwSetErrorCallback(glfw_error_cb);
    if (!glfwInit()) return 1;

    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);

    GLFWwindow* window = glfwCreateWindow(1600, 900, "Trading Terminal", nullptr, nullptr);
    if (!window) { glfwTerminate(); return 1; }
    glfwMakeContextCurrent(window);
    glfwSwapInterval(1);

    // ── Dear ImGui ────────────────────────────────────────────────────────
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImPlot::CreateContext();
    ImPlot::GetStyle().UseLocalTime = false;   // timestamps stored as IST wall-clock, display as-is

    ImGuiIO& io = ImGui::GetIO();
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
    io.ConfigFlags |= ImGuiConfigFlags_DockingEnable;

    // ── Font setup ────────────────────────────────────────────────────────
    // Small, safe glyph range: Basic Latin + Latin-1 + en/em dash only.
    // Keeping it narrow avoids atlas-size issues.
    static const ImWchar k_ranges[] = {
        0x0020, 0x00FF,   // Basic Latin + Latin Supplement
        0x2013, 0x2014,   // en dash, em dash
        0,
    };

    // Try common monospace fonts in order; fall back to built-in if none found.
    static const char* k_candidates[] = {
        "C:/Windows/Fonts/consolas.ttf",
        "C:/Windows/Fonts/cour.ttf",       // Courier New
        "C:/Windows/Fonts/lucon.ttf",       // Lucida Console
        nullptr
    };
    ImFontConfig cfg;
    cfg.OversampleH = 2;
    cfg.OversampleV = 2;
    bool loaded = false;
    for (const char** p = k_candidates; *p && !loaded; ++p) {
        if (std::filesystem::exists(*p)) {
            io.Fonts->AddFontFromFileTTF(*p, 14.5f, &cfg, k_ranges);
            loaded = true;
        }
    }
    if (!loaded)
        io.Fonts->AddFontDefault();

    ImGui_ImplGlfw_InitForOpenGL(window, true);
    ImGui_ImplOpenGL3_Init("#version 330");

    // ── App state (theme applied inside init) ─────────────────────────────
    AppState state;
    state.init(db_path);

    // Try opening backtest_results.db alongside the main DB (silent if absent)
    {
        fs::path bk = fs::path(db_path).parent_path() / "backtest_results.db";
        state.bkdb_path = bk.string();
        state.bkdb.open(state.bkdb_path);
    }

    state.load_settings("app.cfg");   // restore panels, trade, mode from last session

    if (state.instruments.empty())
        fprintf(stderr, "Warning: no instruments found in %s\n", db_path.c_str());

    // ── Render loop ───────────────────────────────────────────────────────
    while (!glfwWindowShouldClose(window)) {
        glfwPollEvents();

        double now = glfwGetTime();
        state.poll(now);

        // Apply deferred layout load before NewFrame so ImGui sees it immediately
        if (!state.layouts.pending_load.empty()) {
            ImGui::LoadIniSettingsFromDisk(state.layouts.pending_load.c_str());
            state.layouts.pending_load.clear();
        }

        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplGlfw_NewFrame();
        ImGui::NewFrame();

        render_ui(state);

        ImGui::Render();

        int w, h;
        glfwGetFramebufferSize(window, &w, &h);
        glViewport(0, 0, w, h);
        glClearColor(0.06f, 0.06f, 0.08f, 1.f);
        glClear(GL_COLOR_BUFFER_BIT);

        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
        glfwSwapBuffers(window);
    }

    // ── Cleanup ───────────────────────────────────────────────────────────
    state.save_settings("app.cfg");    // persist panels, trade, mode for next session
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplGlfw_Shutdown();
    ImPlot::DestroyContext();
    ImGui::DestroyContext();
    state.db.close();
    state.bkdb.close();
    glfwDestroyWindow(window);
    glfwTerminate();
    return 0;
}
