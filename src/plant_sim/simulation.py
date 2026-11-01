from .physics import pump_flow, tank_delta_l, mass_balance_residual

def simulate_interval(max_flow_lpm, speed_pct, demand_lpm, level_l, capacity_l, leakage_lpm=0.0, minutes=1.0):
    produced=pump_flow(speed_pct,max_flow_lpm)
    out=min(produced,demand_lpm)
    change=tank_delta_l(produced,out,leakage_lpm,minutes)
    level_after=level_l+change
    residual=mass_balance_residual(produced,out,leakage_lpm,change,minutes)
    return {"pump_output_lpm":produced,"outflow_lpm":out,"tank_level_l":level_after,"tank_capacity_l":capacity_l,"mass_balance_residual_l":residual}
