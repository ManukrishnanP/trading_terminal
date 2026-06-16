import pandas as pd
import numpy as np
import math

df = pd.read_csv('market_data_csv/market_full_20260512_1505.csv')
df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None).values.astype('datetime64[ns]')

opt_df = df[df['instrument_key'].str.contains('23200 CE', na=False)].sort_values('timestamp')
idx_df = df[df['instrument_key'] == 'NSE_INDEX|Nifty 50'].sort_values('timestamp')

opt_df = opt_df.dropna(subset=['ltp'])
idx_df = idx_df.dropna(subset=['ltp'])

print("Option LTP min:", opt_df['ltp'].min(), "max:", opt_df['ltp'].max())
print("Index LTP min:", idx_df['ltp'].min(), "max:", idx_df['ltp'].max())

