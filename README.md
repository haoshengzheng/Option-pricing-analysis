# Option-pricing-analysis
# Exotic Options Pricing Library

A Python library for pricing and risk-managing exotic options used in the Chinese OTC derivatives market, with focus on Accumulators, Knock-Out Accumulators, and Discrete Barrier Options.

## Core Architecture: Dual-Time Framework & Market Alignment

### 1. The Dual-Time Axis Principle (`Trading Time` vs. `Calendar Time`)
Chinese commodity options trade in fragmented sessions (typically 09:00-15:00 day + 21:00-23:00 night, depending on the contract) with weekends and public 
holidays excluded. Treating maturity as flat 365-day calendar time distorts both implied vol and Greeks. This library decouples the time axis:
* **Trading Time ($T_{\text{trade}}$):** Counted precisely **second-by-second** based only on active exchange sessions (incorporating China's specific morning, afternoon, and night sessions, summing up to trading seconds per full day**). Volatility accumulation and diffusion in Geometric Brownian Motion (GBM) are driven exclusively along this axis to prevent the unphysical decay of option value over non-trading periods.
* **Calendar Time ($T_{\text{cal}}$):** Calculated on a continuous standard 365-day basis, utilized strictly for discounting cash flows ($e^{-r T_{\text{cal}}}$) and calculating cost-of-carry yields, ensuring precise present-value accounting.

* This method of splitting is in line with the reality of China's futures market and is implemented consistently across vanilla, barrier, and accumulator pricers (see 'core/time_utils.py' for session definitions.

### 2. Implementation & Validation
* All pricers are independently developed from scratch based on classical literature, references without consulting any external codebase — no QuantLib,
  no proprietary toolkits.
* **Key references:**
* Haug (2007) — closed-form vanilla and 8-type discrete barrier
* Broadie, Glasserman & Kou (1997) — discrete barrier correction (β ≈ 0.5826)
* Carr & Madan (1998) - static replication of European payoffs via vanilla portfolio
* **Market-consistent pricing.** Under identical parameters, the library
  reproduces the prices and Greek profiles quoted by onshore sell-side
  desks, validated through the author's direct experience in OTC
  settlement.


## Analysis & Diagnostic Modules

### 1. Bump-Size Stability & Numerical Greeks Analysis (`bump_size.py`)
Calculates first and second-order option Greeks via finite difference methods and diagnostics numerical stability.
* **Richardson Extrapolation:** Establishes an $\mathcal{O}(h^4)$ convergence benchmark to evaluate numerical differentiation accuracy without analytical gradients.
* **Optimal Bump Scanning:** Computes the **Optimal Bump Size ($h^*$)** and the **Stable Zone** (where relative errors stay within $1\%$) across a logarithmic spectrum, balancing truncation and round-off errors.
* **Near-Barrier Stress Testing:** Tracks how the stable zone narrows and $h^*$ shrinks as the underlying spot price approaches the knock-out barrier ($S \to B$), illustrating the impact of barrier discontinuities.

### 2. Normal vs. Knock-Out Comparative Framework (`comparison.py`)
Provides structural and economic comparisons between standard and barrier-restricted accumulator contracts.
* **Zero-Cost Strike Solver:** Dynamically solves for the zero-cost strike ($K$) or zero-cost daily rebate under varying market conditions using Brent's method.
* **Value Exchange Matrix:** Visualizes the "Risk-Return" trade-off, showing how much strike discount a client gains by absorbing knock-out risk.
* **Pin Risk & BGK Boundary Adjustment:** Features the Broadie-Glasserman-Kou (BGK) continuity correction ($B_{adj}$). Maps the exact "gray zone" where analytical models remain active but physical risk-management shifts to manual desk execution due to surging Gamma.

### 3. Multi-Dimensional Risk Sensitivities (`greeks.py`)
Generates comprehensive risk landscapes for primary Greeks across multiple dimensions.
* **Greeks vs. Market Parameters:** Maps Delta, Gamma, Vega, and Theta profiles across changing Spot ($S$) and Volatility ($\sigma$).
* **Time Decay Dynamics:** Truncates the total trading schedule to simulate Greek evolution across different time-to-maturity milestones ($T = 100\%, 75\%, 50\%, 25\%$).
* **MC Validation Overlay:** Overlays finite-difference Monte Carlo Greek estimations directly onto analytical curves to verify mathematical consistency.

### 4. Monte Carlo Convergence Diagnostics (`mc_convergence.py`)
An automated empirical testing engine designed to validate numerical pricing stability.
* **Confidence Interval (CI) Tracking:** Computes Monte Carlo running means alongside their $95\%$ Confidence Intervals against varying sample paths (up to 50,000+).
* **Variance Reduction Verification:** Features antithetic variates/symmetric sampling validation, confirming that empirical simulation converges asymptotically to the analytical baseline within a $\pm5\%$ error band.

### 5. PnL Attribution & Higher-Order Greek Decomposition (`pnl.py`)
A daily risk-management script designed to explain portfolio PnL changes via Taylor series expansion.
* **PnL Matrix Heatmap:** Generates a cross-sectional visual grid of portfolio NPV shifts under joint Spot ($\Delta S$) and Volatility ($\Delta \sigma$) moves.
* **Higher-Order Greek Decomposition:** Decomposes daily actual PnL into isolated risk drivers: Linear (Delta, Vega), Second-Order (Gamma, Vomma, Vanna), Time Decay (Theta per second via precise trading time tracking), and **Third-Order Vega (Speed/Color-equivalent adjustments)**.
* **Residual Tracking:** Isolates the unexplained PnL residual to evaluate the capturing capacity of the risk model.

