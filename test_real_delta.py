import numpy as np
import scipy.stats as si

def bsm_delta(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return si.norm.cdf(d1)

S = 23350
K = 23200
r = 0.07
sigma = 0.15

print(f"Delta with 30 Days left: {bsm_delta(S, K, 30/365, r, sigma):.4f}")
print(f"Delta with 5 Days left: {bsm_delta(S, K, 5/365, r, sigma):.4f}")
print(f"Delta with 5 Hours left: {bsm_delta(S, K, 5/(24*365), r, sigma):.4f}")
print(f"Delta with 20 Mins left: {bsm_delta(S, K, 20/(60*24*365), r, sigma):.6f}")

