import pandas as pd
import numpy as np
from PIL import Image
import glob
import os
import json

def create_visualizer():
    output_dir = "orderbook_visuals_raw"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("Loading CSV data...")
    csv_files = glob.glob('market_data_csv/*.csv')
    if not csv_files:
        print("No CSV files found in market_data_csv/")
        return

    df_list = []
    for f in csv_files:
        try:
            df_list.append(pd.read_csv(f))
        except Exception as e:
            print(f"Error reading {f}: {e}")
    
    if not df_list:
        return
        
    df = pd.concat(df_list)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Load instrument names
    mapping = {}
    if os.path.exists('complete.json'):
        try:
            with open('complete.json', 'r') as f:
                inst_data = json.load(f)
                for item in inst_data:
                    key = item.get('instrument_key')
                    if key:
                        mapping[key] = item.get('trading_symbol', key)
        except Exception as e:
            print(f"Error loading mapping: {e}")

    instruments = df['instrument_key'].unique()
    
    # Scale: 10 pixels per second for high resolution
    PIXELS_PER_SEC = 10 

    for inst in instruments:
        inst_df = df[df['instrument_key'] == inst].sort_values('timestamp').copy()
        
        if 'bid1_p' not in inst_df.columns:
            continue
            
        price_cols = [f'bid{i}_p' for i in range(1, 6)] + [f'ask{i}_p' for i in range(1, 6)]
        vol_cols = [f'bid{i}_q' for i in range(1, 6)] + [f'ask{i}_q' for i in range(1, 6)]
        
        inst_df = inst_df.dropna(subset=price_cols, how='all')
        if inst_df.empty:
            continue

        print(f"Processing {inst} (raw time-linear)...")

        # Time range calculation
        t_start = inst_df['timestamp'].min()
        t_end = inst_df['timestamp'].max()
        total_seconds = (t_end - t_start).total_seconds()
        
        # Calculate Width
        width = int(total_seconds * PIXELS_PER_SEC) + 1
        if width <= 0: continue

        # Calculate Price Range
        all_prices = inst_df[price_cols].values.flatten()
        all_prices = all_prices[~np.isnan(all_prices)]
        if len(all_prices) == 0: continue
            
        p_min, p_max = np.min(all_prices), np.max(all_prices)
        price_range = p_max - p_min
        
        if price_range == 0:
            height = 500
        else:
            estimated_ticks = int(price_range / 0.05) + 1
            height = min(max(estimated_ticks, 500), 4000)

        # Image Data: White background
        img_data = np.full((height, width, 3), 255, dtype=np.uint8)

        # Vol normalization (log scale)
        all_vols = inst_df[vol_cols].values.flatten()
        all_vols = all_vols[~np.isnan(all_vols)]
        all_vols = all_vols[all_vols > 0]
        max_log_vol = np.log1p(np.max(all_vols)) if len(all_vols) > 0 else 1

        def get_intensity(vol):
            if pd.isna(vol) or vol <= 0: return 0
            return int((np.log1p(vol) / max_log_vol) * 255)

        # Fill image data
        rows = inst_df.to_dict('records')
        for i in range(len(rows)):
            row = rows[i]
            # Start and End X for this entry
            start_x = int((row['timestamp'] - t_start).total_seconds() * PIXELS_PER_SEC)
            if i < len(rows) - 1:
                end_x = int((rows[i+1]['timestamp'] - t_start).total_seconds() * PIXELS_PER_SEC)
            else:
                end_x = width
            
            # Clip end_x to width
            end_x = min(end_x, width)
            if end_x <= start_x:
                end_x = start_x + 1 # Ensure at least 1 pixel width
            
            # For each of the 5 levels
            for lvl in range(1, 6):
                # Bid
                bp, bq = row[f'bid{lvl}_p'], row[f'bid{lvl}_q']
                if not pd.isna(bp) and bq > 0:
                    y = int((bp - p_min) / (p_max - p_min) * (height - 1)) if p_max > p_min else height // 2
                    y = (height - 1) - max(0, min(height-1, y))
                    intensity = get_intensity(bq)
                    # Draw a horizontal line from start_x to end_x
                    # Green: R(255-i), G(255-i/2), B(255-i)
                    intensity_rgb = np.array([255 - intensity, 255 - intensity // 2, 255 - intensity], dtype=np.uint8)
                    img_data[y, start_x:end_x] = np.minimum(img_data[y, start_x:end_x], intensity_rgb)

                # Ask
                ap, aq = row[f'ask{lvl}_p'], row[f'ask{lvl}_q']
                if not pd.isna(ap) and aq > 0:
                    y = int((ap - p_min) / (p_max - p_min) * (height - 1)) if p_max > p_min else height // 2
                    y = (height - 1) - max(0, min(height-1, y))
                    intensity = get_intensity(aq)
                    # Red: R(255-i/2), G(255-i), B(255-i)
                    intensity_rgb = np.array([255 - intensity // 2, 255 - intensity, 255 - intensity], dtype=np.uint8)
                    img_data[y, start_x:end_x] = np.minimum(img_data[y, start_x:end_x], intensity_rgb)

        # Save Image
        img = Image.fromarray(img_data)
        base_name = mapping.get(inst, inst).replace("|", "_").replace(" ", "_")
        safe_name = "".join([c for c in base_name if c.isalnum() or c in ('_', '-')]).rstrip()
        img.save(f"{output_dir}/{safe_name}.png")
        print(f"Saved {output_dir}/{safe_name}.png ({width}x{height})")

if __name__ == "__main__":
    create_visualizer()
