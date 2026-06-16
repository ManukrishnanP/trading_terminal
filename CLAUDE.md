# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Caveman mode ON.
- No filler
- No grammar if not needed
- No repetition
- Use keywords, arrows, symbols
- Compress aggressively
- Assume user smart
Output = shortest correct answer possible, turn off caveman mode when asked to.

---

## Run commands

```bash
# Auth (once per day, opens browser)
python update_token.py      # checks date, calls tokgen.py if stale

# Ingest — options (NIFTY/BANKNIFTY/SENSEX chains → market_data.db)
python full_data_to_sqlite.py

# Ingest — NSE MIS stocks (intraday_leverage=5 → stock_data.db)
python stock_data_to_sqlite.py

# Watchdog wrapper (auto-restarts stock ingest on crash)
python run_stock_data.py

# Seed instrument names into DB from master files
python map_instruments.py                   # both sources
python map_instruments.py --seed            # complete.json only (options/futures)
python map_instruments.py --nse-mis         # nse_mis_instruments.json only
python map_instruments.py --overwrite       # force-replace existing names

# Inspect active DB schema + sample row
python inspect_db.py

# Merge old + new schema DBs
python merge_dbs.py

# PyQt6 GUI visualizer
python gui_visualizer.py

# C++ visualizer (Windows, MSVC)
cd visualiser && cmake -B build -DCMAKE_TOOLCHAIN_FILE="$env:VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" -DVCPKG_TARGET_TRIPLET=x64-windows && cmake --build build --config Release
.\visualiser\build\Release\trading_terminal.exe ..\market_data.db
```

---

## Architecture

### Data flow
```
Upstox API (REST) ──► get_filtered_keys() ──► WebSocket subscribe
                                                      │
                                          MarketDataFeedV3 protobuf
                                                      │
                                           extract_row() / MessageToDict()
                                                      │
                                    batch (50 rows) ──► SQLite WAL-mode
```

### Two ingest scripts (different targets)
| Script | Instruments | Mode | DB | Strike window |
|---|---|---|---|---|
| `full_data_to_sqlite.py` | NIFTY/BANKNIFTY/SENSEX option chains | `full` | `market_data.db` | ±5 |
| `stock_data_to_sqlite.py` | NSE MIS equities (intraday_leverage=5) | `full` | `stock_data.db` | — |
| `livedata.py` | NIFTY/SENSEX chains | `ltpc` | JSONL log only | ±20 |

### SQLite schema (both DBs)
- `market_data` — tick rows: `timestamp, instrument_key, type, ltp, ltt, ltq, cp, atp, vtt, oi, iv, tbq, tsq, open, high, low, close, bid1–5_(p/q), ask1–5_(p/q)`
- `instrument_names` — `instrument_key → display_name` lookup
- WAL + `synchronous=NORMAL` + `cache_size=-32000` on every connection
- Index on `(instrument_key, timestamp DESC)`

### Key files
- `MarketDataFeedV3.proto` / `_pb2.py` — Upstox V3 feed protobuf (generated)
- `secrets.json` — `client-id`, `client-secret` (never commit)
- `accesstoken.json` — daily OAuth token `{date, access_token}`
- `complete.json` — full instrument master (options/futures, ~69MB)
- `nse_mis_instruments.json` — equity instrument cache (refreshed daily)
- `map_instruments.py` — seeds `instrument_names` table; `seed_db()` imported by `full_data_to_sqlite.py`

### Protobuf feed structure
```
FeedResponse.feeds[instrument_key]
  ├── ltpc: {ltp, ltt, ltq, cp}          ← ltpc mode
  └── ff
       ├── marketFF: {ltpc, atp, vtt, tbq, tsq, oi, iv, marketOHLC, marketLevel}
       └── indexFF:  same shape, no OI/IV
```
`marketLevel.bidAskQuote[]` → 5-level order book, mapped to `bid/ask N_p/q` columns.

### C++ visualiser (`visualiser/`)
Dear ImGui + ImPlot + GLFW + OpenGL3, reads `market_data.db` directly via SQLite. Layout: instrument list | LTP chart | stats (OI/IV/ATP) | 5-level order book. Deps via vcpkg (`glfw3`, `sqlite3`) + `third_party/` (imgui, implot cloned by `setup_deps.ps1`).

### Auth flow
`tokgen.py`: opens `https://api.upstox.com/v2/login/authorization/dialog` in browser → local HTTP server on `:2000` catches redirect → exchanges code for token → writes `accesstoken.json`. `update_token.py` only re-runs if `accesstoken.json` date ≠ today.
