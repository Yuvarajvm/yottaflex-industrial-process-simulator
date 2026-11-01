"""Transparent, steady-state hydraulic approximations (not a solver)."""
def pump_flow(speed_pct: float, max_flow_lpm: float, degradation: float = 1.0) -> float:
    return max(0.0, max_flow_lpm * speed_pct / 100.0 * degradation)

def valve_factor(state: str, opening_pct: float = 100.0) -> float:
    if not 0 <= opening_pct <= 100: raise ValueError("valve opening percentage must be in [0, 100]")
    return {"OPEN": 1.0, "THROTTLED": 0.45, "CLOSED": 0.0}[state] * opening_pct / 100.0

def pipe_pressure_drop(flow_lpm: float, resistance: float) -> float:
    return max(0.0, resistance * flow_lpm * flow_lpm)

def tank_delta_l(inflow_lpm: float, outflow_lpm: float, leakage_lpm: float, minutes: float = 1.0) -> float:
    return (inflow_lpm - outflow_lpm - leakage_lpm) * minutes

def mass_balance_residual(inflow_lpm: float, outflow_lpm: float, leakage_lpm: float, stored_change_l: float, minutes: float = 1.0) -> float:
    return (inflow_lpm - outflow_lpm - leakage_lpm) * minutes - stored_change_l
