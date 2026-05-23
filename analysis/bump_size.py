"""
Bump-size stability analysis for finite-difference Greeks.

The accumulator pricers compute some Greeks by finite difference (the
knock-out pricer fully so). The accuracy of a finite-difference Greek depends
critically on the bump size h, caught between two competing errors:

  - Truncation error: O(h^2) for central difference — grows with h
  - Round-off error : O(1/h) from floating-point cancellation — grows as h
                      shrinks

There is an optimal h that balances the two. This module scans h across many
orders of magnitude, benchmarks each estimate against a high-accuracy
Richardson-extrapolated reference (O(h^4)), and identifies the "stable zone"
where the relative error stays below 1%.

The analysis is most revealing near the knock-out barrier. As spot approaches
the (BGK-adjusted) barrier B_adj, any bump large enough to beat round-off may
straddle the barrier — where the value jumps discontinuously to the rebate —
making the difference meaningless. The stable zone narrows and can vanish entirely
when the spot is very close to barrier: no bump size gives a reliable Greek.

Note on the barrier level: when evaluating the knock-out pricer, the model's
effective barrier is the BGK-adjusted B_adj, not the contractual B. Stress
tests place spot relative to B_adj, since that is the level the model's
discontinuity actually sits at.
"""
import numpy as np
import matplotlib.pyplot as plt
from typing import Callable
from core.time_utils import trading_days_per_year
from models.normal_accumulator import AccumulatorReplication
from models.ko_accumulator import KnockOutAccumulatorPricer

STABLE_STANDARD = 0.01

def _cd1(f:Callable, x: float, h: float) -> float:
    """Central first difference: O(h^2) estimate of f'(x)."""
    return (f(x + h) - f(x - h)) / (2 * h)

def _fd1(f:Callable, x: float, h: float) -> float:
    """Forward first difference: O(h) estimate of f'(x)"""
    return (f(x + h) - f(x)) / h

def _cd2(f:Callable, x: float, h: float, f0: float | None = None) -> float:
    """Central second difference: O(h^2) estimate of f''(x)."""
    if f0 is None:
        f0 = f(x)
    return (f(x + h) - 2 * f0 + f(x - h)) / h ** 2

def _rich1(f:Callable, x: float, h: float) -> float:
    """Richardson first derivative: combines central differences at h and 2h to cancel the leading O(h^2) error, giving O(h^4) accuracy."""
    cd1_h = (f(x + h) - f(x - h)) / (2 * h)
    cd1_2h= (f(x + 2 * h) - f(x - 2 * h)) / (4 * h)
    return (4 * cd1_h - cd1_2h) / 3

def _rich2(f:Callable, x: float, h: float, f0: float | None = None) -> float:
    """Richardson second derivative"""
    if f0 is None:
        f0 = f(x)
    cd2_h = (f(x + h) - 2 * f0 + f(x - h)) / h ** 2
    cd2_2h = (f(x + 2 * h) - 2 * f0 + f(x - 2 * h)) / (2 * h) ** 2
    return (4 * cd2_h - cd2_2h) / 3

def build_pricer (option_type: str, params: dict) -> float:
    if option_type == 'normal':
        return AccumulatorReplication(
            S=params['S'], K=params['K'], B=params['B'],r=params['r'], b=params['b'], sigma=params['sigma'],
            L=params['L'], PR=params['PR'],strike_shift=params['strike_shift'],option_type=params['option_type'],
            start_dt=params['start_dt'], end_dt=params['end_dt']
        ).price()

    elif option_type == 'knockout':
        return KnockOutAccumulatorPricer(
            S=params['S'], K=params['K'], B=params['B'],r=params['r'], b=params['b'], sigma=params['sigma'],
            PR=params['PR'], L=params['L'], rebate=params['rebate'],option_type=params['option_type'],
            start_dt=params['start_dt'], end_dt=params['end_dt'],
        ).price()

    else:
        raise ValueError(f"option_type {option_type} is not supported, register it in build_pricer.")


def scan_bump_sizes(f:Callable, x0: float, bumps:np.ndarray, mode: str = 'central', rich_h: float | None = None, scale: float = 1.0) -> dict:
    """
    Scan a range of bump sizes and assess finite-difference stability. For each h in `bumps`, compute the finite-difference estimate,
    compare against a Richardson O(h^4) benchmark, and flag h as 'stable' if the relative error is below STABLE_STANDARD (1%).
    """
    if rich_h is None:
        rich_h = float(np.exp(np.mean(np.log(bumps))))

    f0 = f(x0)

    # Define the benchmark
    if mode =='second':
        benchmark= _rich2(f, x0, rich_h, f0) * scale
    else:
        benchmark = _rich1(f, x0, rich_h) * scale


    estimates = []
    for h in bumps:
        if mode == 'central':
            est = _cd1(f, x0, h)
        elif mode == 'forward':
            est = _fd1(f, x0, h)
        else:
            est = _cd2(f, x0, h, f0)
        estimates.append(est * scale)

    estimates = np.array(estimates)
    floor = abs(benchmark) if abs(benchmark) > 1e-12 else 1.0
    rel_err = np.abs(estimates - benchmark) / floor

    stable = rel_err < STABLE_STANDARD
    best_i = int(np.argmin(rel_err))

    return dict(
        bumps=bumps,estimates=estimates, rel_errors=rel_err, benchmark=benchmark,stable_mask=stable,optimal_h=bumps[best_i],
        stable_lo=float(bumps[stable][0]) if stable.any() else None,stable_hi=float(bumps[stable][-1]) if stable.any() else None,
        stability_score=float(stable.mean()),
    )



def _fmt(x) -> str:
    return f"{x:.2e}" if x is not None else "N/A"

def _print_summary(greek_results: list[tuple]) -> None:
    w = 80
    print(f"\n{'═' * w}")
    print(f"  {'Greek':<9} {'Method':<10} {'Reference':>12} "
          f"{'Optimal h':>12} {'Stable lo':>11} {'Stable hi':>11} {'Score':>6}")
    print(f"  {'─' * (w - 2)}")
    for label, method, res in greek_results:
        print(
            f"  {label:<9} {method:<10} "
            f"{res['benchmark']:>12.6f} "
            f"{_fmt(res['optimal_h']):>12} "
            f"{_fmt(res['stable_lo']):>11} "
            f"{_fmt(res['stable_hi']):>11} "
            f"{res['stability_score']:>5.0%}"
        )
    print(f"{'═' * w}\n")


def _shade_stable(ax, res, color='green', alpha=0.12) -> None:
    if res['stable_lo'] is not None:
        ax.axvspan(res['stable_lo'], res['stable_hi'],
                   color=color, alpha=alpha, label='Stable zone')
    ax.axvline(res['optimal_h'], color='red', ls='--', lw=1.2,
               label=f"Opt h = {_fmt(res['optimal_h'])}")



def plot_bump_stability(option_type: str, base_params: dict, n_bumps: int = 50,
                        S_frac_range: tuple = (1e-7, 5e-2),sigma_frac_range: tuple = (1e-7, 3e-1),show_forward: bool = True,
) -> None:

    S0 = base_params['S']
    sig0 = base_params['sigma']
    B  = base_params['B']

    S_bumps = S0 * np.logspace(*np.log10(S_frac_range), n_bumps)
    sig_bumps = sig0 * np.logspace(*np.log10(sigma_frac_range), n_bumps)

    def f_S(x):
        return build_pricer(option_type, {**base_params, 'S': x})

    def f_sigma(x):
        return build_pricer(option_type, {**base_params, 'sigma': x})


    res_delta_cd = scan_bump_sizes(f_S, S0, S_bumps, mode='central')
    res_delta_fd = scan_bump_sizes(f_S, S0, S_bumps, mode='forward')
    res_gamma    = scan_bump_sizes(f_S, S0, S_bumps, mode='second')
    res_vega     = scan_bump_sizes(f_sigma, sig0, sig_bumps, mode='central', scale= 1 /100)

    rows =[ ('Delta', 'S bump', res_delta_cd, res_delta_fd),
            ('Gamma', 'S bump', res_gamma, None),
            ('Vega', 'sigma bump', res_vega, None),
          ]

    fig, axes = plt.subplots(3, 2, figsize=(13, 11))
    colors = {'cd': 'steelblue', 'fd': 'darkorange', 'ref': 'grey', 'thresh': 'green'}


    for row_i, (label, xlabel, res_cd, res_fd) in enumerate(rows):
        ax_val = axes[row_i, 0]
        ax_err = axes[row_i, 1]
        bumps  = res_cd['bumps']


        ax_val.semilogx(bumps, res_cd['estimates'], '-',
                        color=colors['cd'], lw=1.8, label='Central diff O(h²)')
        if res_fd is not None:
            ax_val.semilogx(bumps, res_fd['estimates'], '--',
                            color=colors['fd'], lw=1.2, label='Forward diff O(h)')
        ax_val.axhline(res_cd['benchmark'], color=colors['ref'], ls=':',
                       lw=1.5, label=f"Richardson standard = {res_cd['benchmark']:.5f}")
        _shade_stable(ax_val, res_cd)
        ax_val.set_xlabel(f"{xlabel} (absolute)", fontsize=8)
        ax_val.set_ylabel(label, fontsize=9)
        ax_val.set_title(f"{label} — Value vs Bump Size", fontsize=9, fontweight='bold')
        ax_val.legend(fontsize=7)
        ax_val.grid(True, which='both', alpha=0.25)

        floor = 1e-15
        ax_err.loglog(bumps, np.maximum(res_cd['rel_errors'], floor),
                      '-', color=colors['cd'], lw=1.8, label='Central diff')
        if res_fd is not None:
            ax_err.loglog(bumps, np.maximum(res_fd['rel_errors'], floor),
                          '--', color=colors['fd'], lw=1.2, label='Forward diff')
        ax_err.axhline(STABLE_STANDARD, color=colors['thresh'], ls='--', lw=1.2,
                       label=f'{STABLE_STANDARD:.0%} threshold')
        _shade_stable(ax_err, res_cd)
        ax_err.set_xlabel(f"{xlabel} (absolute)", fontsize=8)
        ax_err.set_ylabel('Relative error  |est − bench| / |bench|', fontsize=8)
        ax_err.set_title(f"{label} — Error vs Bump Size (log-log)", fontsize=9,
                         fontweight='bold')
        ax_err.legend(fontsize=7)
        ax_err.grid(True, which='both', alpha=0.25)

    summary_rows = []
    for label, _, res_cd, res_fd in rows:
        summary_rows.append((label, 'Central', res_cd))
        if res_fd is not None:
            summary_rows.append((label, 'Forward', res_fd))
    _print_summary(summary_rows)

    dist_pct = abs(S0 - B) / B * 100
    fig.suptitle(
        f"Bump-Size Stability  [{option_type.upper()}] "
        f"S={S0}  K={base_params['K']}  B={B}  sigma={sig0:.0%}\n"
        f"(S−B)/B = {dist_pct:.2f}%   "
        f"Stable zone = relative error < {STABLE_STANDARD:.0%} vs Richardson O(h⁴) reference",
        fontsize=10
    )
    plt.tight_layout()
    plt.show()



def plot_near_barrier_bump(option_type: str, base_params: dict, n_S: int = 30, barrier_dist_range: tuple = (-0.0033, 0.05),
                           n_bumps: int = 25, S_frac_range: tuple = (1e-7, 5e-2)) -> None:


    B = base_params['B']
    cp = base_params.get('option_type', 'call').lower()

    dist_fracs = np.linspace(barrier_dist_range[0], barrier_dist_range[1], n_S)

    # For call: KO when S ≥ B → approach from below  (S < B)
    # For put:  KO when S ≤ B → approach from above  (S > B)
    if cp == 'call':
        S_vals = B * (1 - dist_fracs)
    else:
        S_vals = B * (1 + dist_fracs)

    optimal_hs = []
    stable_los = []
    stable_his = []
    stable_scores = []


    for i, (S_test, dist) in enumerate(zip(S_vals, dist_fracs)):
        S_bumps_i = S_test * np.logspace(*np.log10(S_frac_range), n_bumps)

        def f_S(x, _S=S_test):
            return build_pricer(option_type, {**base_params, 'S': x})

        res = scan_bump_sizes(f_S, S_test, S_bumps_i, mode='central')

        optimal_hs.append(res['optimal_h'])
        stable_los.append(res['stable_lo'] if res['stable_lo'] else np.nan)
        stable_his.append(res['stable_hi'] if res['stable_hi'] else np.nan)
        stable_scores.append(res['stability_score'])

        print(f"    [{i + 1:02d}/{n_S}]  S={S_test:.2f}  "
              f"dist={dist:.3f}  opt_h={res['optimal_h']:.2e}  "
              f"score={res['stability_score']:.0%}")

    dist_pct = dist_fracs * 100
    optimal_hs = np.array(optimal_hs)
    stable_los = np.array(stable_los)
    stable_his = np.array(stable_his)
    stable_scores = np.array(stable_scores)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))


    ax = axes[0]
    ax.semilogy(dist_pct, optimal_hs, 'o-', color='steelblue',
                ms=5, lw=1.5, label='Optimal delta bump')
    ax.fill_between(dist_pct, stable_los, stable_his,
                    alpha=0.2, color='steelblue', label='Stable zone bounds')
    ax.set_xlabel('Distance from barrier  (B−S)/B  [%]', fontsize=9)
    ax.set_ylabel('Optimal bump size  h*  (log scale)', fontsize=9)
    ax.set_title('Optimal delta Bump vs Barrier Distance', fontsize=10, fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(True, which='both', alpha=0.25)
    ax.invert_xaxis()


    ax = axes[1]
    ax.plot(dist_pct, stable_scores * 100, 'o-', color='green',
            ms=5, lw=1.5, label='Stability score')
    ax.axhline(50, color='grey', ls=':', lw=1, label='50% stability')
    ax.axhline(STABLE_STANDARD * 100, color='red', ls='--', lw=1)
    ax.fill_between(dist_pct, 0, stable_scores * 100, alpha=0.15, color='green')
    ax.set_xlabel('Distance from barrier  (B−S)/B  [%]', fontsize=9)
    ax.set_ylabel('Stability score  [%]', fontsize=9)
    ax.set_title('delta Numerical Stability Score vs Barrier Distance',
                 fontsize=10, fontweight='bold')
    ax.set_ylim(-5, 105)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.invert_xaxis()

    fig.suptitle(
        f"Near-Barrier delta Bump Analysis  [{option_type.upper()}]"
        f"  B={B}  K={base_params['K']}  sigma={base_params['sigma']:.0%}\n"
        "As S → B, the optimal bump shrinks and the stable zone narrows — "
        "a direct consequence of the barrier discontinuity",
        fontsize=9
    )
    plt.tight_layout()
    plt.show()


def run_bump_analysis(
    option_type: str,
    base_params: dict,
    near_barrier: bool = True,
    **stability_kwargs,
) -> None:

    sep = '═' * 65
    print(f"\n{sep}")
    print(f"  Bump-Size Analysis — {option_type.upper()}")
    print(f"  S={base_params['S']}  B={base_params['B']}"
          f"  K={base_params['K']}  sigma={base_params['sigma']:.0%}")
    dist = abs(base_params['S'] - base_params['B']) / base_params['B']
    print(f"  Barrier distance (B−S)/B = {dist:.2%}")
    print(sep)

    plot_bump_stability(option_type, base_params, **stability_kwargs)

    if near_barrier:
        plot_near_barrier_bump(option_type, base_params)


if __name__ == '__main__':
    params_normal = dict(
        S=3362, K=3315, B=3409,
        r=0.03, b=0.0, sigma=0.09,
        PR=1.0, L=2.0,
        strike_shift=0.002,
        rebate=10,
        option_type='call',
        start_dt="2026.04.20 21:17:01",
        end_dt="2026.06.18 15:00:00",
        trading_days_per_year=242,
    )
    #run_bump_analysis('normal', params_normal, near_barrier=True)


    params_ko = {**params_normal}
    #run_bump_analysis('knockout', params_ko, near_barrier=True)


    params_ko_near = {**params_ko, 'S': 3420.25}
    print("\n[Stress test: S close to B]")
    run_bump_analysis('knockout', params_ko_near, near_barrier=False, n_bumps=60, show_forward=True)

    params_normal_near = {**params_normal, 'S': 3420.25}
    print("\n[Stress test: S close to B]")
    run_bump_analysis('normal', params_normal_near, near_barrier=False, n_bumps=60, show_forward=True)






