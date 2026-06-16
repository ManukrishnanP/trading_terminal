# Trading Terminal — C++ Visualiser

Dear ImGui + ImPlot + GLFW + OpenGL3 frontend that reads live market data from `market_data.db`.

## Prerequisites

| Tool | Notes |
|------|-------|
| Visual Studio 2022 (with C++ Desktop workload) | MSVC compiler |
| CMake ≥ 3.20 | `winget install Kitware.CMake` |
| vcpkg | [install guide](https://vcpkg.io/en/getting-started.html) |
| Git | for cloning ImGui / ImPlot |

## 1 — Clone ImGui & ImPlot

```powershell
cd M:\trading\visualiser
.\setup_deps.ps1
```

This clones `third_party/imgui` and `third_party/implot` at pinned tags.

## 2 — Install native packages via vcpkg

```powershell
vcpkg install glfw3:x64-windows sqlite3:x64-windows
```

## 3 — Configure & build

```powershell
cmake -B build `
  -DCMAKE_TOOLCHAIN_FILE="$env:VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" `
  -DVCPKG_TARGET_TRIPLET=x64-windows
cmake --build build --config Release
```

## 4 — Run

```powershell
# Start the Python ingestor first (writes market_data.db)
cd M:\trading
python full_data_to_sqlite.py

# Then launch the visualiser (in another terminal)
.\visualiser\build\Release\trading_terminal.exe ..\market_data.db
```

Pass a path to `market_data.db` as the first argument (defaults to `../market_data.db`).

## UI layout

```
┌──────────────┬──────────────────────────────────┐
│  Instruments │          LTP Chart                │
│  (list box)  │       (ImPlot line chart)         │
│              ├──────────────┬───────────────────┤
│              │    Stats     │   Order Book      │
│              │  OI/IV/ATP…  │  5-level DOM      │
└──────────────┴──────────────┴───────────────────┘
```

All panels are dockable — drag them wherever you like; ImGui saves the layout.

## Architecture

```
full_data_to_sqlite.py  →  market_data.db (WAL)  ←  trading_terminal.exe
   (Python / websocket)         (SQLite)               (C++ / ImGui)
```

The C++ side polls the DB every 500 ms (read-only, WAL allows concurrent readers).
