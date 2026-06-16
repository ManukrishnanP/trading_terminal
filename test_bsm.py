import pandas as pd
import numpy as np
import math
from datetime import datetime

# Simulate variables
idx_vals = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
idx_times = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
win = 3
strike = 100
expiry_str = "25DEC25" # placeholder

t_start = datetime(2025, 12, 1)

# Original Code with fix
returns = np.log(idx_vals[1:] / idx_vals[:-1])
returns = np.insert(returns, 0, np.nan) # Fix for length
if len(returns) > win:
    rolling_std = pd.Series(returns).rolling(window=win).std().values
    dt_avg = np.mean(np.diff(idx_times)) if len(idx_times) > 1 else 1
    ann_vol = rolling_std * np.sqrt(31536000 / max(dt_avg, 0.1))
    
    # Mock T_all
    T_all = np.array([1.0, 0.9, 0.8, 0.7, 0.6, 0.5])
    
    r = 0.07; S = idx_vals; K = strike; sigma = ann_vol
    
    v_erf = np.vectorize(math.erf)
    def n_cdf(x): return 0.5 * (1.0 + v_erf(x / np.sqrt(2.0)))
    
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T_all) / (sigma*np.sqrt(T_all))
    d2 = d1 - sigma*np.sqrt(T_all)
    
    bsm_prices = S * n_cdf(d1) - K * np.exp(-r*T_all) * n_cdf(d2)
    
    mask = ~np.isnan(bsm_prices)
    print("Mask:", mask)
    print("BSM Prices:", bsm_prices[mask])
else:
    print("Not enough data")
