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
