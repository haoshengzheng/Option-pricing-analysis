import numpy as np
from scipy.stats import norm

from core.time_utils import count_trading_seconds_precise, count_trading_days, parse_dt, SECONDS_PER_FULL_TRADE_DAY


'''''''''
Two types of time are taken into account here: trading time and calendar time, to ensure greater alignment with the real world. 
'''''''''

class HaugBarrierDualTime:
    def __init__(self, S, X, H, T_cal, T_trade, r, b, sigma, K=0):
        self.S, self.X, self.H = S, X, H
        self.T_cal, self.T_trade = T_cal, T_trade
        self.r, self.b, self.sigma, self.K = r, b, sigma, K
        self.sigmaT = sigma * np.sqrt(T_trade)
        self.mu = (b - sigma ** 2 / 2) / sigma ** 2
        self.lamda = np.sqrt(self.mu ** 2 + 2 * r / sigma ** 2)
        self.x1 = np.log(S / X)      / self.sigmaT + (1 + self.mu) * self.sigmaT
        self.x2 = np.log(S / H)      / self.sigmaT + (1 + self.mu) * self.sigmaT
        self.y1 = np.log(H**2/(S*X)) / self.sigmaT + (1 + self.mu) * self.sigmaT
        self.y2 = np.log(H / S)      / self.sigmaT + (1 + self.mu) * self.sigmaT
        self.z  = np.log(H / S)      / self.sigmaT + self.lamda * self.sigmaT


    def term_A(self, phi):
        df_S = np.exp((self.b - self.r) * self.T_cal)   # 标的资产贴现因子
        df_X = np.exp(-self.r * self.T_cal)              # 执行价贴现因子
        return (phi * self.S * df_S * norm.cdf(phi * self.x1)
                - phi * self.X * df_X * norm.cdf(phi * self.x1 - phi * self.sigmaT))

    def term_B(self, phi):
        df_S = np.exp((self.b - self.r) * self.T_cal)
        df_X = np.exp(-self.r * self.T_cal)
        return (phi * self.S * df_S * norm.cdf(phi * self.x2)
                - phi * self.X * df_X * norm.cdf(phi * self.x2 - phi * self.sigmaT))

    def term_C(self, phi, eta):
        df_S = np.exp((self.b - self.r) * self.T_cal)
        df_X = np.exp(-self.r * self.T_cal)
        pow1 = (self.H / self.S) ** (2 * (self.mu + 1))
        pow2 = (self.H / self.S) ** (2 * self.mu)
        return (phi * self.S * df_S * pow1 * norm.cdf(eta * self.y1)
                - phi * self.X * df_X * pow2 * norm.cdf(eta * self.y1 - eta * self.sigmaT))

    def term_D(self, phi, eta):
        df_S = np.exp((self.b - self.r) * self.T_cal)
        df_X = np.exp(-self.r * self.T_cal)
        pow1 = (self.H / self.S) ** (2 * (self.mu + 1))
        pow2 = (self.H / self.S) ** (2 * self.mu)
        return (phi * self.S * df_S * pow1 * norm.cdf(eta * self.y2)
                - phi * self.X * df_X * pow2 * norm.cdf(eta * self.y2 - eta * self.sigmaT))

    def term_E(self, eta):
        if self.K <= 0:
            return 0.0
        df = np.exp(-self.r * self.T_cal)
        pow2 = (self.H / self.S) ** (2 * self.mu)
        return self.K * df * (
            norm.cdf(eta * self.x2 - eta * self.sigmaT)
            - pow2 * norm.cdf(eta * self.y2 - eta * self.sigmaT)
        )

    def term_F(self, eta):
        if self.K <= 0:
            return 0.0
        pow_p = (self.H / self.S) ** (self.mu + self.lamda)
        pow_m = (self.H / self.S) ** (self.mu - self.lamda)
        return self.K * (
            pow_p * norm.cdf(eta * self.z)
            + pow_m * norm.cdf(eta * self.z - 2 * eta * self.lamda * self.sigmaT)
        )

    def price(self, barrier_type: str) -> float:
        phi = 1 if barrier_type.startswith('c') else -1
        eta = 1 if 'd' in barrier_type else -1

        bt = barrier_type.lower()

        if bt == 'cdo':
            if self.X >= self.H:
                return self.term_A(phi) - self.term_C(phi, eta) + self.term_F(eta)
            else:
                return self.term_B(phi) - self.term_D(phi, eta) + self.term_F(eta)

        elif bt == 'cdi':
            if self.X >= self.H:
                return self.term_C(phi, eta) + self.term_E(eta)
            else:
                return self.term_A(phi) - self.term_B(phi) + self.term_D(phi, eta) + self.term_E(eta)

        elif bt == 'cuo':
            if self.X >= self.H:
                return self.term_F(eta)
            else:
                return (self.term_A(phi) - self.term_B(phi)
                        + self.term_C(phi, eta) - self.term_D(phi, eta) + self.term_F(eta))

        elif bt == 'cui':
            if self.X >= self.H:
                return self.term_A(phi) + self.term_E(eta)
            else:
                return self.term_B(phi) - self.term_C(phi, eta) + self.term_D(phi, eta) + self.term_E(eta)

        elif bt == 'pdo':
            if self.X >= self.H:
                return (self.term_A(phi) - self.term_B(phi)
                        + self.term_C(phi, eta) - self.term_D(phi, eta) + self.term_F(eta))
            else:
                return self.term_F(eta)

        elif bt == 'pdi':
            if self.X >= self.H:
                return self.term_B(phi) - self.term_C(phi, eta) + self.term_D(phi, eta) + self.term_E(eta)
            else:
                return self.term_A(phi) + self.term_E(eta)

        elif bt == 'puo':
            if self.X >= self.H:
                return self.term_B(phi) - self.term_D(phi, eta) + self.term_F(eta)
            else:
                return self.term_A(phi) - self.term_C(phi, eta) + self.term_F(eta)

        elif bt == 'pui':
            if self.X >= self.H:
                return self.term_A(phi) - self.term_B(phi) + self.term_D(phi, eta) + self.term_E(eta)
            else:
                return self.term_C(phi, eta) + self.term_E(eta)

        else:
            raise ValueError(f"未知 barrier_type: {barrier_type!r}. "
                             "合法值: cdi/cdo/cui/cuo/pdi/pdo/pui/puo")


class DiscreteBarrierPricer:
    BETA_DEFAULT = 0.5826

    def __init__(self, start_dt: str, end_dt: str, S: float, X: float, H: float, r: float, b: float, sigma: float, K: float = 0.0, \
                 trading_days_per_year: int = 252, beta: float = BETA_DEFAULT, ):

        self.start = parse_dt(start_dt)
        self.end   = parse_dt(end_dt)
        self.S, self.X, self.H_orig = S, X, H
        self.r, self.b, self.sigma, self.K = r, b, sigma, K
        self.beta = beta
        self.ann = trading_days_per_year
        self.n_trading = count_trading_days(self.start, self.end)

        total_calendar_seconds = (self.end - self.start).total_seconds()
        self.T_cal   = total_calendar_seconds / (365 * 24 * 3600)

        self.total_trade_seconds = count_trading_seconds_precise(self.start, self.end)
        self.T_trade = self.total_trade_seconds / (self.ann * SECONDS_PER_FULL_TRADE_DAY)
        self.dt = 1.0 / self.ann


    @property
    def time_info(self) -> dict:
        cal_days = (self.end.date() - self.start.date()).days
        return {
            "起始时间":     str(self.start),
            "到期时间":     str(self.end),
            "自然日数":     cal_days,
            "T_cal (年)":  round(self.T_cal, 6),
            "交易日数":     self.n_trading,
            "T_trade (年)": round(self.T_trade, 6),
        }

    def _vanilla_price(self, barrier_type: str) -> float:
        is_call = 'c' in barrier_type.lower()
        S, X = self.S, self.X
        r, b, sigma = self.r, self.b, self.sigma
        T_cal = self.T_cal
        T_trade = self.T_trade

        if T_trade <= 0:
            return max(0.0, S - X) if is_call else max(0.0, X - S)
        d1 = (np.log(S / X) + (b + 0.5 * sigma ** 2) * T_trade) / (sigma * np.sqrt(T_trade))
        d2 = d1 - sigma * np.sqrt(T_trade)
        if is_call:
            price = S * np.exp((b - r) * T_cal) * norm.cdf(d1) \
                    - X * np.exp(-r * T_cal) * norm.cdf(d2)
        else:
            price = X * np.exp(-r * T_cal) * norm.cdf(-d2) \
                    - S * np.exp((b - r) * T_cal) * norm.cdf(-d1)
        return price

    def _bgk_adjust(self, is_upper: bool) -> float:
        correction = self.beta * self.sigma * np.sqrt(self.dt)
        sign = +1 if is_upper else -1
        return self.H_orig * np.exp(sign * correction)

    def discrete_price(self, barrier_type: str, show_detail: bool = False,) -> float:
        bt = barrier_type.lower()
        is_upper = 'u' in bt
        is_out = 'o' in bt
        is_in = 'i' in bt
        H_adj = self._bgk_adjust(is_upper)
        pricer = HaugBarrierDualTime( S=self.S, X=self.X, H=H_adj, T_cal=self.T_cal, T_trade=self.T_trade, r=self.r, b=self.b,
                                      sigma=self.sigma, K=self.K )

        hit_barrier = (is_upper and self.S >= H_adj) or (not is_upper and self.S <= H_adj)
        if is_out:
            if hit_barrier:
                return self.K
        elif is_in:
            if hit_barrier:
                return self._vanilla_price(barrier_type)


        price_val = pricer.price(bt)
        if show_detail:
            self._print_detail(barrier_type, H_adj, price_val)

        return price_val

    def _print_detail(self, bt, H_adj, price_val):
        correction_pct = (H_adj / self.H_orig - 1) * 100
        direction = "上移" if 'u' in bt.lower() else "下移"
        print("=" * 55)
        print(f"  离散障碍期权定价明细  [{bt.upper()}]")
        print("=" * 55)
        for k, v in self.time_info.items():
            print(f"  {k:<15}: {v}")
        print(f"  {'现价 S':<15}: {self.S}")
        print(f"  {'执行价 X':<15}: {self.X}")
        print(f"  {'原始障碍 H':<15}: {self.H_orig}")
        print(f"  BGK 修正 ({direction}): H → {H_adj:.4f}  ({correction_pct:+.3f}%)")
        print(f"  β={self.beta},  σ={self.sigma},  dt=1/{self.ann}={self.dt:.6f}")
        print(f"  {'波动率 sigma':<15}: {self.sigma}")
        print(f"  {'无风险利率 r':<15}: {self.r}")
        print(f"  {'持有成本 b':<15}: {self.b}")
        print("-" * 55)
        print(f"  ▶  期权价格: {price_val:.6f}")
        print("=" * 55)


    def continuous_price(self, barrier_type: str) -> float:
        pricer = HaugBarrierDualTime( S=self.S, X=self.X, H=self.H_orig, T_cal=self.T_cal, T_trade=self.T_trade,
                                      r=self.r, b=self.b, sigma=self.sigma, K=self.K )
        bt = barrier_type.lower()
        is_upper = 'u' in bt
        is_out = 'o' in bt

        # 连续障碍判断是否敲出
        if is_upper and self.S >=self.H_orig:
            if is_out:
                return self.K
        if (not is_upper) and (self.S <= self.H_orig):
            if is_out:
                return self.K

        return pricer.price(barrier_type.lower())

    def compare(self, barrier_type: str):
        p_cont = self.continuous_price(barrier_type)
        p_disc = self.discrete_price(barrier_type)
        diff = p_disc - p_cont
        print(f"\n  [{barrier_type.upper()}] 连续 vs 离散障碍对比")
        print(f"  连续障碍价格: {p_cont:.6f}")
        print(f"  离散障碍价格: {p_disc:.6f}")
        print(f"  差值 (离散-连续): {diff:+.6f}  ({diff/p_cont*100:+.3f}%)\n")

if __name__ == "__main__":
    pricer = DiscreteBarrierPricer(
        start_dt = "2026.05.01 14:00:00",
        end_dt   = "2026.05.28 15:00:00",
        S        = 120,
        X        = 105.0,
        H        = 110.0,
        r        = 0.03,
        b        = 0.0,
        sigma    = 0.20,
        K        = 2.0,
    )

    pricer.discrete_price("pdo", show_detail=False)
    pricer.discrete_price("pdi", show_detail=True)

    pricer.compare("cuo")
    pricer.compare("pdi")