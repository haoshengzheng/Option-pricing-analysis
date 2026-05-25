# Exotic Options Pricing & Risk Analytics

A from-scratch Python library for pricing and risk-managing the exotic options
traded in the Chinese OTC commodity market — Accumulators, Knock-Out
Accumulators, and discrete barrier options — built around a **dual-time
framework** that separates trading time from calendar time, with a suite of
risk-diagnostic studies and an implied-volatility surface for listed equity
options.

All pricers are implemented from first principles based on the classical
literature — no QuantLib, no proprietary toolkits — and validated internally
via put-call / in-out parity, Monte Carlo cross-checks, and agreement with
QuantLib on vanilla benchmarks.

![Pin risk near the barrier](/images/Pin_Risk.png)

---

## Why this library is different: the Dual-Time Framework

Chinese commodity options trade in fragmented sessions (typically 09:00–15:00
day plus 21:00–23:00 night, varying by contract), with weekends and public
holidays excluded. Treating maturity as flat 365-day calendar time distorts
both implied vol and Greeks — an option does not diffuse while the market is
closed, but its cash flows still discount over the weekend.

This library decouples the two clocks and uses each where it physically belongs:

- **Trading time (T_trade):** counted second-by-second over active exchange
  sessions only. It drives the diffusion term ($\sigma\sqrt{T}_{trade}$), so option value does
  not decay over nights, weekends, or holidays when no trading occurs.
- **Calendar time (T_cal):** the continuous 365-day clock, used strictly for
  discounting ($e^{−r·T_{cal}}$) and cost-of-carry.

This split mirrors how onshore desks mark these books and is applied
consistently across the vanilla, barrier, and accumulator pricers. Its
consequences surface throughout the analyses — for instance, theta is exactly
zero across an overnight marking window because no trading time elapses (PnL
study). The modelling choices here — dual-time accounting, the strike-shift
replication, the BGK gray-zone handling — follow onshore sell-side desk
practice, informed by the author's experience in OTC derivatives settlement.
Session definitions live in `core/time_utils.py`.

---

## Pricing engine (`core/`, `models/`)

- **Vanilla (BSM)** — Black-Scholes-Merton with the dual-time convention and
  cost-of-carry `b`; analytic Greeks.
- **Discrete barrier (Haug)** — closed-form 8-type barrier options
  (up/down × in/out × call/put) via the reflection principle, with the
  **Broadie-Glasserman-Kou (1997)** continuity correction ($\beta \approx 0.5826$) mapping
  continuous-monitoring formulas to discrete daily monitoring.
- **Accumulator** — priced by **Carr-Madan (1998)** static replication: the
  piecewise-linear daily payoff is decomposed into a finite portfolio of
  vanilla options ([derivation](docs/normal_accumulator_replication.md)).
- **Knock-Out Accumulator** — the accumulator with a knock-out barrier and
  rebate, built on the discrete-barrier engine.
- Each analytic pricer has a matching **Monte Carlo** implementation using
  **antithetic variates** for variance reduction, used for validation.

**Key references:** Haug (2007); Broadie, Glasserman & Kou (1997); Carr & Madan
(1998), *Towards a Theory of Volatility Trading*.

---

## Risk-analysis studies (coded in `analysis/`, documented in `docs/`)

Each study is a standalone module with a written analysis. Beyond standard
profiles, each surfaces a non-trivial finding:

| Study                                                    | Focus & key finding                                                                                                                                                                                                                                                         |
|----------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [PnL Attribution](docs/PnL_Attribution_analysis.md)      | Decomposes mark-to-market PnL into Greek contributions. **Finding:** the knock-out's rebate cap *shrinks* the upside residual versus the normal accumulator, and theta is exactly zero over a non-trading marking window — a direct dual-time consequence.                  |
| [Pin Risk & Comparison](docs/Comparison_and_pin_risk.md) | Normal vs Knockout; zero-cost strike trade-off; the BGK gray zone. **Finding:** maps the 11.5-point gray zone where the contract has knocked out but the model still prices it alive, and the gamma spike that forces manual hedging.                                       |
| [Bump-Size Stability](docs/Bump_size_stability.md)       | Optimal finite-difference bump and the "stable zone." **Finding:** a quarter-point from the barrier the knock-out has *no* stable bump size at all — any bump either crosses the discontinuity or hits round-off; the continuous normal accumulator survives the same spot. |
| [Greek Landscape](docs/Greeks_analysis.md)               | Price and Greek surfaces across spot, vol, and maturity. **Finding:** the value hump near the barrier moves with maturity, flipping the sign of delta, gamma, and vega — vega even passes through zero around 75% of maturity.                                              |
| [MC Convergence](docs/MC_convergence.md)                 | Validates analytic prices against Monte Carlo. **Finding:** near-barrier biases (strike-shift replication for the normal, BGK discrete-monitoring residual for the knock-out) confirmed systematic via a six-seed test, and vanish at the strike.                           |

---

## Implied-volatility surface (`volatility/`)

[Vol_surface](docs/Vol_Surface.md) — an IV surface for TSLA
listed calls:

- **Robust IV inversion** — Newton-Raphson on vega with a Brenner-Subrahmanyam
  seed and bisection fallback for deep-OTM options where vega vanishes.
- **Surface construction** — a thin-plate-spline RBF interpolant in
  (log-moneyness, $\sqrt{T}$); $\sqrt{T}$ is used because skew scales as $1/\sqrt{T}$ and variance as
  $T$, which linearises the surface.
- **Per-expiry SVI fits** — Gatheral's five-parameter form, with the
  no-arbitrage wing and non-negative-variance constraints, for the smile plots.
- **Sticky-rule analysis** — sticky strike / moneyness / delta, deriving the
  **vanna correction** ($\Delta_{eff} = \Delta_{BSM} − vega·skew/S$) each convention implies
  for the hedging delta, and the P&L consequence of choosing the wrong one.

(Calls on a non-dividend underlier, where American = European by Merton.)

---

## A recurring theme: the barrier region is special

Three independent studies converge on the same conclusion — the spot region
around the knock-out barrier is simultaneously:

- **financially dangerous** — pin risk: a near-discontinuous delta and an
  extreme localized gamma;
- **numerically unreliable** — finite-difference Greeks have no stable bump
  size there;
- **model-vs-contract inconsistent** — the BGK gray zone, where the model
  prices the option as alive but the contract has knocked out.

All three point to the same desk practice: near the barrier, automated hedging
gives way to manual intervention and analytic Greeks to scenario repricing.
This cross-study consistency — financial, numerical, and contractual risk all
localizing to the same spot region — is the central thread of the project.

---

## Project structure

| Document    | content or code                                           |
|-------------|-----------------------------------------------------------|
| core/       | vanilla BSM, discrete-barrier (Haug), dual-time utilities |
| models/     | normal & knock-out accumulators (analytic + Monte Carlo)  |
| analysis/   | pnl, comparison, bump_size, greeks, mc_convergence        |
| volatility/ | IV solver and vol-surface construction                    |
| docs/       | methodology and per-study write-ups                       |
| images/     | generated figures                                         |


## Installation

```bash
git clone https://github.com/haoshengzheng/Option-pricing-analysis.git
cd Option-pricing-analysis
pip install -r requirements.txt
```

Requires Python 3.10+.

## Usage

```python
from models.ko_accumulator import KnockOutAccumulatorPricer

pricer = KnockOutAccumulatorPricer(
    S=3362, K=3315, B=3409, r=0.03, b=0.0, sigma=0.09,
    PR=1.0, L=2.0, rebate=10.0, option_type='call',
    start_dt="2026.04.20 21:17:01", end_dt="2026.06.18 15:00:00",
)
print(pricer.price())
print(pricer.greeks())
```

Each analysis module runs standalone:

```bash
python -m analysis.pnl
python -m analysis.comparison
python -m analysis.bump_size
python -m analysis.greeks
python -m analysis.mc_convergence
```

---

## Validation

- **Put-call parity** and **in-out barrier parity** checks on the pricers.
- **Monte Carlo cross-checks** (antithetic variates) against every analytic
  price, with 95% confidence intervals shown to converge as $1/\sqrt{n}$.
- **QuantLib agreement** on vanilla benchmarks to under 1e-6.

---

## Scope and limitations

- The accumulator's Carr-Madan replication is accurate away from the barrier
  but carries a known approximation error within a fraction of a percent of B
  (quantified in the MC convergence study).
- Session definitions in `core/time_utils.py` are configured for specific
  Chinese commodity sessions and must be adjusted for other contracts.
- The volatility surface covers non-dividend equity calls; American puts would
  require a dedicated early-exercise pricer.
