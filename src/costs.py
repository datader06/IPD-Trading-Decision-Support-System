"""Transaction-cost and slippage model (Phase A, A8). Pure functions, no hidden defaults.

Costs are percentages of traded value, charged on BOTH legs (entry and exit notional). Slippage is an adverse move of the fill
price, also per side, in % of price. net_R = gross_R - cost_R with
    cost_R = (pct_per_side / 100) * (fill_price + exit_price) / risk_per_share
(shares cancel, so cost_R does not depend on position size).

The exact broker / tax figures are NOT decided yet (user, Phase A). The scenarios below are lumped round-trip assumptions:
  rt0.20 = 0.20 % round trip: the figure used in docs/DECISIONS.md Record B (distal-buffer sweep);
  rt0.10 / rt0.30 = the sensitivity bracket requested by the user.
Itemised fields (brokerage / exchange / taxes) exist so a real fee schedule can replace the lump later; they default to 0.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    name: str
    lump_pct_per_side: float = 0.0      # all-in scenario cost, % of value per side
    brokerage_pct_per_side: float = 0.0
    exchange_pct_per_side: float = 0.0
    taxes_pct_per_side: float = 0.0
    slippage_pct_per_side: float = 0.0

    def pct_per_side(self):
        return (self.lump_pct_per_side + self.brokerage_pct_per_side + self.exchange_pct_per_side
                + self.taxes_pct_per_side + self.slippage_pct_per_side)

    def cost_r(self, fill_price, exit_price, risk):
        """Cost of one round trip in R units."""
        if risk is None or risk <= 0:
            raise ValueError("risk must be > 0")
        return self.pct_per_side() / 100.0 * (float(fill_price) + float(exit_price)) / float(risk)

    def net_r(self, gross_r, fill_price, exit_price, risk):
        return float(gross_r) - self.cost_r(fill_price, exit_price, risk)


def round_trip(name, round_trip_pct, slippage_pct_per_side=0.0):
    """Scenario with a lumped round-trip cost (split equally over the two sides) plus optional slippage per side."""
    return CostModel(name=name, lump_pct_per_side=round_trip_pct / 2.0, slippage_pct_per_side=slippage_pct_per_side)


def scenarios(slippage_pct_per_side=0.0):
    """The Phase A reporting scenarios. Slippage is 0 unless the caller passes a value (none has been agreed)."""
    s = slippage_pct_per_side
    return [round_trip("gross", 0.0, 0.0), round_trip("rt0.10", 0.10, s), round_trip("rt0.20", 0.20, s),
            round_trip("rt0.30", 0.30, s)]
