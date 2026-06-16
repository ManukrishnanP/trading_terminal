import asyncio
import json
import ssl
import os
import datetime
import requests
import websockets
import urllib.parse
from google.protobuf.json_format import MessageToDict
import MarketDataFeedV3_pb2 as pb

# ================= CONFIGURATION =================

# 1. Hardcoded Keys (CORRECTED)
INDICES_CONFIG = [
    {
        "name": "NIFTY",
        "instrument_key": "NSE_INDEX|Nifty 50", 
        "expiry_weekday": 1  # Tuesday
    },
    {
        "name": "SENSEX",
        "instrument_key": "BSE_INDEX|SENSEX",  # Corrected from SENSEX50
        "expiry_weekday": 3  # Friday (Sensex expiry is typically Friday)
    }
]

# 2. Settings
STRIKE_WINDOW = 20
MODE = "ltpc"

# 3. Logging
LOG_FOLDER = "market_data_logs"
os.makedirs(LOG_FOLDER, exist_ok=True)
log_filename = os.path.join(LOG_FOLDER, f"market_stream_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.jsonl")

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
    """Fetches spot price via HTTP to calculate ATM strike."""
    encoded_key = urllib.parse.quote(instrument_key)
    url = f"https://api.upstox.com/v3/market-quote/ltp?instrument_key={encoded_key}"
    
    try:
        resp = requests.get(url, headers=get_headers())
        data = resp.json()
        
        if "data" in data and data["data"]:
            # Grab the first available key (handling | vs : mismatch)
            first_key = list(data["data"].keys())[0]
            price = data["data"][first_key]["last_price"]
            print(f"  > Spot Price ({first_key}): {price}")
            return price
    except Exception as e:
        print(f"  Spot price check failed: {e}")
    return None

def get_next_expiry_date(target_weekday):
    today = datetime.date.today()
    days_ahead = target_weekday - today.weekday()
    if days_ahead < 0: days_ahead += 7
    elif days_ahead == 0 and datetime.datetime.now().hour >= 16: days_ahead += 7
    return (today + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def get_filtered_keys():
    final_keys = []
    
    for config in INDICES_CONFIG:
        idx_key = config['instrument_key']
        print(f"\n--- Setup for {idx_key} ---")
        
        final_keys.append(idx_key)

        # 1. Get Spot
        spot_price = get_spot_price(idx_key)
        if not spot_price: continue

        # 2. Expiry
        expiry = get_next_expiry_date(config['expiry_weekday'])
        print(f"  Expiry Date: {expiry}")

        # 3. Option Chain
        encoded_key = urllib.parse.quote(idx_key)
        url = f"https://api.upstox.com/v2/option/chain?instrument_key={encoded_key}&expiry_date={expiry}"
        
        try:
            resp = requests.get(url, headers=get_headers())
            data = resp.json().get('data', [])
            if not data:
                print(f"  No chain data for {expiry}")
                continue

            # 4. Filter
            strikes_map = {}
            for entry in data:
                strike = float(entry['strike_price'])
                if strike not in strikes_map: strikes_map[strike] = {}
                if entry.get('call_options'): strikes_map[strike]['CE'] = entry['call_options']['instrument_key']
                if entry.get('put_options'): strikes_map[strike]['PE'] = entry['put_options']['instrument_key']

            sorted_strikes = sorted(strikes_map.keys())
            if not sorted_strikes: continue
            
            atm_strike = min(sorted_strikes, key=lambda x: abs(x - spot_price))
            atm_index = sorted_strikes.index(atm_strike)
            
            start = max(0, atm_index - STRIKE_WINDOW)
            end = min(len(sorted_strikes), atm_index + STRIKE_WINDOW + 1)
            selected = sorted_strikes[start:end]
            
            print(f"  Selected {len(selected)} strikes around {atm_strike}")
            
            for s in selected:
                if 'CE' in strikes_map[s]: final_keys.append(strikes_map[s]['CE'])
                if 'PE' in strikes_map[s]: final_keys.append(strikes_map[s]['PE'])

        except Exception as e:
            print(f"  Error: {e}")

    return list(set(final_keys))

def get_auth_url():
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    resp = requests.get(url, headers=get_headers())
    return resp.json()["data"]["authorized_redirect_uri"]

def decode_protobuf(buffer):
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response

# ================= MAIN STREAM LOGIC =================

async def run_stream():
    keys = get_filtered_keys()
    total_keys = len(keys)
    print(f"\nTotal Keys to Stream: {total_keys}")
    if not keys: return

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        ws_url = get_auth_url()
    except Exception as e:
        print(f"Auth Failed: {e}")
        return

    # Tracking for the Dual Ticker (Updated Key)
    latest_spot = {
        "NSE_INDEX|Nifty 50": 0.0,
        "BSE_INDEX|SENSEX": 0.0
    }

    async with websockets.connect(ws_url, ssl=ssl_context) as websocket:
        print("WebSocket Connected.")
        await asyncio.sleep(1)

        # 1. Single Subscription (No Chunking)
        payload = {
            "guid": "sub_request",
            "method": "sub",
            "data": {
                "mode": MODE,
                "instrumentKeys": keys
            }
        }
        await websocket.send(json.dumps(payload).encode('utf-8'))
        print(f"Sent subscription for {total_keys} keys.")
        print("-" * 65)

        with open(log_filename, "a") as f:
            while True:
                try:
                    msg = await websocket.recv()
                    decoded = decode_protobuf(msg)
                    data_dict = MessageToDict(decoded)
                    
                    if "feeds" in data_dict:
                        # Log to file
                        data_dict["_ts"] = datetime.datetime.now().isoformat()
                        f.write(json.dumps(data_dict) + "\n")
                        f.flush()
                        
                        # Update Ticker (Handle both : and | in keys)
                        raw_feeds = data_dict["feeds"]
                        updated = False
                        
                        for key in latest_spot.keys():
                            # Check for the key using both | and : format
                            alt_key = key.replace("|", ":")
                            feed_item = raw_feeds.get(key) or raw_feeds.get(alt_key)
                            
                            if feed_item:
                                price = 0.0
                                # Handle V3 structure variations
                                if "ltpc" in feed_item:
                                    price = feed_item["ltpc"].get("ltp", 0.0)
                                elif "ff" in feed_item:
                                    # Check both marketFF and indexFF in the modified proto
                                    ff_data = feed_item["ff"]
                                    # Note: After proto modification, fullFeed is now ff
                                    inner = ff_data.get("marketFF") or ff_data.get("indexFF")
                                    if inner:
                                        price = inner.get("ltpc", {}).get("ltp", 0.0)
                                
                                if price > 0:
                                    latest_spot[key] = price
                                    updated = True

                        # Print Dual Ticker Line
                        if updated:
                            nifty_price = latest_spot["NSE_INDEX|Nifty 50"]
                            sensex_price = latest_spot["BSE_INDEX|SENSEX"]
                            
                            # \r overwrites the current line
                            print(f"\r NIFTY: {nifty_price:,.2f}  |  SENSEX: {sensex_price:,.2f}  |  Feed Update Size: {len(raw_feeds)}    ", end="")

                except Exception as e:
                    print(f"\nStream Error: {e}")
                    break

if __name__ == "__main__":
    try:
        asyncio.run(run_stream())
    except KeyboardInterrupt:
        print("\nStopped.")