import asyncio
import json
import ssl
import os
import gzip
import io
import sqlite3
import requests
import websockets
import datetime
from google.protobuf.json_format import MessageToDict
import MarketDataFeedV3_pb2 as pb

# ================= CONFIGURATION =================

NSE_MIS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE_MIS.json.gz"
INSTRUMENTS_CACHE_PATH = "nse_mis_instruments.json"

MODE = "full"
DB_PATH = "stock_data.db"
BATCH_SIZE = 50

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
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")
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


# ================= INSTRUMENTS FETCH =================

def _cache_is_fresh(path: str) -> bool:
    """Returns True if the cache file exists and was written today."""
    if not os.path.exists(path):
        return False
    mtime = datetime.date.fromtimestamp(os.path.getmtime(path))
    return mtime == datetime.date.today()


def load_nse_mis_instruments() -> list[dict]:
    """
    Downloads NSE_MIS instruments, filters to intraday_leverage == 5,
    caches the filtered list, and re-downloads only once per day.
    """
    if _cache_is_fresh(INSTRUMENTS_CACHE_PATH):
        print(f"Using cached instruments from {INSTRUMENTS_CACHE_PATH}")
        with open(INSTRUMENTS_CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    print(f"Downloading NSE MIS instruments from {NSE_MIS_URL} ...")
    resp = requests.get(NSE_MIS_URL, timeout=30)
    resp.raise_for_status()

    with gzip.open(io.BytesIO(resp.content)) as gz:
        all_instruments = json.load(gz)

    instruments = [i for i in all_instruments if i.get("intraday_leverage") == 5.0]

    with open(INSTRUMENTS_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(instruments, f)

    print(f"Fetched {len(all_instruments)} total, {len(instruments)} with leverage 5 cached to {INSTRUMENTS_CACHE_PATH}")
    return instruments


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


def _none(v):
    return None if v == "" else v


def extract_row(instrument_key: str, feed_item: dict) -> dict | None:
    row = {k: None for k in COLUMNS}
    row["instrument_key"] = instrument_key
    row["timestamp"] = datetime.datetime.now().isoformat(timespec="milliseconds")

    if "ff" in feed_item:
        ff = feed_item["ff"]
        inner = ff.get("marketFF") or ff.get("indexFF")
        if not inner:
            return None
        row["type"] = "market" if "marketFF" in ff else "index"

        ltpc = inner.get("ltpc", {})
        row["ltt"] = _none(ltpc.get("ltt", ""))
        row["ltp"] = _none(ltpc.get("ltp", ""))
        row["ltq"] = _none(ltpc.get("ltq", ""))
        row["cp"]  = _none(ltpc.get("cp",  ""))

        row["atp"] = _none(inner.get("atp", ""))
        row["vtt"] = _none(inner.get("vtt", ""))
        row["tbq"] = _none(inner.get("tbq", ""))
        row["tsq"] = _none(inner.get("tsq", ""))
        row["oi"]  = _none(inner.get("oi",  ""))
        row["iv"]  = _none(inner.get("iv",  ""))

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

    elif "ltpc" in feed_item:
        row["type"] = "partial_ltpc"
        ltpc = feed_item["ltpc"]
        row["ltt"] = _none(ltpc.get("ltt", ""))
        row["ltp"] = _none(ltpc.get("ltp", ""))
        row["ltq"] = _none(ltpc.get("ltq", ""))
        row["cp"]  = _none(ltpc.get("cp",  ""))

    else:
        return None

    return row


# ================= MAIN STREAM LOGIC =================

async def run_stream(instruments: list[dict]):
    # Build (instrument_key, display_name) pairs from the instruments list
    # Field names TBD — placeholders until you confirm the JSON schema
    key_pairs: list[tuple[str, str]] = [
        (inst["instrument_key"], inst["trading_symbol"])
        for inst in instruments
    ]

    keys = [k for k, _ in key_pairs]
    print(f"Subscribing to {len(keys)} NSE MIS instruments in {MODE} mode.")
    print(f"Writing to SQLite: {DB_PATH}")

    conn = open_db(DB_PATH)
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

    # Upstox WebSocket accepts max 100 keys per subscription message;
    # chunk if the list is larger.
    CHUNK_SIZE = 100

    async with websockets.connect(ws_url, ssl=ssl_context) as websocket:
        for chunk_start in range(0, len(keys), CHUNK_SIZE):
            chunk = keys[chunk_start:chunk_start + CHUNK_SIZE]
            payload = {
                "guid": f"sub_stock_{chunk_start}",
                "method": "sub",
                "data": {"mode": MODE, "instrumentKeys": chunk}
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

            except websockets.exceptions.ConnectionClosedError as e:
                if "no close frame" in str(e).lower():
                    print(f"\n[warn] no close frame, continuing...")
                    continue
                print(f"\nConnection closed: {e}")
                break
            except Exception as e:
                print(f"\nStream error: {e}")
                break

    flush_batch(conn, batch)
    conn.close()
    print(f"\nDone. {total_rows} rows written to {DB_PATH}")


if __name__ == "__main__":
    instruments = load_nse_mis_instruments()
    try:
        asyncio.run(run_stream(instruments))
    except KeyboardInterrupt:
        print("\nStopped.")
