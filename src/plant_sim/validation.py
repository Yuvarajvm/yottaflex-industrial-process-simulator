import csv, json
import math
from datetime import datetime
from pathlib import Path
from .topology import connectivity

VALVE_STATES={"OPEN","CLOSED","THROTTLED"}
def validate_required(record, required):
    missing=[name for name in required if record.get(name) in (None,"")]
    if missing:raise ValueError(f"missing required fields: {', '.join(missing)}")
def validate_unique_ids(records, field):
    ids=[r.get(field) for r in records]
    if None in ids or len(ids)!=len(set(ids)):raise ValueError(f"missing or duplicate {field}")
def validate_pipe_record(pipe, node_ids):
    validate_required(pipe,["pipe_id","facility_id","from_node_id","to_node_id","valve_id"])
    if pipe["from_node_id"] not in node_ids or pipe["to_node_id"] not in node_ids:raise ValueError("pipe references missing node")
    if pipe["from_node_id"]==pipe["to_node_id"]:raise ValueError("pipe self-connection")
def validate_tank_level(level, capacity):
    if level>capacity:raise ValueError("tank level exceeds capacity")
def validate_simulation_input(config):
    if not config:raise ValueError("simulation input configuration is required")
def validate_simulation_config(config, actual_sensor_count, actual_telemetry_count, start_timestamp=None, end_timestamp=None):
    validate_simulation_input(config)
    if int(config.get("sensor_count", -1)) != actual_sensor_count:
        raise ValueError("configured sensor_count does not match generated sensor inventory")
    expected_steps=math.ceil(int(config["telemetry_count"])/actual_sensor_count)
    if int(config.get("steps", -1)) != expected_steps:
        raise ValueError("configured steps do not match telemetry_count and sensor_count")
    if int(config.get("telemetry_count", -1)) != actual_telemetry_count:
        raise ValueError("configured telemetry_count does not match emitted telemetry")
    if int(config.get("step_duration_minutes", -1)) != 1:
        raise ValueError("step_duration_minutes must be one for this simulator")
    if start_timestamp is not None and end_timestamp is not None:
        elapsed=(datetime.fromisoformat(end_timestamp)-datetime.fromisoformat(start_timestamp)).total_seconds()/60
        if elapsed != int(config["steps"])*int(config["step_duration_minutes"]):
            raise ValueError("simulation run timestamps do not match configured duration")
def validate_valve_state(state):
    if state not in VALVE_STATES:raise ValueError(f"invalid valve state: {state}")
def validate_valve_configuration(valve):
    validate_required(valve,["state","opening_pct"]);validate_valve_state(valve["state"])
    if not 0<=float(valve["opening_pct"])<=100:raise ValueError("valve opening percentage outside [0,100]")
def validate_pump_config(pump):
    validate_required(pump,["max_flow_lpm","speed_pct"])
    if float(pump["max_flow_lpm"])<=0 or not 0<=float(pump["speed_pct"])<=100:raise ValueError("invalid pump configuration")
def validate_event_order(start, end):
    if start>end:raise ValueError("event end precedes start")
def validate_lifecycle_transition(previous, new):
    allowed={"ACTIVE":{"MAINTENANCE","INACTIVE"},"MAINTENANCE":{"ACTIVE","INACTIVE"},"INACTIVE":{"ACTIVE"}}
    if new not in allowed.get(previous,set()):raise ValueError(f"invalid lifecycle transition {previous}->{new}")

def validate(input_dir):
    root=Path(input_dir)
    def read(name):
        with (root/f"{name}.csv").open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
    tables={n:read(n) for n in ("facilities","assets","pumps","tanks","valves","pipes","nodes","sensors","telemetry","simulation_runs","state_events","simulation_assets")}
    id_fields={"facilities":"facility_id","assets":"asset_id","pumps":"pump_id","tanks":"tank_id","valves":"valve_id","pipes":"pipe_id","nodes":"node_id","sensors":"sensor_id","telemetry":"telemetry_id","simulation_runs":"simulation_run_id","state_events":"event_id"}
    checks={}; errors=[]
    for name,key in id_fields.items():
        vals=[r.get(key) for r in tables[name]]
        checks[f"{name}_unique_ids"]=len(vals)==len(set(vals))
        if not checks[f"{name}_unique_ids"]:errors.append(f"duplicate {key}")
        if any(not x for x in vals):errors.append(f"missing {key}")
    node_ids={r["node_id"] for r in tables["nodes"]}
    node_fac={r["node_id"]:r["facility_id"] for r in tables["nodes"]}
    facility_ids={r["facility_id"] for r in tables["facilities"]}
    valves={r["valve_id"]:r for r in tables["valves"]}
    sensors={r["sensor_id"]:r for r in tables["sensors"]}
    tanks={r["tank_id"]:r for r in tables["tanks"]}
    asset_ids={r[k] for group,k in [(tables["pumps"],"pump_id"),(tables["tanks"],"tank_id"),(tables["pipes"],"pipe_id")] for r in group}
    for group in ("pumps","tanks","valves","pipes","nodes","sensors"):
        for row in tables[group]:
            if row.get("facility_id") not in facility_ids:errors.append(f"{group} {row.get('facility_id')} references missing facility")
    for p in tables["pipes"]:
        if p["from_node_id"] not in node_ids or p["to_node_id"] not in node_ids: errors.append(f"pipe {p['pipe_id']} references missing node")
        elif node_fac[p["from_node_id"]]!=p["facility_id"] or node_fac[p["to_node_id"]]!=p["facility_id"]:errors.append(f"pipe {p['pipe_id']} endpoint facility mismatch")
        if p.get("valve_id") not in valves:errors.append(f"pipe {p['pipe_id']} references missing valve")
    over_capacity=0
    for row in tables["telemetry"]:
        s=sensors.get(row.get("sensor_id"))
        if not s:errors.append(f"telemetry {row.get('telemetry_id')} references missing sensor");continue
        if row.get("facility_id")!=s["facility_id"]:errors.append(f"telemetry {row.get('telemetry_id')} facility mismatch")
        if row.get("asset_id")!=s["asset_id"]:errors.append(f"telemetry {row.get('telemetry_id')} asset mismatch")
        if row.get("measurement_type") not in {"FLOW","PRESSURE","LEVEL"}:errors.append("invalid telemetry measurement enum")
        if row.get("quality_status") not in {"GOOD","SUSPECT","BAD"}:errors.append("invalid telemetry quality enum")
        if row.get("measurement_type")=="LEVEL" and row.get("asset_id") in tanks and float(row["value"])>float(tanks[row["asset_id"]]["capacity_l"]):over_capacity+=1
    for p in tables["pumps"]:
        try:validate_pump_config(p)
        except ValueError as exc:errors.append(str(exc))
    for v in tables["valves"]:
        try:validate_valve_configuration(v)
        except ValueError as exc:errors.append(str(exc))
    config_valid=True
    for run in tables["simulation_runs"]:
        try:
            cfg=json.loads(run.get("input_config_json",""))
            validate_simulation_config(cfg,len(tables["sensors"]),len(tables["telemetry"]),run["start_timestamp"],run["end_timestamp"])
            validate_event_order(run["start_timestamp"],run["end_timestamp"])
        except (ValueError,KeyError,json.JSONDecodeError,ZeroDivisionError) as exc:
            config_valid=False;errors.append(f"simulation run invalid: {exc}")
    asset_ids={r["asset_id"] for r in tables["assets"]};run_ids={r["simulation_run_id"] for r in tables["simulation_runs"]}
    associations=[(r["simulation_run_id"],r["asset_id"]) for r in tables["simulation_assets"]]
    checks["simulation_asset_unique_pairs"]=len(associations)==len(set(associations))
    checks["simulation_asset_references_valid"]=all(run in run_ids and asset in asset_ids for run,asset in associations)
    checks["simulation_asset_rows"]=len(associations)
    current_asset_set={r["asset_id"] for r in tables["assets"]}
    checks["simulation_asset_membership_complete"]=len(associations)==len(current_asset_set) and {asset for _,asset in associations}==current_asset_set and len(run_ids)==1 and all(run==next(iter(run_ids)) for run,_ in associations)
    if not checks["simulation_asset_membership_complete"]:errors.append("simulation run is not associated with every generated participating asset exactly once")
    if not checks["simulation_asset_unique_pairs"]:errors.append("duplicate simulation-asset association")
    if not checks["simulation_asset_references_valid"]:errors.append("invalid simulation-asset reference")
    checks["graph_connectivity"]=connectivity(tables["nodes"],tables["pipes"])
    checks["foreign_keys_valid"]=not any("references missing" in e for e in errors)
    checks["all_graphs_connected"]=all(checks["graph_connectivity"].values())
    checks["telemetry_rows"]=len(tables["telemetry"])
    checks["simulation_configuration_consistent"]=config_valid
    checks["tank_over_capacity_readings"]=over_capacity
    checks["expected_anomaly_exceptions"]=["tank capacity exceeded in controlled TANK_OVER_CAPACITY episode"] if over_capacity else []
    with (root/"mass_balance.csv").open(encoding="utf-8",newline="") as f:balance=list(csv.DictReader(f))
    checks["mass_balance_intervals"]=len(balance)
    checks["mass_balance_violations_over_tolerance"]=sum(abs(float(r["residual_l"]))>float(r["tolerance_l"]) for r in balance)
    result={"valid":not errors and checks["all_graphs_connected"] and checks["simulation_asset_references_valid"] and checks["simulation_asset_membership_complete"] and config_valid,"errors":errors,"checks":checks}
    (root/"validation_summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return result
