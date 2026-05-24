"""
Monte Carlo vs analytic price convergence check.

Validates the analytic pricers (Carr-Madan replication for the normal
accumulator, Haug closed-form for the knock-out) against Monte Carlo by
plotting the MC mean and its 95% confidence interval against the analytic
price as the number of paths grows. A ±5% band around the analytic price is
shown for reference.

Known behavior near the barrier: When the spot approaches the barrier level B,
the pricing discrepancy between the analytical solutions (both normal and KO) and
the Monte Carlo results becomes larger than when the spot is far from the barrier.
This is caused by the use of the strike-shift and BGK corrections, which introduce
deviations between the analytical pricing formulas and the actual payoff.
"""
import numpy as np
import matplotlib.pyplot as plt
import inspect
from models.normal_accumulator import AccumulatorReplication, AccumulatorMC
from models.ko_accumulator import KnockOutAccumulatorPricer, KnockOutAccumulatorMC


def filter_params_for_class(cls, params: dict):
    sig = inspect.signature(cls.__init__)
    valid_keys = sig.parameters.keys()
    return {k: v for k, v in params.items() if k in valid_keys}

def plot_mc_convergence_generic(analytic_cls, mc_cls, base_params: dict,option_name: str = "",n_paths_list=(500, 1000, 2000, 5000, 10000, 30000, 50000,100000)):
    filtered_params = filter_params_for_class(analytic_cls, base_params)
    pricer = analytic_cls(**filtered_params)
    analytic_price = pricer.price()
    mc_means = []
    ci_lo = []
    ci_hi = []


    for n in n_paths_list:
        assert n % 2 == 0, "The number of paths must be even"
        filtered_params = filter_params_for_class(mc_cls, base_params)
        mc = mc_cls(**filtered_params, n_paths=n)
        rng = np.random.default_rng(base_params.get('seed', 42))
        S_obs = mc.simulate_gbm_path(rng)
        payoff = mc.pay_off(S_obs)

        if payoff.ndim == 1:
            pv = payoff
        else:
            pv = payoff @ mc.df_obs

        mean = float(pv.mean())
        se = float(pv.std(ddof=1) / np.sqrt(n))

        mc_means.append(mean)
        ci_lo.append(mean - 1.96 * se)
        ci_hi.append(mean + 1.96 * se)



    x = np.array(n_paths_list)
    mc_means = np.array(mc_means)
    ci_lo = np.array(ci_lo)
    ci_hi = np.array(ci_hi)

    fig, ax = plt.subplots(figsize=(9, 5))

    lower_bound = analytic_price * 0.95
    upper_bound = analytic_price * 1.05
    ax.fill_between(x, lower_bound, upper_bound,
                    alpha=0.1, color='red',
                    label=f'±5% band of analytic')

    ax.fill_between(x, ci_lo, ci_hi, alpha=0.3, label='95% confidence interval of MC')
    ax.plot(x, mc_means, 'o-', lw=1.5, ms=5, label='MC Mean')
    ax.axhline(analytic_price, linestyle='--',
               label=f'Analytic {analytic_price:.4f}')

    diff = mc_means[-1] - analytic_price

    ax.set_xscale('log')
    ax.set_xlabel('Number of paths (log scale)')
    ax.set_ylabel('Price')
    ax.set_title(
        f"MC Convergence — {option_name}\n"
        f"S={base_params['S']}  K={base_params['K']}  B={base_params['B']}\n"
        f"Analytic={analytic_price:.4f} | MC {n_paths_list[-1]:,} paths difference={diff:+.4f} ({diff / analytic_price * 100:+.3f}%)"
    )

    ax.legend()
    ax.grid(True)

    ax.xaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f'{int(v):,}')
    )
    plt.xticks(x, [f'{n:,}' for n in n_paths_list], rotation=30)

    plt.tight_layout()
    plt.show()


def run_convergence(option_name: str, params: dict):

    PRICER_MAP = {
        "normal": (AccumulatorReplication, AccumulatorMC),
        "knockout": (KnockOutAccumulatorPricer, KnockOutAccumulatorMC),
    }

    if option_name not in PRICER_MAP:
        raise ValueError("option_name must be 'normal' or 'knockout'")

    analytic_cls, mc_cls = PRICER_MAP[option_name]

    print(f"\nThe convergence of {option_name} ")

    plot_mc_convergence_generic(analytic_cls,mc_cls,params, option_name=option_name)

if __name__ == "__main__":

    params = dict(
        S=3400,
        K=3315,
        B=3409,
        r=0.03,
        b=0.0,
        sigma=0.09,
        PR=1.0,
        L=2.0,
        strike_shift=0.002,
        rebate=10,
        option_type='call',
        start_dt="2026.04.20 15:00:01",
        end_dt="2026.06.18 15:00:00",
        trading_days_per_year=242,
        seed=46
    )


    run_convergence("normal", params)
    run_convergence("knockout", params)