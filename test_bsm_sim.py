import numpy as np
import scipy.stats as si

def bsm_call(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * si.norm.cdf(d1) - K * np.exp(-r * T) * si.norm.cdf(d2)

# Simulate 0DTE ITM
S_vals = np.linspace(23300, 23400, 100) # Range of 100 points
K = 23200
T = 0.00003 # ~15 mins
r = 0.07
sigma = 0.15

bsm_vals = [bsm_call(s, K, T, r, sigma) for s in S_vals]
print(f"ITM: S range={np.max(S_vals)-np.min(S_vals):.2f}, BSM range={np.max(bsm_vals)-np.min(bsm_vals):.2f}")

# Simulate 0DTE OTM
S_vals = np.linspace(23100, 23150, 100) # Range of 50 points
K = 23200
bsm_vals = [bsm_call(s, K, T, r, sigma) for s in S_vals]
print(f"OTM: S range={np.max(S_vals)-np.min(S_vals):.2f}, BSM range={np.max(bsm_vals)-np.min(bsm_vals):.2f}")

