# Implied Volatility Surface (TSLA)

Building an implied-volatility surface from raw TSLA option quotes,
and using it to study smile dynamics and the delta corrections a desk needs
when spot moves.
---

## Scope and a key modelling assumption

The dataset is **TSLA call options only**, and TSLA pays no regular dividend.
By Merton (1973), early exercise of a call on a non-dividend-paying stock is
never optimal, so the American call equals the European call and Black-Scholes
is exact for both pricing and IV inversion. The IV solver therefore uses BSM
directly.

This argument does **not** extend to American puts (early exercise can be
optimal for deep-ITM puts), which would need a dedicated American-put pricer.
Restricting to non-dividend calls keeps the surface clean and theoretically
exact — a deliberate scope choice, stated explicitly.

All time-to-expiry uses the dual-time framework: T_trade (trading seconds)
drives the diffusion term, T_cal (calendar) drives carry and discounting.

---

## Pipeline

1. **Solve IV from mid prices.** For each option, invert the BSM price at
   mid = (bid+ask)/2 to an implied vol. The solver starts with the
   Brenner-Subrahmanyam ATM approximation, runs Newton-Raphson on vega, and
   falls back to bisection when vega is too small to trust (deep OTM). Prices
   violating no-arbitrage bounds return NaN.

2. **Clean the data.** Drop low-price, low-volume, wide-spread quotes; restrict
   log-moneyness and the BSM delta to [5%, 95%] (removing unreliable deep
   OTM/ITM wings); drop failed or extreme IV solves. This leaves a
   high-fidelity set for surface fitting.

3. **Interpolate the surface (RBF).** Fit a thin-plate-spline radial-basis
   interpolator over ($\text{log-moneyness}$, $\sqrt{T}$ ). The $\sqrt{T}$ axis is used because skew
   scales as $1 / \sqrt{T}$ and total variance as T, which linearises the surface and
   stabilises interpolation and extrapolation.

SVI (below) is fitted separately per expiry for the smile plots; the
**surface itself is the RBF**, which every later query and the
sticky-rule analysis use.

---

## 1. Term Structure

![Term structure](../images/tsla_vol_term_structure.png)

Three views of the volatility term structure:

- **ATM IV** rises sharply from the 2-day expiry (~56%) and stabilises around
  63–66% — the short end is depressed (little time, low event risk priced) and
  the curve flattens at longer tenors.
- **Total variance $\sigma^2 T$** is plotted against a linear fit. A no-arbitrage
  surface must have total variance **monotone increasing** in T (otherwise
  calendar arbitrage exists). The near-linear, monotone fit confirms the
  surface is calendar-arbitrage-free.
- **Forward IV** (the vol of each forward period between expiries) extracted
  from successive total variances. Lower in forward ATM IV indicate periods that the 
  market expects to be relatively calmer, even if the overall spot-to-maturity ATM IV remains elevated.


---

## 2. Smiles per Expiry (with SVI)

![Smiles](../images/tsla_vol_smiles.png)

Each panel is one expiry: IV scatter coloured by delta, with the SVI fit
overlaid. The top axis marks approximate delta levels (10$\Delta$..90$\Delta$).

### What SVI is

SVI (Stochastic-Volatility-Inspired, Gatheral 2004) is a five-parameter form
for **one expiry's** smile. It parameterises **total variance** $w = \sigma^2 T$, not
volatility directly:

    
  $w(x) = a + b[ \rho (x − m) + \sqrt{((x − m)^2 + \sigma^2)} ],   x = ln(K/F)$

The five parameters have clean geometric meanings:

| Parameter    | Controls                                          |
|--------------|---------------------------------------------------|
| **$a$**      | overall level (raises/lowers the whole slice)     |
| **$b$**      | wing slope (how steeply both wings rise)          |
| **$\rho$**   | direction of the skew                             |
| **$m$**      | horizontal position of the smile's minimum        |
| **$\sigma$** | curvature of the trough (larger = rounder bottom) |


### Why SVI rather than a polynomial

SVI has no-arbitrage structure built in. By Lee's moment formula, total
variance can grow **at most linearly** in the far wings; SVI's wings are linear
by construction, so it extrapolates sensibly, whereas a polynomial grows
quadratically and misbehaves. The fit also enforces $a + b·\sigma·\sqrt{(1−\rho^2)} ≥ 0$, which
keeps total variance non-negative (no butterfly arbitrage). The fit minimises
squared error in variance space from three starting points (SVI is non-convex)
with these constraints as penalties.

### What the smiles show

The short expiries show a pronounced, convex smile (steep put-side skew, the
classic equity shape). As maturity lengthens the smile turns to skews and the
minimum drifts to higher moneyness — visible as the SVI trough moving right.
The fit tracks the data tightly across all tenors, confirming the IV solver and
the smile shape are well-behaved.

---

## 3. Surface and Diagnostics

![Surface](../images/tsla_vol_surface.png)

- **3-D surface & heatmap:** the RBF surface over (log-moneyness, days). The
  dominant feature is the steep rise in IV for low strikes at short maturity
  (the deep red corner) — short-dated downside protection is expensive, the
  hallmark of equity skew.
- **Skew term structure** (25$\Delta$ − 75$\Delta$): negative at all tenors (put skew),
  steepest at short maturity and flattening with time — skew decays roughly as
  $1/\sqrt{T}$.
- **Smile convexity** (25$\Delta$ butterfly): mostly positive, the smile's curvature;
  a spike at one tenor flags a locally sharper smile.
- **Smile dispersion** (vol-of-vol proxy): the spread of IV across the 20$\Delta$–80$\Delta$
  range, a rough measure of how much the smile "bends" at each tenor.

---

## 4. Sticky Rules — the desk-relevant part

![Sticky rules](../images/tsla_vol_sticky.png)

When spot moves from S0 to S1, how does the smile move with it? There is no
single answer — it depends on the **sticky convention** the market follows, and
the choice changes the **hedging delta**. This is the most practically
important analysis in the file.

### Where the delta corrections come from

When the smile moves with spot, the IV of a fixed strike is itself a function
of spot, so the true hedging delta is the total derivative:


$\Delta_{eff} = \frac{dV}{dS} = \underbrace{\frac{\partial V}{\partial S}}_{\Delta_{BSM}}$
$+ \underbrace{\frac{\partial V}{\partial \sigma}}_{vega} \cdot \frac{d\sigma}{dS}$

The correction is essentially a vanna term $(vega × d\sigma/dS)$: choosing the wrong
sticky rule means hedging with the wrong vanna adjustment.

### The three conventions

- **Sticky Strike (SS):** $\sigma(K, T)$ stays fixed — each strike keeps its vol. In
  moneyness space the smile shifts left by ln(S1/S0) when spot rises. ATM vol
  then falls as spot rises (negative vol-spot correlation). Hedging delta needs
  **no correction**: $\Delta_{eff} = \Delta_{BSM}$.

- **Sticky Moneyness (SM):** $\sigma(ln(K/S), T)$ stays fixed — the smile shape is
  pinned to moneyness and does not shift laterally. ATM vol is unchanged as
  spot moves. The hedging delta gains a vanna correction:
  $\Delta_{eff} = \Delta_{BSM} - vega·skew·1/S$, Where $skew = \partial{\sigma}/\partial(ln(S/K))$

- **Sticky Delta (SD):** $\sigma(\Delta, T)$ stays fixed. Since delta and moneyness are nearly
  one-to-one, this almost matches Sticky Moneyness. The two query the old smile
  at slightly different moneyness points — sticky-delta preserves d1, giving
  $x_{new} = (b + 1 /2 \sigma^2)T − d_1· \sigma \sqrt{T}$, versus sticky-moneyness's plain $ln(K/S_1)$. The gap
  between these moneyness points is the $1/2 \sigma^2 T$ drift term in d1; it feeds through
  the skew slope into an IV difference and hence a small delta difference. So
  the two coincide for small $\sigma^2T$ or flat skew and separate as both grow.
  the skew slope.

### Why it matters

Panel D overlays all three for a +10% spot shock. The ATM vol the desk would
mark differs by rule — e.g. 60.6% under Sticky Strike versus 64.2% under Sticky
Moneyness — and that feeds straight into the delta hedge. Choosing the wrong
sticky convention means hedging with the wrong delta: a desk that assumes
sticky-strike but lives in a sticky-moneyness world will be systematically
under- or over-hedged after spot moves. The vanna correction (vega × skew
slope) is exactly the adjustment that distinguishes them.

This connects the smile geometry to a concrete P&L consequence — which sticky
assumption you make is a real risk decision, not a modelling detail.

---

## Limitations

- Calls only, non-dividend underlier — exact by Merton, but the method does not
  extend to American puts without a dedicated pricer.
- The RBF surface is a smooth interpolant, not an arbitrage-free model: it does
  not strictly guarantee the absence of butterfly or calendar arbitrage
  everywhere (the diagnostics check for it rather than enforce it). A fully
  arbitrage-free surface would use an SVI/SSVI calibration across all slices
  with the no-arb constraints imposed jointly.
- SVI is used for per-slice visualisation, not stitched into the surface.

