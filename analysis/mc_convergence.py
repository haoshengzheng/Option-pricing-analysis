import numpy as np
import matplotlib.pyplot as plt
import inspect

from models.normal_accumulator import AccumulatorReplication
from models.normal_accumulator import AccumulatorMC
from models.ko_accumulator import KnockOutAccumulatorPricer
from models.ko_accumulator import KnockOutAccumulatorMC


def filter_params_for_class(cls, params: dict):
    sig = inspect.signature(cls.__init__)
    valid_keys = sig.parameters.keys()
    return {k: v for k, v in params.items() if k in valid_keys}

def plot_mc_convergence_generic(analytic_cls, mc_cls, base_params: dict,n_paths_list=(500, 1000, 2000, 5000, 10000, 30000, 50000)):
    filtered_params = filter_params_for_class(analytic_cls, base_params)
    pricer = analytic_cls(**filtered_params)
    analytic_price = pricer.price()
    print(f"Analytic price: {analytic_price:.6f}")
    mc_means = []
    ci_lo = []
    ci_hi = []


    for n in n_paths_list:
        assert n % 2 == 0, "路径数须为偶数（方便对称采样）"
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

        print(f"Paths={n:>6} | MC={mean:.6f} | CI=({ci_lo[-1]:.6f}, {ci_hi[-1]:.6f})")

    x = np.array(n_paths_list)
    mc_means = np.array(mc_means)
    ci_lo = np.array(ci_lo)
    ci_hi = np.array(ci_hi)

    fig, ax = plt.subplots(figsize=(9, 5))

    lower_bound = analytic_price * 0.95
    upper_bound = analytic_price * 1.05
    ax.fill_between(x, lower_bound, upper_bound,
                    alpha=0.1, color='green',
                    label=f'±5% band ({lower_bound:.4f}, {upper_bound:.4f})')

    ax.fill_between(x, ci_lo, ci_hi, alpha=0.2, label='95% CI')
    ax.plot(x, mc_means, 'o-', lw=1.5, ms=5, label='MC Mean')
    ax.axhline(analytic_price, linestyle='--',
               label=f'Analytic {analytic_price:.4f}')

    ax.set_xscale('log')
    ax.set_xlabel('Number of paths (log scale)')
    ax.set_ylabel('Price')
    ax.set_title("MC Convergence")

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

    plot_mc_convergence_generic(
        analytic_cls,
        mc_cls,
        params
    )

if __name__ == "__main__":

    params = dict(
        S=3133,
        K=3130.5,
        B=3193,
        r=0.03,
        b=0.0,
        sigma=0.115,
        PR=1.0,
        L=2.0,
        strike_shift=0.002,
        rebate=10,
        option_type='call',
        start_dt="2026.04.16 15:00:01",
        end_dt="2026.05.07 15:00:00",
        trading_days_per_year=242,
        seed=42
    )


    run_convergence("normal", params)
    run_convergence("knockout", params)