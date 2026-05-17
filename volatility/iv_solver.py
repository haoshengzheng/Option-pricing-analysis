import numpy as np
from typing import Union, List
from core.time_utils import parse_dt, count_trading_seconds_precise, SECONDS_PER_FULL_TRADE_DAY, trading_days_per_year
from core.vanilla import VanillaBSM

'''
I implemented an implied volatility solver using Newton-Raphson with a bisection fallback for robustness.
I also enforce no-arbitrage bounds and ensure the solution is properly bracketed before applying root-finding methods.
'''

def implied_vol(price_mkt: float, S: float, K: float, start_dt: str, end_dt: str, r: float, b: float,
                option_type: str = 'call', max_iter: int = 100, epsilon = 1e-6, sigma_low = 1e-4, sigma_high = 10 ) -> float:

    start_dt = parse_dt(start_dt)
    end_dt = parse_dt(end_dt)
    T_cal = max(0.0, (end_dt - start_dt).total_seconds() / (365 * 86400))
    trade_sec = count_trading_seconds_precise(start_dt, end_dt)
    T_trade = max(0.0, trade_sec / (trading_days_per_year * SECONDS_PER_FULL_TRADE_DAY))
    phi= 1 if option_type.lower() == 'call' else -1

    low, high = sigma_low, sigma_high

    v_high = VanillaBSM(S, K, T_trade, T_cal, r, b, sigma=high)
    if price_mkt >= v_high.price(phi):
        return high

    v_low = VanillaBSM(S, K, T_trade, T_cal, r, b, sigma=low)
    if price_mkt <= v_low.price(phi):
        return low

    forward = S * np.exp((b - r) * T_cal)
    discount = np.exp(-r * T_cal)
    if option_type.lower() == 'call':
        intrinsic = max(0.0, forward - K * discount)
    else:
        intrinsic = max(0.0, K * discount - forward)
    if price_mkt < intrinsic - epsilon:
        return np.nan

    if T_trade <= 0:
        return np.nan

    if option_type.lower() == 'call':
        upper_bound = S * np.exp((b - r) * T_cal)
    else:
        upper_bound = K * np.exp(-r * T_cal)
    if price_mkt > upper_bound:
        return np.nan

    # Consider the initial seed of sigma (using Brenner and Subrahmanyam method which is effective at ATM)
    sigma = np.sqrt(2 * np.pi / T_trade) * (price_mkt / (S * np.exp((b - r) * T_trade)) )
    sigma = np.clip(sigma, sigma_low, sigma_high)


    for _ in range(max_iter):
        v = VanillaBSM(S, K, T_trade, T_cal, r, b, sigma)
        diff = v.price(phi) - price_mkt

        if abs(diff) < epsilon:
            return sigma

        vega = v.vega() * 100
        if abs(vega) > 1e-12:
            sigma_new = sigma - diff / vega
            sigma = np.clip(sigma_new, sigma_low, sigma_high)
        else:
            break   # Newton may fail for deep OTM options due to low Vega, so fall back to bisection.

    for _ in range(200):
        mid = 0.5 * (low + high)
        v_mid = VanillaBSM(S=S, K=K, T_trade=T_trade, T_cal=T_cal, r=r, b=b, sigma=mid)
        diff_mid = v_mid.price(phi) - price_mkt

        if abs(diff_mid) < epsilon:
            return mid

        if diff_mid < 0:
            low = mid
        else:
            high = mid

    return 0.5 * (low + high)


def implied_vol_vec(prices: np.ndarray, S: float, K_arr: np.ndarray, start_dt: str, end_dt_arr: Union[str, np.ndarray, List[str]],
                    r: float, b: float = 0.0, option_types: Union[str, list, np.ndarray] = None, **kwargs) -> np.ndarray:


    n = len(prices)
    K_arr = np.atleast_1d(K_arr)
    if len(K_arr) == 1 and n > 1:
        K_arr = np.repeat(K_arr, n)


    if isinstance(end_dt_arr, str):
        end_dts = [end_dt_arr] * n
    else:
        end_dts = list(end_dt_arr)
        if len(end_dts) == 1 and n > 1:
            end_dts = end_dts * n

    if option_types is None:
        opts = ['call'] * n
    elif isinstance(option_types, str):
        mapped_type = 'call' if option_types.lower() in ('call', 'c') else 'put'
        opts = [mapped_type] * n
    else:
        opts = [
            'call' if str(t).lower() in ('call', 'c') else 'put'
            for t in option_types
        ]

    iv_results = np.empty(n)

    for i in range(n):
        iv_results[i] = implied_vol(price_mkt=prices[i],S=S,K=K_arr[i],start_dt=start_dt,end_dt=end_dts[i],r=r,
                                    b=b, option_type=opts[i],**kwargs)

    return iv_results

