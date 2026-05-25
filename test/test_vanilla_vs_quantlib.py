"""
tests/test_vanilla_vs_quantlib.py

Cross-validate the from-scratch dual-time BSM against QuantLib's analytic
European engine. To make the comparison apples-to-apples, the dual-time pricer
is run with T_trade = T_cal = T (the degenerate case where trading time equals
calendar time), reducing it to standard BSM.
"""
import QuantLib as ql
from core.vanilla import VanillaBSM
from core.time_utils import trading_days_per_year

def quantlib_european_days(S, K, days, r, q, sigma, option_type='call'):
    """Price a European option and its Greeks with QuantLib's analytic engine.
    q is the dividend yield; cost-of-carry b = r - q, so to match a given b,
    pass q = r - b."""
    calc_date = ql.Date(25, 5, 2026)
    ql.Settings.instance().evaluationDate = calc_date
    dc = ql.Actual365Fixed()
    opt_type = ql.Option.Call if option_type == 'call' else ql.Option.Put
    exercise = ql.EuropeanExercise(calc_date + ql.Period(days, ql.Days))
    option = ql.VanillaOption(ql.PlainVanillaPayoff(opt_type, K), exercise)
    spot = ql.QuoteHandle(ql.SimpleQuote(S))
    rate_ts = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, r, dc))
    div_ts  = ql.YieldTermStructureHandle(ql.FlatForward(calc_date, q, dc))
    vol_ts  = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(calc_date, ql.NullCalendar(), sigma, dc))
    process = ql.BlackScholesMertonProcess(spot, div_ts, rate_ts, vol_ts)
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    return {'price': option.NPV(), 'delta': option.delta(),
            'gamma': option.gamma(), 'vega': option.vega() / 100, 'theta': option.theta()/365 }


def test_compare():
    S, r, b = 100.0, 0.03, 0.01
    q = r - b

    cases_days = [
        (100.0, 365,  0.20, 'call'),
        (90.0,  182,  0.25, 'call'),
        (110.0, 730,  0.15, 'put'),
        (100.0, 91,   0.40, 'put'),
        (120.0, 365,  0.30, 'call'),
    ]
    phi_map = {'call': 1, 'put': -1}
    max_price_err = 0.0

    print(f"{'K':>6}{'days':>6}{'sigma':>6}{'type':>6}"
          f"{'mine':>12}{'QL':>10}{'diff_price':>12}{'diff_delta':>12}"
          f"{'diff_gamma':>13}{'diff_vega':>12}{'diff_theta':>13}")

    for K, days, sigma, typ in cases_days:
        T = days / 365.0
        mine = VanillaBSM(S, K, T_trade=T, T_cal=T, r=r, b=b, sigma=sigma)
        phi = phi_map[typ]
        my_price = mine.price(phi)
        my_delta = mine.delta(phi)
        my_gamma = mine.gamma()
        my_vega = mine.vega()
        my_theta = mine.theta(phi) * trading_days_per_year / 365.0

        ql_res = quantlib_european_days(S, K, days, r, q, sigma, typ)

        dprice = abs(my_price - ql_res['price'])
        ddelta = abs(my_delta - ql_res['delta'])
        dgamma = abs(my_gamma - ql_res['gamma'])
        dvega = abs(my_vega - ql_res['vega'])
        dtheta = abs(my_theta - ql_res['theta'])

        max_price_err = max(max_price_err, dprice)
        print(f"{K:>6.0f}{days:>6d}{sigma:>6.2f}{typ:>6}"
              f"{my_price:>12.6f}{ql_res['price']:>12.6f}"
              f"{dprice:>12.2e}{ddelta:>10.2e}"
              f"{dgamma:>12.2e}{dvega:>10.2e}"
              f"{dtheta:>12.2e}"
              )

    print(f"\nMax price error: {max_price_err:.2e}")
    assert max_price_err < 1e-6


if __name__ == '__main__':
    test_compare()