def controlled_observations():
    return [
      {"scenario_id":"SCN-LEAK","asset_id":"PIPE-001","flow_imbalance":True,"pressure_drop":True},
      {"scenario_id":"SCN-BLOCK","asset_id":"PIPE-002","downstream_flow_low":True,"upstream_pressure_high":True},
      {"scenario_id":"SCN-PUMP","asset_id":"PUMP-001","pump_flow_below_curve":True},
      {"scenario_id":"SCN-SENSOR","asset_id":"SNS-001","sensor_stuck_or_drifting":True},
      {"scenario_id":"SCN-TANK","asset_id":"TANK-001","level_above_capacity":True},
      {"scenario_id":"SCN-BALANCE","asset_id":"FAC-001","residual_over_tolerance":True},
    ]
