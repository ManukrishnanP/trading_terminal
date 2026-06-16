import asyncio
import json
import ssl
import os
import datetime
import csv
import requests
import websockets
import urllib.parse
from google.protobuf.json_format import MessageToDict
import MarketDataFeedV3_pb2 as pb

# ================= CONFIGURATION =================

# 1. Instruments to track
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

# 2. Settings
STRIKE_WINDOW = 5  # Tracks ATM + 5 OTM + 5 ITM (11 strikes total per index)
MODE = "full"      # "full" mode for complete market depth and details

# 3. CSV Logging
CSV_FOLDER = "market_data_csv"
os.makedirs(CSV_FOLDER, exist_ok=True)
csv_filename = os.path.join(CSV_FOLDER, f"market_full_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv")

# CSV Headers (Expanded for 5-level Market Depth)
CSV_HEADERS = [
    "timestamp", "instrument_key", "type",
    "ltp", "ltt", "ltq", "cp", 
    "atp", "vtt", "oi", "iv", "tbq", "tsq",
    "open", "high", "low", "close",
    "bid1_p", "bid1_q", "ask1_p", "ask1_q",
    "bid2_p", "bid2_q", "ask2_p", "ask2_q",
    "bid3_p", "bid3_q", "ask3_p", "ask3_q",
    "bid4_p", "bid4_q", "ask4_p", "ask4_q",
    "bid5_p", "bid5_q", "ask5_p", "ask5_q"
]

# 4. Load Token
try:
    with open('accesstoken.json', 'r') as at:
        ACCESS_TOKEN = json.load(at)['access_token']
except FileNotFoundError:
    print("Error: 'accesstoken.json' not found.")
    exit()

# ================= HELPER FUNCTIONS =================

def get_headers():
    return {
        'Accept': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

def get_spot_price(instrument_key):
    encoded_key = urllib.parse.quote(instrument_key)
    url = f"https://api.upstox.com/v3/market-quote/ltp?instrument_key={encoded_key}"
    try:
        resp = requests.get(url, headers=get_headers())
        data = resp.json()
        if "data" in data and data["data"]:
            first_key = list(data["data"].keys())[0]
            return data["data"][first_key]["last_price"]
    except Exception as e:
        print(f"Spot price check failed: {e}")
    return None

def get_next_expiry_date(target_weekday):
    today = datetime.date.today()
    days_ahead = target_weekday - today.weekday()
    if days_ahead <= 0: days_ahead += 7
    return (today + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def get_filtered_keys():
    final_keys = []
    for config in INDICES_CONFIG:
        idx_key = config['instrument_key']
        final_keys.append(idx_key)
        print(f"Searching for options for {config['name']}...")
        
        # We search for CE and PE separately using atm_offset
        # We'll search for offsets from -STRIKE_WINDOW to +STRIKE_WINDOW
        offsets = list(range(-STRIKE_WINDOW, STRIKE_WINDOW + 1))
        
        search_url = "https://api.upstox.com/v2/instruments/search"
        
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
                    resp_json = resp.json()
                    data = resp_json.get('data', [])
                    if data:
                        key = data[0]['instrument_key']
                        final_keys.append(key)
                except Exception as e:
                    print(f"  Error searching {config['name']} {option_type} offset {offset}: {e}")
        
        print(f"  Total keys after {config['name']}: {len(final_keys)}")

    return list(set(final_keys))

def get_auth_url():
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    resp = requests.get(url, headers=get_headers())
    return resp.json()["data"]["authorized_redirect_uri"]

def decode_protobuf(buffer):
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response

def extract_row(instrument_key, feed_item):
    """Extracts a flattened row for CSV from the feed item, handling full and partial updates."""
    # We only want to save if there's actually some data
    has_data = False
    row = {k: "" for k in CSV_HEADERS}
    row["timestamp"] = datetime.datetime.now().isoformat()
    row["instrument_key"] = instrument_key
    
    # Priority 1: Full Feed ("ff")
    if "ff" in feed_item:
        has_data = True
        ff = feed_item["ff"]
        inner = ff.get("marketFF") or ff.get("indexFF")
        if inner:
            row["type"] = "market" if "marketFF" in ff else "index"
            
            # LTPC
            ltpc = inner.get("ltpc", {})
            row["ltp"] = ltpc.get("ltp", "")
            row["ltt"] = ltpc.get("ltt", "")
            row["ltq"] = ltpc.get("ltq", "")
            row["cp"] = ltpc.get("cp", "")
            
            # Market Specific
            row["atp"] = inner.get("atp", "")
            row["vtt"] = inner.get("vtt", "")
            row["oi"] = inner.get("oi", "")
            row["iv"] = inner.get("iv", "")
            row["tbq"] = inner.get("tbq", "")
            row["tsq"] = inner.get("tsq", "")
            
            # OHLC
            ohlc_list = inner.get("marketOHLC", {}).get("ohlc", [])
            if ohlc_list:
                d = ohlc_list[0]
                row["open"] = d.get("open", "")
                row["high"] = d.get("high", "")
                row["low"] = d.get("low", "")
                row["close"] = d.get("close", "")
                
            # Depth (Up to 5 levels)
            depth = inner.get("marketLevel", {}).get("bidAskQuote", [])
            for i, quote in enumerate(depth):
                if i >= 5: break  # Limit to 5 levels as per headers
                idx = i + 1
                row[f"bid{idx}_p"] = quote.get("bidP", "")
                row[f"bid{idx}_q"] = quote.get("bidQ", "")
                row[f"ask{idx}_p"] = quote.get("askP", "")
                row[f"ask{idx}_q"] = quote.get("askQ", "")
    
    # Priority 2: LTPC (often sent as partial updates)
    elif "ltpc" in feed_item:
        has_data = True
        row["type"] = "partial_ltpc"
        ltpc = feed_item["ltpc"]
        row["ltp"] = ltpc.get("ltp", "")
        row["ltt"] = ltpc.get("ltt", "")
        row["ltq"] = ltpc.get("ltq", "")
        row["cp"] = ltpc.get("cp", "")
        
    return row if has_data else None

# ================= MAIN STREAM LOGIC =================

async def run_stream():
    keys = get_filtered_keys()
    if not keys: 
        print("No keys to subscribe to.")
        return
    print(f"Subscribing to {len(keys)} keys in FULL mode.")

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        ws_url = get_auth_url()
    except Exception as e:
        print(f"Auth Failed: {e}")
        return

    total_rows_captured = 0
    msg_count = 0
    
    async with websockets.connect(ws_url, ssl=ssl_context) as websocket:
        print(f"WebSocket Connected. Writing to {csv_filename}")
        
        # Initialize CSV
        with open(csv_filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()

        # Subscribe
        payload = {
            "guid": "sub_full",
            "method": "sub",
            "data": {
                "mode": MODE,
                "instrumentKeys": keys
            }
        }
        await websocket.send(json.dumps(payload).encode('utf-8'))

        while True:
            try:
                msg = await websocket.recv()
                msg_count += 1
                
                decoded = decode_protobuf(msg)
                data_dict = MessageToDict(decoded)
                
                rows_in_this_msg = 0
                if "feeds" in data_dict:
                    feeds = data_dict["feeds"]
                    rows_to_write = []
                    
                    for key, feed_item in feeds.items():
                        row = extract_row(key, feed_item)
                        if row:
                            rows_to_write.append(row)
                    
                    if rows_to_write:
                        rows_in_this_msg = len(rows_to_write)
                        total_rows_captured += rows_in_this_msg
                        with open(csv_filename, 'a', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                            writer.writerows(rows_to_write)
                
                # Update status for every message to show "aliveness"
                timestamp = datetime.datetime.now().strftime('%H:%M:%S')
                print(f"\r[{timestamp}] Msg #{msg_count} | New Rows: {rows_in_this_msg} | Total: {total_rows_captured} ", end="", flush=True)

            except Exception as e:
                print(f"\nStream Error: {e}")
                break

if __name__ == "__main__":
    try:
        asyncio.run(run_stream())
    except KeyboardInterrupt:
        print("\nStopped.")
