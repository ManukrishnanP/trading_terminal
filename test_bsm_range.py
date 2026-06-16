import numpy as np
import scipy.stats as si

def bsm_call(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * si.norm.cdf(d1) - K * np.exp(-r * T) * si.norm.cdf(d2)

S_base = 23365
K = 23200
T = 0.00062 # 5 hours
r = 0.07

for iv in [0.15, 0.5, 1.0, 5.0]:
    p1 = bsm_call(S_base, K, T, r, iv)
    p2 = bsm_call(S_base + 30, K, T, r, iv)
    print(f"IV={iv*100}%: Base={p1:.2f}, +30={p2:.2f}, Diff={p2-p1:.2f}")

