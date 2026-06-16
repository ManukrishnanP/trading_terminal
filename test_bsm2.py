import pandas as pd
import numpy as np
import math

idx_vals = np.array([100.0, 101.0, 102.0, 103.0])
idx_times = np.array([1.0, 2.0, 3.0, 4.0])
valid_idx = pd.DataFrame({'timestamp': pd.date_range('2025-01-01', periods=4, freq='1s')})
win = 3
strike = 100
expiry_str = "25DEC25"
t_start = pd.Timestamp('2025-01-01')

# BSM Formula
returns = np.log(idx_vals[1:] / idx_vals[:-1])
returns = np.insert(returns, 0, np.nan)
rolling_std = pd.Series(returns).rolling(window=win).std().values
dt_avg = np.mean(np.diff(idx_times)) if len(idx_times) > 1 else 1
ann_vol = rolling_std * np.sqrt(31536000 / max(dt_avg, 0.1))

exp_dt = pd.to_datetime(expiry_str + f" {t_start.year}", errors='ignore')
if exp_dt < t_start: exp_dt = exp_dt + pd.DateOffset(years=1)
T_all = (exp_dt - valid_idx['timestamp']).dt.total_seconds().values / 31536000.0
T_all = np.maximum(T_all, 1e-9)

r = 0.07; S = idx_vals; K = strike; sigma = ann_vol

v_erf = np.vectorize(math.erf)
def n_cdf(x): return 0.5 * (1.0 + v_erf(x / np.sqrt(2.0)))

sigma = np.maximum(sigma, 1e-9)
d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T_all) / (sigma*np.sqrt(T_all))
d2 = d1 - sigma*np.sqrt(T_all)

bsm_prices = S * n_cdf(d1) - K * np.exp(-r*T_all) * n_cdf(d2)

mask = ~np.isnan(bsm_prices)
print("done")
