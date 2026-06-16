import asyncio
import json
import ssl
import os
import datetime
import sqlite3
import requests
import websockets
import urllib.parse
from google.protobuf.json_format import MessageToDict
import MarketDataFeedV3_pb2 as pb
from map_instruments import seed_db

# ================= CONFIGURATION =================

INDICES_CONFIG = [
    {
        "name": "NIFTY",
        "instrument_key": "NSE_INDEX|Nifty 50",
        "expiry_weekday": 3  # Thursday
    },
    {
        "name": "BANKNIFTY",
        "instrument_key": "NSE_INDEX|Nifty Bank",
        "expiry_weekday": 2  # Wednesday
    },
    {
        "name": "SENSEX",
        "instrument_key": "BSE_INDEX|SENSEX",
        "expiry_weekday": 4  # Friday
    }
]

STRIKE_WINDOW = 5
MODE = "full"

DB_PATH = "market_data.db"
BATCH_SIZE = 50  # rows buffered before a single INSERT

# Load Token
try:
    with open('accesstoken.json', 'r') as at:
        ACCESS_TOKEN = json.load(at)['access_token']
except FileNotFoundError:
    print("Error: 'accesstoken.json' not found.")
    exit()

# ================= DATABASE SETUP =================

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

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_instrument_ts
    ON market_data (instrument_key, timestamp DESC);
"""

INSERT_SQL = """
INSERT INTO market_data (
    timestamp, instrument_key, type,
    ltp, ltt, ltq, cp, atp, vtt, oi, iv, tbq, tsq,
    open, high, low, close,
    bid1_p, bid1_q, ask1_p, ask1_q,
    bid2_p, bid2_q, ask2_p, ask2_q,
    bid3_p, bid3_q, ask3_p, ask3_q,
    bid4_p, bid4_q, ask4_p, ask4_q,
    bid5_p, bid5_q, ask5_p, ask5_q
) VALUES (
    :timestamp, :instrument_key, :type,
    :ltp, :ltt, :ltq, :cp, :atp, :vtt, :oi, :iv, :tbq, :tsq,
    :open, :high, :low, :close,
    :bid1_p, :bid1_q, :ask1_p, :ask1_q,
    :bid2_p, :bid2_q, :ask2_p, :ask2_q,
    :bid3_p, :bid3_q, :ask3_p, :ask3_q,
    :bid4_p, :bid4_q, :ask4_p, :ask4_q,
    :bid5_p, :bid5_q, :ask5_p, :ask5_q
);
"""

COLUMNS = [
    "timestamp", "instrument_key", "type",
    "ltp", "ltt", "ltq", "cp", "atp", "vtt", "oi", "iv", "tbq", "tsq",
    "open", "high", "low", "close",
    "bid1_p", "bid1_q", "ask1_p", "ask1_q",
    "bid2_p", "bid2_q", "ask2_p", "ask2_q",
    "bid3_p", "bid3_q", "ask3_p", "ask3_q",
    "bid4_p", "bid4_q", "ask4_p", "ask4_q",
    "bid5_p", "bid5_q", "ask5_p", "ask5_q",
]


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")  # WAL + NORMAL is safe & fast
    conn.execute("PRAGMA cache_size=-32000")   # 32 MB page cache
    conn.execute(CREATE_NAMES_SQL)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_INDEX_SQL)
    conn.commit()
    return conn


def flush_batch(conn: sqlite3.Connection, batch: list[dict]) -> None:
    if not batch:
        return
    conn.executemany(INSERT_SQL, batch)
    conn.commit()
    batch.clear()


# ================= HELPER FUNCTIONS =================

def get_headers():
    return {
        'Accept': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }


def get_auth_url():
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    resp = requests.get(url, headers=get_headers())
    return resp.json()["data"]["authorized_redirect_uri"]


def decode_protobuf(buffer):
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response


def get_filtered_keys() -> list[tuple[str, str]]:
    """Returns deduplicated list of (instrument_key, display_name) pairs."""
    seen: dict[str, str] = {}

    search_url = "https://api.upstox.com/v2/instruments/search"

    for config in INDICES_CONFIG:
        idx_key = config['instrument_key']
        seen[idx_key] = config['name']
        print(f"Searching options for {config['name']}...")

        offsets = list(range(-STRIKE_WINDOW, STRIKE_WINDOW + 1))

        for option_type in ['CE', 'PE']:
            for offset in offsets:
                params = {
                    'query': config['name'],
                    'instrument_types': option_type,
                    'expiry': 'current_week',
                    'atm_offset': offset,
                    'records': 1
                }
                try:
                    resp = requests.get(search_url, headers=get_headers(), params=params)
                    data = resp.json().get('data', [])
                    if data:
                        key  = data[0]['instrument_key']
                        name = data[0].get('trading_symbol') or key
                        seen[key] = name
                except Exception as e:
                    print(f"  Search error {config['name']} {option_type} {offset}: {e}")

        print(f"  Keys so far: {len(seen)}")

    return list(seen.items())


def _none(v):
    """Convert empty string to None so SQLite stores NULL."""
    return None if v == "" else v


def extract_row(instrument_key: str, feed_item: dict) -> dict | None:
    row = {k: None for k in COLUMNS}
    row["timestamp"] = datetime.datetime.now().isoformat()
    row["instrument_key"] = instrument_key

    if "ff" in feed_item:
        ff = feed_item["ff"]
        inner = ff.get("marketFF") or ff.get("indexFF")
        if not inner:
            return None
        row["type"] = "market" if "marketFF" in ff else "index"

        ltpc = inner.get("ltpc", {})
        row["ltp"] = _none(ltpc.get("ltp", ""))
        row["ltt"] = _none(ltpc.get("ltt", ""))
        row["ltq"] = _none(ltpc.get("ltq", ""))
        row["cp"]  = _none(ltpc.get("cp",  ""))

        row["atp"] = _none(inner.get("atp", ""))
        row["vtt"] = _none(inner.get("vtt", ""))
        row["oi"]  = _none(inner.get("oi",  ""))
        row["iv"]  = _none(inner.get("iv",  ""))
        row["tbq"] = _none(inner.get("tbq", ""))
        row["tsq"] = _none(inner.get("tsq", ""))

        ohlc_list = inner.get("marketOHLC", {}).get("ohlc", [])
        if ohlc_list:
            d = ohlc_list[0]
            row["open"]  = _none(d.get("open",  ""))
            row["high"]  = _none(d.get("high",  ""))
            row["low"]   = _none(d.get("low",   ""))
            row["close"] = _none(d.get("close", ""))

        depth = inner.get("marketLevel", {}).get("bidAskQuote", [])
        for i, quote in enumerate(depth[:5]):
            n = i + 1
            row[f"bid{n}_p"] = _none(quote.get("bidP", ""))
            row[f"bid{n}_q"] = _none(quote.get("bidQ", ""))
            row[f"ask{n}_p"] = _none(quote.get("askP", ""))
            row[f"ask{n}_q"] = _none(quote.get("askQ", ""))

        return row

    elif "ltpc" in feed_item:
        row["type"] = "partial_ltpc"
        ltpc = feed_item["ltpc"]
        row["ltp"] = _none(ltpc.get("ltp", ""))
        row["ltt"] = _none(ltpc.get("ltt", ""))
        row["ltq"] = _none(ltpc.get("ltq", ""))
        row["cp"]  = _none(ltpc.get("cp",  ""))
        return row

    return None


# ================= MAIN STREAM LOGIC =================

async def run_stream():
    key_pairs = get_filtered_keys()
    if not key_pairs:
        print("No keys to subscribe to.")
        return
    keys = [k for k, _ in key_pairs]
    print(f"Subscribing to {len(keys)} keys in FULL mode.")
    print(f"Writing to SQLite: {DB_PATH}")

    conn = open_db(DB_PATH)
    # Seed from complete.json first (OR IGNORE so live names take priority)
    seed_db(db_path=DB_PATH, overwrite=False)
    # Persist human-readable names so the C++ visualiser can display them
    conn.executemany(
        "INSERT OR REPLACE INTO instrument_names(instrument_key, display_name) VALUES (?,?)",
        key_pairs
    )
    conn.commit()
    batch: list[dict] = []

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        ws_url = get_auth_url()
    except Exception as e:
        print(f"Auth Failed: {e}")
        return

    total_rows = 0
    msg_count = 0

    async with websockets.connect(ws_url, ssl=ssl_context) as websocket:
        payload = {
            "guid": "sub_full",
            "method": "sub",
            "data": {"mode": MODE, "instrumentKeys": keys}
        }
        await websocket.send(json.dumps(payload).encode('utf-8'))

        while True:
            try:
                msg = await websocket.recv()
                msg_count += 1
                decoded = decode_protobuf(msg)
                data_dict = MessageToDict(decoded)

                rows_this_msg = 0
                if "feeds" in data_dict:
                    for key, feed_item in data_dict["feeds"].items():
                        row = extract_row(key, feed_item)
                        if row:
                            batch.append(row)
                            rows_this_msg += 1

                    if len(batch) >= BATCH_SIZE:
                        flush_batch(conn, batch)

                total_rows += rows_this_msg
                ts = datetime.datetime.now().strftime('%H:%M:%S')
                print(
                    f"\r[{ts}] Msg #{msg_count} | +{rows_this_msg} rows | "
                    f"Total: {total_rows} | Pending: {len(batch)} ",
                    end="", flush=True
                )

            except Exception as e:
                print(f"\nStream error: {e}")
                break

    # Flush whatever remains on clean exit
    flush_batch(conn, batch)
    conn.close()
    print(f"\nDone. {total_rows} rows written to {DB_PATH}")


if __name__ == "__main__":
    try:
        asyncio.run(run_stream())
    except KeyboardInterrupt:
        print("\nStopped.")
