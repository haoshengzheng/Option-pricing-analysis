"""
Comparison and risk-diagnostics for normal vs knock-out accumulators.

Three analyses, each highlighting a different facet of how the knock-out
feature changes the risk profile relative to a plain accumulator:

1. Zero-cost strike trade-off (plot_zero_cost_strike)
   For a structurer, The basic question: given the barrier and current price,
   what zero-cost strike can the client get? And how much better is that strike
   if the client accepts knock-out risk? The plots show the tradeoff between strike and rebate.

2. Pin risk near the barrier (plot_pin_risk)
   The figures show the changes in Delta and Gamma for the two structures near the barrier level.
   Highlights the BGK "gray zone" between the real barrier B and the model-adjusted barrier B_adj,
   where the contract has knocked out but the model is still alive.

3. Trade sensitivity (plot_sensitivity)
   Set both products to zero-cost by solving for strike and rebate. Then sweep spot
   and volatility to show the change of value and Greeks, comparing delta, gamma and vega stability
   when volatility changes.
"""
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import brentq
from core.time_utils import trading_days_per_year
from models.normal_accumulator import AccumulatorReplication
from models.ko_accumulator import KnockOutAccumulatorPricer


def _build(option_type: str, params: dict):
    """Construct a normal or knock-out accumulator pricer from a params dict."""
    p   = params
    if option_type == 'normal':
        return AccumulatorReplication(
            S=p['S'], K=p['K'], B=p['B'],
            r=p['r'], b=p['b'], sigma=p['sigma'],
            L=p['L'], PR=p['PR'],
            strike_shift=p['strike_shift'],
            option_type=p['option_type'],
            start_dt=p['start_dt'], end_dt=p['end_dt'],
        )
    elif option_type == 'knockout':
        return KnockOutAccumulatorPricer(
            S=p['S'], K=p['K'], B=p['B'],
            r=p['r'], b=p['b'], sigma=p['sigma'],
            PR=p['PR'], L=p['L'],
            rebate=p.get('rebate', 0.0),
            option_type=p['option_type'],
            start_dt=p['start_dt'], end_dt=p['end_dt'],
        )
    else:
        raise ValueError(f"Unknown option_type: {option_type!r}")


def _price(option_type, params, **ov):
    return _build(option_type, {**params, **ov}).price()

def _greeks(option_type, params, **ov):
    return _build(option_type, {**params, **ov}).greeks()

def _bgk_adj(params, beta=0.5826):
    """Compute the BGK-adjusted barrier B_adj = B * exp(beta * sigma * sqrt(dt))."""
    ann = trading_days_per_year
    dt  = 1.0 / ann
    return params['B'] * np.exp(beta * params['sigma'] * np.sqrt(dt))


def print_summary(params: dict) -> None:
    w     = 65
    normal_price  = _price('normal',  params)
    knockout_price  = _price('knockout', params)
    normal_greek  = _greeks('normal',  params)
    knockout_greek  = _greeks('knockout', params)
    B_adj = _bgk_adj(params)

    print(f"  Normal vs KO Accumulator — Summary")
    print(f"  S={params['S']}  K={params['K']}  B={params['B']}  sigma={params['sigma']:.0%}")
    print(f"  PR={params['PR']}  L={params['L']}  rebate(KO)={params.get('rebate',0)}")
    print(f"  B_adj = {B_adj:.4f}  (BGK gray zone = {B_adj - params['B']:.4f} pts)")
    print(f"{'─'*w}")
    print(f"  {'':16} {'Normal':>12} {'KO':>12} {'Delta(KO-N)':>12}")
    print(f"{'─'*w}")
    for lbl, nv, kv in [
        ('Price',   normal_price, knockout_price),
        ('Delta',   normal_greek['delta'], knockout_greek['delta']),
        ('Gamma',   normal_greek['gamma'], knockout_greek['gamma']),
        ('Vega',    normal_greek['vega'],  knockout_greek['vega']),
        ('Theta',   normal_greek['theta'], knockout_greek['theta']),
    ]:
        diff = kv - nv
        pct  = diff / abs(nv) * 100 if abs(nv) > 1e-10 else float('nan')
        print(f"  {lbl:16} {nv:>12.5f} {kv:>12.5f} "
              f"{diff:>+12.5f}  ({pct:+.1f}%)")
    print(f"{'='*w}\n")



def _find_zero_cost_k(option_type: str, params: dict,
                      K_low=0.70, K_high=1.3) -> float:
    """Solve for the strike K that makes the contract zero-cost (price = 0), via Brent's method"""
    B  = params['B']
    low = B * K_low
    high = B * K_high

    def obj(k):
        try:
            return _price(option_type, params, K=k)
        except Exception:
            return float('nan')

    price_low, price_high = obj(low), obj(high)
    if (price_low != price_low) or (price_high != price_high):
        return float('nan')
    if price_low * price_high > 0:
        return float('nan')
    try:
        res =  brentq(obj, low, high, xtol=1e-3, maxiter=120)
        strike_k = res[0] if isinstance(res, (tuple, list)) else res
        return float(strike_k)
    except Exception:
        return float('nan')


def _find_zero_cost_rebate(params: dict) -> float:
    """Solve for the daily rebate that makes the knock-out contract zero-cost."""
    def obj(r):
        p = params.copy()
        p['rebate'] = r
        return _price('knockout', p)
    try:
        res = brentq(obj, 0, 100, xtol=1e-2)
        rebate = res[0] if isinstance(res, (tuple, list)) else res
        return float(rebate)
    except:
        return 0.0

def plot_zero_cost_strike(params: dict, rebates=None) -> None:
    B = params['B']

    if rebates is None:
        rebates = np.linspace(0, 50, 50)

    K_normal = _find_zero_cost_k('normal', params)
    if K_normal != K_normal:
        print("  [Warning] Normal zero-cost K not found.")
        K_normal = params.get('K', B * 0.97)

    K_ko_list = []
    for reb in rebates:
        k = _find_zero_cost_k('knockout', {**params, 'rebate': reb})
        K_ko_list.append(k)
    K_ko_arr = np.array(K_ko_list)


    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    side = 1 if params.get('option_type', 'call').lower() == 'call' else -1
    valid = ~np.isnan(K_ko_arr)
    effective_discount = (K_normal - K_ko_arr) * side

    ax1.plot(rebates[valid], K_ko_arr[valid],
             'o-', color='darkorange', ms=4, lw=2, label='Knockout strike K with Zero-Cost')
    ax1.axhline(K_normal, color='steelblue', ls='--', lw=2,
                label=f'Normal strike K with Zero-Cost = {K_normal:.2f}')
    ax1.axhline(B, color='black', ls=':', lw=1, alpha=0.5, label=f'Barrier B={B}')
    ax1.set_ylabel('Zero-Cost Strike K', fontsize=10)
    ax1.set_title(f"Zero-Cost Strike Analysis ({params['option_type'].upper()})", fontweight='bold')
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)

    ax2.fill_between(rebates[valid], 0, effective_discount[valid],
                     where=(effective_discount[valid] >= 0),
                     color='forestgreen', alpha=0.3,
                     label='Benefit: Knockout gives better K for client')

    ax2.fill_between(rebates[valid], 0, effective_discount[valid],
                     where=(effective_discount[valid] < 0),
                     color='tomato', alpha=0.3,
                     label='Cost: Rebate over-compensates (K worsens)')

    ax2.plot(rebates[valid], effective_discount[valid], 'o-', color='darkgreen', ms=3)
    ax2.axhline(0, color='black', lw=1)

    discount_label = "(K_Normal - K_KO)" if side == 1 else "(K_KO - K_Normal)"
    ax2.set_ylabel(f'Effective Discount\n{discount_label}')
    ax2.set_xlabel('Daily Rebate')
    ax2.set_title('Value Exchange: KO Risk vs Strike Improvement', fontsize=9)
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.25)

    plt.tight_layout()
    plt.show()


def plot_pin_risk(params: dict, dist_low: float = 0.005, dist_high: float = 0.005,n_pts: int = 80,beta: float = 0.5826) -> None:

    B     = params['B']
    B_adj = _bgk_adj(params, beta)
    S_low  = B * (1 - dist_low)
    S_high  = B * (1 + dist_high)
    S_arr = np.linspace(S_low, S_high, n_pts)

    delta_normal, gamma_normal, delta_knockout, gamma_knockout = [], [], [], []

    print(f"  B = {B:.4f}")
    print(f"  B_adj = {B_adj:.4f}  (beta={beta}, sigma={params['sigma']:.0%})")
    print(f"  The zone between real barrier B and adjustment B_adj: [{B:.2f}, {B_adj:.2f}]  "
          f"width = {B_adj-B:.3f} pts = {(B_adj/B-1)*100:.3f}% of B")

    for S in S_arr:
        for ot, dl, gm in [('normal', delta_normal, gamma_normal),
                            ('knockout', delta_knockout, gamma_knockout)]:
            try:
                gk = _greeks(ot, params, S=S)
                dl.append(gk['delta'])
                gm.append(gk['gamma'])
            except Exception:
                dl.append(float('nan'))
                gm.append(float('nan'))

    delta_normal = np.array(delta_normal)
    gamma_normal = np.array(gamma_normal)
    delta_knockout = np.array(delta_knockout)
    gamma_knockout = np.array(gamma_knockout)


    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    gray = dict(color='gold', alpha=0.35, zorder=0)

    for ax, yn, yk, ylabel, title in [
        (ax1, delta_normal, delta_knockout, 'Delta', 'Delta Profile near Barrier'),
        (ax2, gamma_normal, gamma_knockout, 'Gamma', 'Gamma Profile (Pin Risk)'),
    ]:
        ax.axvspan(B, min(B_adj, S_high), **gray,
                   label=f'BGK gray zone [{B:.0f}, {B_adj:.1f}]')
        ax.plot(S_arr, yn, color='steelblue',  lw=2.2, label='Normal')
        ax.plot(S_arr, yk, color='darkorange', lw=2.2, ls='--', label='KO')
        ax.axvline(B,     color='black', lw=1.5, ls='--',
                   label=f'B={B} (contract)')
        ax.axvline(B_adj, color='red',   lw=1.2, ls=':',
                   label=f'B_adj={B_adj:.1f} (model)')
        ax.axhline(0, color='black', lw=0.8)
        ax.set_xlabel('Spot S', fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=10, fontweight='bold')
        ax.legend(fontsize=8)
        ax.grid(alpha=0.25)

    mid_gray = (B + min(B_adj, S_high)) / 2
    for ax in (ax1, ax2):
        ylim = ax.get_ylim()
        ypos = ylim[0] + (ylim[1] - ylim[0]) * 0.15
        ax.text(mid_gray, ypos,
                f'Gray zone\nContract: KO\nModel: alive',
                fontsize=7, color='saddlebrown', ha='center', va='bottom',
                bbox=dict(boxstyle='round', fc='lightyellow', alpha=0.85))

    plt.suptitle(
        f"Pin Risk: Normal vs Knockout  |  B={B}  B_adj={B_adj:.2f}\n"
        f"sigma={params['sigma']:.0%}  PR={params['PR']}  L={params['L']}  "
        f"rebate={params.get('rebate',0)}",
        fontsize=10,
    )
    plt.tight_layout()
    plt.show()


def plot_sensitivity(params: dict, n_pts: int = 40):

    S0, sig0 = params['S'], params['sigma']
    k_zero = _find_zero_cost_k('normal', params)
    params['K'] = k_zero

    rebate_zero = _find_zero_cost_rebate(params)
    params['rebate'] = rebate_zero

    print(f"  [Setup] K={k_zero:.2f}, Zero-Cost Rebate={rebate_zero:.2f}")

    S_vals = np.linspace(S0 * 0.97, params['B'] * 1.03, n_pts)
    sig_vals = np.linspace(sig0 * 0.5, sig0 * 3.0, n_pts)

    def sweep(vary_name, vals, metric='price'):
        n_r, k_r = [], []
        for v in vals:
            current_p = {**params, vary_name: v}
            if metric == 'price':
                n_r.append(_price('normal', current_p))
                k_r.append(_price('knockout', current_p))
            else:  # delta or gamma
                n_gk = _greeks('normal', current_p)
                k_gk = _greeks('knockout', current_p)
                n_r.append(n_gk[metric])
                k_r.append(k_gk[metric])
        return np.array(n_r), np.array(k_r)


    val_S_n, val_S_k = sweep('S', S_vals, 'price')
    val_sig_n, val_sig_k = sweep('sigma', sig_vals, 'price')
    dl_sig_n, dl_sig_k = sweep('sigma', sig_vals, 'delta')
    gm_sig_n, gm_sig_k = sweep('sigma', sig_vals, 'gamma')


    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    ax = axes[0, 0]
    ax.plot(S_vals, val_S_n, label='Normal Value', color='steelblue')
    ax.plot(S_vals, val_S_k, label='KO Value', color='darkorange', ls='--')
    ax.axvline(params['K'], color='Green', ls='-', label='Strike')
    ax.axvline(S0, color='red', ls=':', label='Entry Spot')
    ax.axvline(params['B'], color='black', ls='-', alpha=0.3, label='Barrier')
    ax.set_title("Valuation vs Spot")
    ax.set_ylabel("NPV (Value)")


    ax = axes[0, 1]
    ax.plot(sig_vals * 100, val_sig_n, label='Normal Value', color='steelblue')
    ax.plot(sig_vals * 100, val_sig_k, label='KO Value', color='darkorange', ls='--')
    ax.axvline(sig0 * 100, color='Red', ls='-', label='current sigma')
    ax.set_title("Valuation vs Volatility")
    ax.set_ylabel("NPV (Value)")
    ax.set_xlabel("Sigma (%)")

    ax = axes[1, 0]
    ax.plot(sig_vals * 100, dl_sig_n, label='Normal Delta', color='steelblue')
    ax.plot(sig_vals * 100, dl_sig_k, label='KO Delta', color='darkorange', ls='--')
    ax.axvline(sig0 * 100, color='Red', ls='-', label='current sigma')
    ax.set_title("Delta vs Volatility")
    ax.set_ylabel("Delta")
    ax.set_xlabel("Sigma (%)")

    ax = axes[1, 1]
    ax.plot(sig_vals * 100, gm_sig_n, label='Normal Gamma', color='steelblue')
    ax.plot(sig_vals * 100, gm_sig_k, label='KO Gamma', color='darkorange', ls='--')
    ax.axvline(sig0 * 100, color='Red', ls='-', label='current sigma')
    ax.set_title("Gamma vs Volatility")
    ax.set_ylabel("Gamma")
    ax.set_xlabel("Sigma (%)")

    for a in axes.flatten():
        a.legend(fontsize=9)
        a.grid(alpha=0.3)
        a.axhline(0, color='black', lw=1)

    plt.suptitle(f"Greeks and Valuation Profile (Initial Zero-Cost at S={S0}, K={k_zero:.1f}, Rebate={rebate_zero:.2f})", fontsize=12,
                 fontweight='bold')
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()



def run_comparison(params: dict,
                   sections: tuple = (0, 1, 2, 3),
                   rebates=None) -> None:
    sep = '=' * 65
    print(f"\n{sep}")
    print(f"  Normal vs KO Accumulator — Comparison")
    print(sep)

    if 0 in sections:
        print_summary(params)
    if 1 in sections:
        print("\nZero-cost strike analysis")
        plot_zero_cost_strike(params, rebates=rebates)
    if 2 in sections:
        print("\nPin risk analysis")
        plot_pin_risk(params)
    if 3 in sections:
        print("\nParameter sensitivity analysis")
        plot_sensitivity(params)

    print(f"\n{sep}\n  Done.\n{sep}")



if __name__ == '__main__':
    params = dict(
        S=3362, K=3315, B=3409,
        r=0.03, b=0.0, sigma=0.09,
        PR=1.0, L=2.0,
        strike_shift=0.002,
        rebate=10.0,
        option_type='call',
        start_dt="2026.04.20 21:17:01",
        end_dt="2026.06.18 15:00:00",
    )

    run_comparison(params, sections=(0,1,2,3))