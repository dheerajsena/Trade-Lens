from dataclasses import dataclass
from typing import Dict, List
from db import sum_open_capital, get_settings

@dataclass
class RiskAlert:
    level: str
    message: str

def _risk_pct(qty:int, buy:float, sl:float, capital_pool:float)->float:
    if buy<=0 or qty<=0 or sl<=0 or capital_pool<=0: return 0.0
    loss_per_share = max(0.0, buy - sl)
    return (loss_per_share * qty / capital_pool) * 100.0

def risk_nudges(user_id:int, trade:Dict, open_trades:List[Dict])->List[RiskAlert]:
    s = get_settings(user_id)
    pool = float(s.get("capital_pool") or 0.0)
    max_risk = float(s.get("max_risk_per_trade_pct") or 1.5)
    max_open = int(s.get("max_open_trades") or 3)
    alerts: List[RiskAlert] = []

    basis_sl = trade.get("sl1") or trade.get("sl2") or 0
    rp = _risk_pct(trade.get("qty",0), trade.get("buy_price",0), basis_sl, pool)
    if rp > max_risk:
        alerts.append(RiskAlert("warn", f"Risk {rp:.2f}% exceeds rule of {max_risk:.1f}% per trade."))

    open_cap = sum_open_capital(user_id)
    remaining = max(0.0, pool - open_cap - float(trade.get("capital") or 0.0))
    alerts.append(RiskAlert("info", f"Remaining deployable capital after this trade: ₹{remaining:,.0f}"))
    if len(open_trades) >= max_open:
        alerts.append(RiskAlert("warn", f"Max open trades ({max_open}) reached."))

    return alerts
