import pandas as pd
df = pd.read_csv('market_data_csv/market_full_20260512_1505.csv')
fut_df = df[df['instrument_key'].str.contains('FUT', na=False) & df['instrument_key'].str.contains('NIFTY', na=False)]
fut_df = fut_df.dropna(subset=['ltp'])
print("Futures unique keys:", fut_df['instrument_key'].unique())
if not fut_df.empty:
    print("Futures min:", fut_df['ltp'].min(), "max:", fut_df['ltp'].max())
