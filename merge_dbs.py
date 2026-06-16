"""
Merges stock_data_old.db (old schema) and stock_data.db (new schema)
into merged.db using the old schema.

Old schema: timestamp NOT NULL, instrument_key, type, ltp, ltt, ltq, cp,
            atp, vtt, oi, iv, tbq, tsq, open, high, low, close, bid/ask x5
New schema: instrument_key, ltt NOT NULL, type, ltp, ltq, cp, atp, vtt,
            tbq, tsq, open, high, low, close, bid/ask x5  (no timestamp/oi/iv)

Strategy for new schema rows: use ltt as timestamp, oi/iv = NULL.
"""

import sqlite3

OLD_DB   = "M:/trading/stock_data_old.db"
NEW_DB   = "M:/trading/stock_data.db"
MERGED   = "M:/trading/merged.db"

CREATE_NAMES_SQL = """
CREATE TABLE IF NOT EXISTS instrument_names (
    instrument_key TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL
);
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    instrument_key TEXT NOT NULL,
    type        TEXT,
    ltp         REAL,
    ltt         TEXT,
    ltq         REAL,
    cp          REAL,
    atp         REAL,
    vtt         REAL,
    oi          REAL,
    iv          REAL,
    tbq         REAL,
    tsq         REAL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    bid1_p REAL, bid1_q REAL, ask1_p REAL, ask1_q REAL,
    bid2_p REAL, bid2_q REAL, ask2_p REAL, ask2_q REAL,
    bid3_p REAL, bid3_q REAL, ask3_p REAL, ask3_q REAL,
    bid4_p REAL, bid4_q REAL, ask4_p REAL, ask4_q REAL,
    bid5_p REAL, bid5_q REAL, ask5_p REAL, ask5_q REAL
);
"""

# ── setup merged db ──────────────────────────────────────────────────────────
dst = sqlite3.connect(MERGED)
dst.execute("PRAGMA journal_mode=WAL")
dst.execute("PRAGMA synchronous=NORMAL")
dst.execute(CREATE_NAMES_SQL)
dst.execute(CREATE_TABLE_SQL)
dst.execute("CREATE INDEX IF NOT EXISTS idx_instrument_ts ON market_data (instrument_key, timestamp DESC)")
dst.commit()

# ── copy instrument_names from both ─────────────────────────────────────────
for path in (OLD_DB, NEW_DB):
    src = sqlite3.connect(path)
    rows = src.execute("SELECT instrument_key, display_name FROM instrument_names").fetchall()
    dst.executemany("INSERT OR REPLACE INTO instrument_names VALUES (?,?)", rows)
    src.close()
dst.commit()
print("instrument_names merged.")

# ── copy old db (schema already matches) ────────────────────────────────────
src = sqlite3.connect(OLD_DB)
rows = src.execute("""
    SELECT timestamp, instrument_key, type, ltp, ltt, ltq, cp, atp, vtt,
           oi, iv, tbq, tsq, open, high, low, close,
           bid1_p, bid1_q, ask1_p, ask1_q,
           bid2_p, bid2_q, ask2_p, ask2_q,
           bid3_p, bid3_q, ask3_p, ask3_q,
           bid4_p, bid4_q, ask4_p, ask4_q,
           bid5_p, bid5_q, ask5_p, ask5_q
    FROM market_data
    -- skip the autoincrement id; SELECT gives 36 data cols matching 36 INSERT cols
""").fetchall()
dst.executemany("""
    INSERT INTO market_data (
        timestamp, instrument_key, type, ltp, ltt, ltq, cp, atp, vtt,
        oi, iv, tbq, tsq, open, high, low, close,
        bid1_p, bid1_q, ask1_p, ask1_q,
        bid2_p, bid2_q, ask2_p, ask2_q,
        bid3_p, bid3_q, ask3_p, ask3_q,
        bid4_p, bid4_q, ask4_p, ask4_q,
        bid5_p, bid5_q, ask5_p, ask5_q
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", rows)
dst.commit()
print(f"old db: {len(rows)} rows copied.")
src.close()

# ── copy new db (ltt → timestamp, oi/iv = NULL) ──────────────────────────────
src = sqlite3.connect(NEW_DB)
rows = src.execute("""
    SELECT ltt, instrument_key, type, ltp, ltt, ltq, cp, atp, vtt,
           NULL, NULL, tbq, tsq, open, high, low, close,
           bid1_p, bid1_q, ask1_p, ask1_q,
           bid2_p, bid2_q, ask2_p, ask2_q,
           bid3_p, bid3_q, ask3_p, ask3_q,
           bid4_p, bid4_q, ask4_p, ask4_q,
           bid5_p, bid5_q, ask5_p, ask5_q
    FROM market_data
    WHERE ltt IS NOT NULL
    -- 37 cols: timestamp(=ltt), instrument_key, type, ltp, ltt, ltq, cp, atp, vtt, oi(NULL), iv(NULL), tbq, tsq, open, high, low, close, bid/ask x5
""").fetchall()
dst.executemany("""
    INSERT INTO market_data (
        timestamp, instrument_key, type, ltp, ltt, ltq, cp, atp, vtt,
        oi, iv, tbq, tsq, open, high, low, close,
        bid1_p, bid1_q, ask1_p, ask1_q,
        bid2_p, bid2_q, ask2_p, ask2_q,
        bid3_p, bid3_q, ask3_p, ask3_q,
        bid4_p, bid4_q, ask4_p, ask4_q,
        bid5_p, bid5_q, ask5_p, ask5_q
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", rows)
dst.commit()
print(f"new db: {len(rows)} rows copied.")
src.close()

total = dst.execute("SELECT COUNT(*) FROM market_data").fetchone()[0]
dst.close()
print(f"Done. merged.db → {total} total rows.")
