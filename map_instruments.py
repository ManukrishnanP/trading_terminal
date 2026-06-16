import json
import os
import sqlite3
import glob
import pandas as pd

COMPLETE_JSON   = 'complete.json'
NSE_MIS_JSON    = 'nse_mis_instruments.json'
DB_PATH         = 'market_data.db'

CREATE_NAMES_SQL = """
CREATE TABLE IF NOT EXISTS instrument_names (
    instrument_key TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL
);
"""


def load_instrument_map(json_path: str = COMPLETE_JSON) -> dict[str, str]:
    """Parse complete.json → {instrument_key: display_name}."""
    print(f"Loading instrument map from {json_path}...")
    with open(json_path, 'r') as f:
        data = json.load(f)

    mapping = {}
    for item in data:
        key = item.get('instrument_key')
        if not key:
            continue
        name   = item.get('name', '')
        symbol = item.get('trading_symbol', '')
        segment = item.get('segment', '')

        if segment in ('NSE_FO', 'BSE_FO'):
            # e.g. "SENSEX25JUN4600CE (SENSEX)"
            display = f"{symbol} ({name})" if name else symbol
        else:
            # e.g. "Nifty 50 [NIFTY]"
            display = f"{name} [{symbol}]" if symbol else name

        if display:
            mapping[key] = display

    print(f"  Loaded {len(mapping):,} instruments.")
    return mapping


def seed_db(db_path: str = DB_PATH,
            json_path: str = COMPLETE_JSON,
            overwrite: bool = False) -> int:
    """
    Seed instrument_names table from complete.json.

    overwrite=False  →  INSERT OR IGNORE  (keeps names set by the live ingestor)
    overwrite=True   →  INSERT OR REPLACE (force-update everything)

    Returns number of rows written.
    """
    if not os.path.exists(json_path):
        print(f"{json_path} not found — skipping seed.")
        return 0

    mapping = load_instrument_map(json_path)
    if not mapping:
        return 0

    mode = "OR REPLACE" if overwrite else "OR IGNORE"
    sql  = f"INSERT {mode} INTO instrument_names(instrument_key, display_name) VALUES (?,?)"

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(CREATE_NAMES_SQL)
    conn.executemany(sql, mapping.items())
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM instrument_names").fetchone()[0]
    conn.close()

    print(f"  instrument_names table now has {count:,} rows.")
    return len(mapping)


def seed_from_nse_mis(db_path: str = DB_PATH,
                      json_path: str = NSE_MIS_JSON,
                      overwrite: bool = False) -> int:
    """
    Seed instrument_names from the NSE MIS instruments JSON (stocks, ETFs, etc.).

    Uses trading_symbol as the display name (e.g. "RELIANCE", "TCS").
    INSERT OR IGNORE by default so complete.json options names are not overwritten.
    """
    if not os.path.exists(json_path):
        print(f"{json_path} not found — skipping NSE MIS seed.")
        return 0

    print(f"Loading {json_path}...")
    with open(json_path) as f:
        data = json.load(f)

    pairs = []
    for item in data:
        key = item.get('instrument_key', '')
        if not key:
            continue
        # trading_symbol is the market ticker (RELIANCE, TCS, …)
        name = (item.get('trading_symbol') or
                item.get('short_name') or
                item.get('name') or key)
        pairs.append((key, name))

    if not pairs:
        return 0

    print(f"  {len(pairs):,} instruments found.")
    mode = "OR REPLACE" if overwrite else "OR IGNORE"
    sql  = f"INSERT {mode} INTO instrument_names(instrument_key, display_name) VALUES (?,?)"

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(CREATE_NAMES_SQL)
    conn.executemany(sql, pairs)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM instrument_names").fetchone()[0]
    conn.close()

    print(f"  instrument_names table now has {count:,} rows.")
    return len(pairs)


def show_csv_instrument_names():
    """Print resolved names for all keys seen in market_data_csv/*.csv."""
    mapping = load_instrument_map()

    csv_files = glob.glob('market_data_csv/*.csv')
    if not csv_files:
        print("No CSV files found in market_data_csv/.")
        return

    all_keys: set[str] = set()
    for f in csv_files:
        df = pd.read_csv(f, usecols=['instrument_key'])
        all_keys.update(df['instrument_key'].unique())

    print("\n--- Instrument Mapping ---")
    for key in sorted(all_keys):
        print(f"{key} => {mapping.get(key, 'NOT FOUND')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Instrument name tools")
    parser.add_argument('--db',        default=DB_PATH,
                        help=f'Path to SQLite DB (default: {DB_PATH})')
    parser.add_argument('--seed',      action='store_true',
                        help='Seed from complete.json (options/futures master)')
    parser.add_argument('--nse-mis',   action='store_true',
                        help='Seed from nse_mis_instruments.json (stocks/ETFs)')
    parser.add_argument('--overwrite', action='store_true',
                        help='Replace existing names instead of skipping them')
    parser.add_argument('--show-csv',  action='store_true',
                        help='Print resolved names for CSV files (legacy mode)')
    args = parser.parse_args()

    # Default (no flags): seed from whichever master files exist
    run_all = not args.show_csv
    if run_all or args.seed:
        seed_db(db_path=args.db, overwrite=args.overwrite)
    if run_all or args.nse_mis:
        seed_from_nse_mis(db_path=args.db, overwrite=args.overwrite)
    if args.show_csv:
        show_csv_instrument_names()
