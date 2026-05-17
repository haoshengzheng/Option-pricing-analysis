import numpy as np
import matplotlib.pyplot as plt
from core.time_utils import generate_trading_day_obs
from models.normal_accumulator import AccumulatorReplication, AccumulatorMC
from models.ko_accumulator import KnockOutAccumulatorPricer, KnockOutAccumulatorMC


def _make_pricer(option_type, base, **override):
    p = {**base, **override}

    if option_type == "normal":
        return AccumulatorReplication(
            S=p['S'], K=p['K'], B=p['B'],
            r=p['r'], b=p['b'], sigma=p['sigma'],
            L=p['L'], PR=p['PR'], strike_shift=p['strike_shift'],
            option_type=p['option_type'],
            start_dt=p['start_dt'], end_dt=p['end_dt'],
        )

    elif option_type == "knockout":
        return KnockOutAccumulatorPricer(
            S=p['S'], K=p['K'], B=p['B'],
            r=p['r'], b=p['b'], sigma=p['sigma'],
            PR=p['PR'], L=p['L'], rebate=p['rebate'],
            option_type=p['option_type'],
            start_dt=p['start_dt'], end_dt=p['end_dt'],
        )


def _make_mc(option_type, base, n_paths, seed, **override):
    p = {**base, **override}
    if option_type == "normal":
        return AccumulatorMC(
            S=p['S'], K=p['K'], B=p['B'],
            r=p['r'], b=p['b'], sigma=p['sigma'],
            L=p['L'], PR=p['PR'],
            option_type=p['option_type'],
            start_dt=p['start_dt'], end_dt=p['end_dt'],
            n_paths=n_paths, seed=seed,
        )

    elif option_type == "knockout":
        return KnockOutAccumulatorMC(
            S=p['S'], K=p['K'], B=p['B'],
            r=p['r'], b=p['b'], sigma=p['sigma'],
            PR=p['PR'], L=p['L'], rebate=p['rebate'],
            option_type=p['option_type'],
            start_dt=p['start_dt'], end_dt=p['end_dt'],
            n_paths=n_paths, seed=seed,
        )


def _mc_price(option_type, mc):
    rng = np.random.default_rng(mc.seed)
    S_obs = mc.simulate_gbm_path(rng)
    payoff = mc.pay_off(S_obs)

    if option_type == "normal":
        return float((payoff @ mc.df_obs).mean())
    else:
        return float(payoff.mean())



def plot_metric_vs_params(option_type: str, metric: str, base_params: dict, S_range: tuple=(0.95, 1.05), sigma_range: tuple=(0.05, 0.5),
                          T_fracs: tuple=(1.0, 0.75, 0.5, 0.25), n_S: int=100, n_sig: int=50, mc_overlay: bool=True, mc_paths=30000,mc_seed=42,):

    assert metric in ('price', 'delta', 'gamma', 'vega', 'theta')

    base_S = base_params['S']
    base_sig = base_params['sigma']
    all_obs = generate_trading_day_obs(base_params['start_dt'], base_params['end_dt'])
    n_total = len(all_obs)

    def pricer_trunc(frac, **kw):
        n_keep = max(1, int(round(frac * n_total)))
        return _make_pricer(option_type, base_params,
                            end_dt=all_obs[n_keep - 1], **kw)

    def get_metric(p):
        if metric == "price":
            return p.price()
        return p.greeks()[metric]

    colors = ['steelblue', 'darkorange', 'green', 'crimson']
    fig, axes = plt.subplots(1, 3, figsize=(16, 4))


    ax = axes[0]
    S_vals = np.linspace(base_S * S_range[0], base_S * S_range[1], n_S)

    for frac, col in zip(T_fracs, colors):
        vals = [get_metric(pricer_trunc(frac, S=s)) for s in S_vals]
        ax.plot(S_vals, vals, color=col, label=f"T={frac:.0%}")

    ax.axvline(base_params['K'], color='grey', ls=':', label='K')
    ax.axvline(base_params['B'], color='black', ls='--', label='B')

    # MC overlay
    if mc_overlay and metric in ('price', 'delta', 'gamma', 'vega'):
        eps_S = base_S * 1e-3

        if metric == "price":
            mc_val = _mc_price(option_type,
                _make_mc(option_type, base_params, mc_paths, mc_seed))

        elif metric == "delta":
            up = _mc_price(option_type, _make_mc(option_type, base_params, mc_paths, mc_seed, S=base_S+eps_S))
            dn = _mc_price(option_type, _make_mc(option_type, base_params, mc_paths, mc_seed, S=base_S-eps_S))
            mc_val = (up - dn) / (2 * eps_S)

        elif metric == "gamma":
            up = _mc_price(option_type, _make_mc(option_type, base_params, mc_paths, mc_seed, S=base_S+eps_S))
            mid = _mc_price(option_type, _make_mc(option_type, base_params, mc_paths, mc_seed))
            dn = _mc_price(option_type, _make_mc(option_type, base_params, mc_paths, mc_seed, S=base_S-eps_S))
            mc_val = (up - 2*mid + dn) / eps_S**2

        elif metric == "vega":
            dv = 1e-4
            up = _mc_price(option_type, _make_mc(option_type, base_params, mc_paths, mc_seed, sigma=base_sig+dv))
            dn = _mc_price(option_type, _make_mc(option_type, base_params, mc_paths, mc_seed, sigma=base_sig-dv))
            mc_val = (up - dn) / (2 * dv) /100

        ax.scatter([base_S], [mc_val], color='red', s=70, label='MC')

    ax.set_title(f"{metric} vs S")
    ax.legend(fontsize=7)
    ax.grid()

    # ================= Panel 2: vs sigma =================
    ax = axes[1]
    sig_vals = np.linspace(sigma_range[0], sigma_range[1], n_sig)

    for frac, col in zip(T_fracs, colors):
        vals = [get_metric(pricer_trunc(frac, sigma=s)) for s in sig_vals]
        ax.plot(sig_vals * 100, vals, color=col)

    ax.set_title(f"{metric} vs sigma")
    ax.grid()

    # ================= Panel 3: vs time =================
    ax = axes[2]
    frac_vals = np.linspace(0.05, 1.0, 40)

    for mult, col in zip([0.8, 1.0, 1.2], ['steelblue', 'darkorange', 'green']):
        sig = base_sig * mult
        vals = [get_metric(pricer_trunc(f, sigma=sig)) for f in frac_vals]
        ax.plot(frac_vals * 100, vals, color=col, label=f"σ×{mult}")

    ax.set_title(f"{metric} vs time")
    ax.legend(fontsize=7)
    ax.grid()

    plt.suptitle(
        f"{metric.upper()} — {option_type.upper()} | "
        f"K={base_params['K']} B={base_params['B']} σ={base_sig:.0%}"
    )

    plt.tight_layout()
    plt.show()


def run_greeks(option_type, params):
    for m in ["delta"]:
        print(f"\n=== {option_type} | {m} ===")
        plot_metric_vs_params(option_type, m, params)


if __name__ == "__main__":

    params = dict(
        S=3362,
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
        start_dt="2026.04.20 21:17:01",
        end_dt="2026.06.18 15:00:00",
        trading_days_per_year=242,
        seed=42
    )
run_greeks("knockout", params)