import math
import numpy as np
import scipy.stats as si

def bsm_call(S, K, T, r, sigma):
    if T <= 0:
        return max(S - K, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * si.norm.cdf(d1) - K * np.exp(-r * T) * si.norm.cdf(d2)

# Case 1: Deep ITM
S1, S2 = 23365, 23395 # 30 point move
K = 23200
T = 20 / (365 * 24 * 60) # 20 mins left
print("ITM Delta near expiry:")
print("P1:", bsm_call(S1, K, T, 0.07, 0.15))
print("P2:", bsm_call(S2, K, T, 0.07, 0.15))

# Case 2: ATM
S1, S2 = 23200, 23230
print("\nATM Delta near expiry:")
print("P1:", bsm_call(S1, K, T, 0.07, 0.15))
print("P2:", bsm_call(S2, K, T, 0.07, 0.15))

# Case 3: OTM
S1, S2 = 23100, 23130
print("\nOTM Delta near expiry:")
print("P1:", bsm_call(S1, K, T, 0.07, 0.15))
print("P2:", bsm_call(S2, K, T, 0.07, 0.15))
