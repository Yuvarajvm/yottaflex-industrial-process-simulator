import csv, hashlib, json, random, time
from pathlib import Path
from .config import Config
from .ids import entity_id, simulation_id
from .physics import pump_flow, pipe_pressure_drop, valve_factor
from .manifest import refresh_manifest

EPOCH = "2026-01-01T00:00:00+00:00"
FACILITIES = ["FAC-001", "FAC-002", "FAC-003"]
ANOMALY_START, ANOMALY_END = 5, 10
SCENARIOS=[
 {"scenario_id":"SCN-LEAK-HIGH","asset_id":"PIPE-001","kind":"LEAK","start":5,"end":10,"severity":"HIGH","loss":20,"pressure_drop":35},
 {"scenario_id":"SCN-BLOCK-HIGH","asset_id":"PIPE-002","kind":"BLOCKAGE","start":5,"end":10,"severity":"HIGH","resistance_factor":6.0,"pressure_rise":80},
 {"scenario_id":"SCN-PUMP-HIGH","asset_id":"PUMP-001","kind":"PUMP_DEGRADATION","start":5,"end":10,"severity":"HIGH","efficiency":0.55},
 {"scenario_id":"SCN-SENSOR-HIGH","asset_id":"SNS-001","kind":"SENSOR_FAULT","start":5,"end":10,"severity":"HIGH"},
 {"scenario_id":"SCN-TANK-HIGH","asset_id":"TANK-001","kind":"TANK_OVER_CAPACITY","start":5,"end":10,"severity":"HIGH","excess_l":500},
 {"scenario_id":"SCN-BALANCE-HIGH","asset_id":"FAC-002","pipe_id":"PIPE-005","kind":"FLOW_CONSERVATION_VIOLATION","start":5,"end":10,"severity":"HIGH","loss":45},
 {"scenario_id":"SCN-LEAK-MILD","asset_id":"PIPE-004","kind":"LEAK","start":15,"end":20,"severity":"MEDIUM","loss":8,"pressure_drop":15},
 {"scenario_id":"SCN-BLOCK-MILD","asset_id":"PIPE-008","kind":"BLOCKAGE","start":15,"end":20,"severity":"MEDIUM","resistance_factor":3.0,"pressure_rise":40},
 {"scenario_id":"SCN-PUMP-MILD","asset_id":"PUMP-008","kind":"PUMP_DEGRADATION","start":15,"end":20,"severity":"MEDIUM","efficiency":0.75},
 {"scenario_id":"SCN-SENSOR-MILD","asset_id":"SNS-007","kind":"SENSOR_FAULT","start":15,"end":20,"severity":"MEDIUM"},
 {"scenario_id":"SCN-TANK-MILD","asset_id":"TANK-008","kind":"TANK_OVER_CAPACITY","start":15,"end":20,"severity":"MEDIUM","excess_l":100},
 {"scenario_id":"SCN-BALANCE-MILD","asset_id":"FAC-003","pipe_id":"PIPE-006","kind":"FLOW_CONSERVATION_VIOLATION","start":15,"end":20,"severity":"MEDIUM","loss":20},
]
OPERATING_MODES={"NORMAL":1.0,"HIGH_DEMAND":1.3,"MAINTENANCE":0.5,"STARTUP":0.7}
PUMP_SPEED_CHANGE={"asset_id":"PUMP-001","start":45,"end":50,"new_speed_pct":100.0}

def operating_mode(minute):
    if 25<=minute<30:return "HIGH_DEMAND"
    if 30<=minute<35:return "MAINTENANCE"
    if 35<=minute<40:return "STARTUP"
    return "NORMAL"

def _write(path, fields, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def generate(config: Config, out_dir: str | Path) -> dict:
    total_started=time.perf_counter()
    if config.steps not in (None,config.actual_steps):
        raise ValueError(f"configured steps={config.steps} does not match required steps={config.actual_steps}")
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); rng=random.Random(config.seed)
    for stale in ("alarms.csv","evaluation_summary.json","performance.json"):
        old=out/stale
        if old.exists():old.unlink()
    facilities=[{"facility_id":entity_id("FAC",i),"name":f"Facility {i:03d}","lifecycle_state":"ACTIVE"} for i in range(1,config.facilities+1)]
    pumps=[{"pump_id":entity_id("PUMP",i),"facility_id":FACILITIES[(i-1)%config.facilities],"max_flow_lpm":round(rng.uniform(500,1200),2),"speed_pct":round(rng.uniform(70,100),2),"lifecycle_state":"ACTIVE"} for i in range(1,config.pumps+1)]
    tanks=[{"tank_id":entity_id("TANK",i),"facility_id":FACILITIES[(i-1)%config.facilities],"capacity_l":round(rng.uniform(30000,70000),2),"initial_level_l":round(rng.uniform(9000,18000),2),"lifecycle_state":"ACTIVE"} for i in range(1,config.tanks+1)]
    valves=[{"valve_id":entity_id("VALVE",i),"facility_id":FACILITIES[(i-1)%config.facilities],"state":"OPEN","opening_pct":100.0,"lifecycle_state":"ACTIVE"} for i in range(1,config.valves+1)]
    valve_by_id={v["valve_id"]:v for v in valves}
    nodes=[]
    for p in pumps:nodes.append({"node_id":f"NODE-{p['pump_id']}","facility_id":p["facility_id"],"asset_type":"PUMP","asset_id":p["pump_id"]})
    for t in tanks:nodes.append({"node_id":f"NODE-{t['tank_id']}","facility_id":t["facility_id"],"asset_type":"TANK","asset_id":t["tank_id"]})
    pipes=[]
    for i in range(1,config.pipes+1):
        fac=FACILITIES[(i-1)%config.facilities]; group=[n for n in nodes if n["facility_id"]==fac]; k=(i-1)//config.facilities
        pipes.append({"pipe_id":entity_id("PIPE",i),"facility_id":fac,"from_node_id":group[k%len(group)]["node_id"],"to_node_id":group[(k+1)%len(group)]["node_id"],"valve_id":entity_id("VALVE",i),"diameter_mm":round(rng.uniform(80,300),2),"resistance":round(rng.uniform(.000001,.00001),8),"lifecycle_state":"ACTIVE"})
    node_degree={n["node_id"]:0 for n in nodes}
    for p in pipes:
        node_degree[p["from_node_id"]]+=1;node_degree[p["to_node_id"]]+=1
    sensors=[]
    for i,p in enumerate(pipes,1):
        for typ in ("FLOW","PRESSURE"):
            sensors.append({"sensor_id":entity_id("SNS",len(sensors)+1),"facility_id":p["facility_id"],"asset_id":p["pipe_id"],"measurement_type":typ,"unit":"L/min" if typ=="FLOW" else "kPa","lifecycle_state":"ACTIVE"})
    # Independent redundant flow pickup supports distinguishing a bad sensor from a real pipe leak.
    sensors.append({"sensor_id":entity_id("SNS",len(sensors)+1),"facility_id":pipes[0]["facility_id"],"asset_id":pipes[0]["pipe_id"],"measurement_type":"FLOW","unit":"L/min","lifecycle_state":"ACTIVE"})
    for t in tanks:sensors.append({"sensor_id":entity_id("SNS",len(sensors)+1),"facility_id":t["facility_id"],"asset_id":t["tank_id"],"measurement_type":"LEVEL","unit":"L","lifecycle_state":"ACTIVE"})
    for p in pumps:sensors.append({"sensor_id":entity_id("SNS",len(sensors)+1),"facility_id":p["facility_id"],"asset_id":p["pump_id"],"measurement_type":"FLOW","unit":"L/min","lifecycle_state":"ACTIVE"})
    sensors.append({"sensor_id":entity_id("SNS",len(sensors)+1),"facility_id":pipes[3]["facility_id"],"asset_id":pipes[3]["pipe_id"],"measurement_type":"FLOW","unit":"L/min","lifecycle_state":"ACTIVE"})
    for name,rows in [("facilities",facilities),("pumps",pumps),("tanks",tanks),("valves",valves),("pipes",pipes),("nodes",nodes),("sensors",sensors)]:_write(out/f"{name}.csv",list(rows[0]),rows)
    assets=[]
    for table,ident,kind in [(facilities,"facility_id","FACILITY"),(pumps,"pump_id","PUMP"),(tanks,"tank_id","TANK"),(valves,"valve_id","VALVE"),(pipes,"pipe_id","PIPE"),(sensors,"sensor_id","SENSOR")]:
        assets.extend({"asset_id":r[ident],"asset_type":kind,"facility_id":r["facility_id"]} for r in table)
    _write(out/"assets.csv",["asset_id","asset_type","facility_id"],assets)
    # Sensor inventory is intentionally independent of telemetry volume: the profile changes only simulated duration.
    # Each timestep is one minute. All sensor values are functions of current physical state.
    run=simulation_id(config.run_number); steps=config.actual_steps
    speed_change=PUMP_SPEED_CHANGE if steps>=PUMP_SPEED_CHANGE["end"] else None
    pump_by_fac={f:[p for p in pumps if p["facility_id"]==f] for f in FACILITIES[:config.facilities]}
    tank_by_fac={f:[t for t in tanks if t["facility_id"]==f] for f in FACILITIES[:config.facilities]}
    pipe_by_id={p["pipe_id"]:p for p in pipes}; tank_state={t["tank_id"]:float(t["initial_level_l"]) for t in tanks}
    normal_reference={}
    telemetry_fields=["telemetry_id","simulation_run_id","sensor_id","facility_id","asset_id","timestamp","measurement_type","value","unit","quality_status"]
    simulation_started=time.perf_counter()
    scenarios=[s for s in SCENARIOS if s["end"]<=steps] if config.scenario=="all" else []
    truth=[{"simulation_run_id":run,"scenario_id":s["scenario_id"],"affected_asset_id":s["asset_id"],"anomaly_type":s["kind"],"start_timestamp":f"2026-01-01T00:{s['start']:02d}:00+00:00","end_timestamp":f"2026-01-01T00:{s['end']:02d}:00+00:00","expected_class":s["kind"],"expected_decision":s["kind"],"severity":s["severity"],"event_refs":json.dumps([f"EVT-{config.run_number:06d}-{i:06d}",f"EVT-{config.run_number:06d}-{i+len(scenarios):06d}"])} for i,s in enumerate(scenarios,1)]
    with (out/"telemetry.csv").open("w",newline="",encoding="utf-8") as f, (out/"mass_balance.csv").open("w",newline="",encoding="utf-8") as mf:
        w=csv.DictWriter(f,fieldnames=telemetry_fields);w.writeheader(); emitted=0
        mw=csv.DictWriter(mf,fieldnames=["simulation_run_id","facility_id","timestamp","inflow_lpm","outflow_lpm","storage_change_l","residual_l","tolerance_l"]);mw.writeheader()
        for minute in range(steps):
            active_specs=[s for s in scenarios if s["start"]<=minute<s["end"]]
            active=bool(active_specs)
            fac_pump_flow={}; fac_tank_delta={}; fac_leak={}; pump_outputs={}; nominal_flow={};fac_outflow={};fac_residual={};pipe_flows={}
            for fac,ps in pump_by_fac.items():
                q=0.0;nominal=0.0
                for p in ps:
                    pump_fault=next((s for s in active_specs if s["kind"]=="PUMP_DEGRADATION" and s["asset_id"]==p["pump_id"]),None)
                    deg=float(pump_fault["efficiency"]) if pump_fault else 1.0
                    speed=float(p["speed_pct"])
                    if speed_change and p["pump_id"]==speed_change["asset_id"] and speed_change["start"]<=minute<speed_change["end"]:
                        speed=float(PUMP_SPEED_CHANGE["new_speed_pct"])
                    pump_outputs[p["pump_id"]]=pump_flow(speed,float(p["max_flow_lpm"]),deg)
                    q+=pump_outputs[p["pump_id"]]
                    nominal+=pump_flow(float(p["speed_pct"]),float(p["max_flow_lpm"]))
                fac_pump_flow[fac]=q
                nominal_flow[fac]=nominal
                fac_pipes=[x for x in pipes if x["facility_id"]==fac]
                mean_r=sum(float(p["resistance"]) for p in fac_pipes)/max(1,len(fac_pipes))
                raw_weights={}
                for p in fac_pipes:
                    block=next((s for s in active_specs if s["kind"]=="BLOCKAGE" and s["asset_id"]==p["pipe_id"]),None)
                    conductance=(float(p["diameter_mm"])/150.0)**2*(mean_r/float(p["resistance"]))
                    network_factor=1.0/(1.0+0.08*node_degree[p["from_node_id"]])
                    resistance_factor=float(block["resistance_factor"]) if block else 1.0
                    valve=valve_by_id[p["valve_id"]]
                    raw_weights[p["pipe_id"]]=conductance*network_factor*valve_factor(valve["state"],float(valve["opening_pct"]))/resistance_factor
                weight_sum=sum(raw_weights.values()) or 1.0
                for p in fac_pipes:pipe_flows[p["pipe_id"]]=q*raw_weights[p["pipe_id"]]/weight_sum
                # Restriction withholds the share this branch would carry at its baseline pipe conductance.
                normal_weights={p["pipe_id"]:(float(p["diameter_mm"])/150.0)**2*(mean_r/float(p["resistance"]))/(1.0+0.08*node_degree[p["from_node_id"]]) for p in fac_pipes}
                normal_sum=sum(normal_weights.values()) or 1.0
                blocked_reduction=sum(nominal*normal_weights[s["asset_id"]]/normal_sum*(1-1/float(s["resistance_factor"])) for s in active_specs if s["kind"]=="BLOCKAGE" and pipe_by_id[s["asset_id"]]["facility_id"]==fac)
                fac_outflow[fac]=nominal*OPERATING_MODES[operating_mode(minute)]-blocked_reduction
                known_loss=sum(float(s.get("loss",0)) for s in active_specs if s["kind"] in {"LEAK","FLOW_CONSERVATION_VIOLATION"} and (pipe_by_id.get(s.get("pipe_id",s["asset_id"]),{}).get("facility_id")==fac))
                # Volume follows actual inflow less modeled outflow and known losses.
                fac_tank_delta[fac]=q-fac_outflow[fac]-known_loss
                fac_leak[fac]=known_loss
                fac_residual[fac]=q-fac_outflow[fac]-fac_tank_delta[fac]
            # Equal steady withdrawal makes the normal baseline conserve volume. Fault injections perturb only the named process.
            for fac,ts in tank_by_fac.items():
                delta=fac_tank_delta[fac]; per=delta/max(1,len(ts))
                for t in ts:
                    before=tank_state[t["tank_id"]]; after=before+per
                    tank_fault=next((s for s in active_specs if s["kind"]=="TANK_OVER_CAPACITY" and s["asset_id"]==t["tank_id"]),None)
                    if tank_fault:after=float(t["capacity_l"])+float(tank_fault["excess_l"])
                    elif any(s["kind"]=="TANK_OVER_CAPACITY" and s["asset_id"]==t["tank_id"] and minute>=s["end"] for s in scenarios):after=float(t["initial_level_l"])
                    tank_state[t["tank_id"]]=after
            timestamp=f"2026-01-01T{minute//60:02d}:{minute%60:02d}:00+00:00"
            for fac in pump_by_fac:
                mw.writerow({"simulation_run_id":run,"facility_id":fac,"timestamp":timestamp,"inflow_lpm":round(fac_pump_flow[fac],3),"outflow_lpm":round(fac_outflow[fac],3),"storage_change_l":round(fac_tank_delta[fac],3),"residual_l":round(fac_residual[fac],3),"tolerance_l":10.0})
            for s in sensors:
                if emitted>=config.telemetry_count:break
                typ=s["measurement_type"]; asset=s["asset_id"]; fac=s["facility_id"]; quality="GOOD"
                if typ=="LEVEL":
                    value=tank_state[asset]
                elif asset in pump_outputs:
                    value=pump_outputs[asset]
                elif asset in pipe_by_id:
                    p=pipe_by_id[asset]; q=pipe_flows.get(asset,0.0)
                    blockage=next((x for x in active_specs if x["kind"]=="BLOCKAGE" and x["asset_id"]==asset),None)
                    effective_resistance=float(p["resistance"])*(150.0/float(p["diameter_mm"]))**4*(float(blockage["resistance_factor"]) if blockage else 1.0)
                    pressure=220.0+min(180.0,pipe_pressure_drop(q,effective_resistance))
                    for scenario in active_specs:
                        if scenario["kind"]=="LEAK" and asset==scenario["asset_id"]:q=max(0,q-float(scenario["loss"]));pressure=max(0,pressure-float(scenario["pressure_drop"]))
                        elif scenario["kind"]=="BLOCKAGE" and asset==scenario["asset_id"]:pressure+=float(scenario["pressure_rise"])
                        elif scenario["kind"]=="FLOW_CONSERVATION_VIOLATION" and asset==scenario["pipe_id"]:q=max(0,q-float(scenario["loss"]))
                    value=q if typ=="FLOW" else pressure
                    sensor_fault=next((x for x in active_specs if x["kind"]=="SENSOR_FAULT" and x["asset_id"]==s["sensor_id"]),None)
                    if typ=="FLOW" and sensor_fault:
                        value=normal_reference.get(s["sensor_id"],value);quality="SUSPECT"
                    elif minute==0:normal_reference[s["sensor_id"]]=value
                elif typ=="PRESSURE":value=220.0
                else:value=0.0
                # Measurement noise is seeded; a stuck sensor freezes the prior noisy measurement.
                sigma=max(0.15,abs(float(value))*0.0015) if typ=="FLOW" else (0.25 if typ=="PRESSURE" else 0.5)
                measured=float(value)+rng.gauss(0.0,sigma)
                sensor_fault=next((x for x in active_specs if x["kind"]=="SENSOR_FAULT" and x["asset_id"]==s["sensor_id"]),None)
                if typ=="FLOW" and sensor_fault:
                    measured=normal_reference.get(s["sensor_id"],measured);quality="SUSPECT"
                elif minute==0:normal_reference[s["sensor_id"]]=measured
                row={"telemetry_id":f"TEL-{config.run_number:06d}-{emitted+1:09d}","simulation_run_id":run,"sensor_id":s["sensor_id"],"facility_id":fac,"asset_id":asset,"timestamp":timestamp,"measurement_type":typ,"value":round(measured,3),"unit":s["unit"],"quality_status":quality}
                w.writerow(row);emitted+=1
    simulation_seconds=time.perf_counter()-simulation_started
    modes=[{"mode_id":f"MODE-{i:02d}","name":n,"demand_factor":v} for i,(n,v) in enumerate(OPERATING_MODES.items(),1)]
    _write(out/"operating_modes.csv",["mode_id","name","demand_factor"],modes)
    end_min=max(1,steps); end=f"2026-01-01T{end_min//60:02d}:{end_min%60:02d}:00+00:00"
    run_config={**config.__dict__,"steps":steps,"step_duration_minutes":1,"sensor_count":len(sensors),"participating_asset_count":len(assets),"pump_speed_change":speed_change,"master_snapshot":{"facilities":facilities,"assets":assets,"pumps":pumps,"tanks":tanks,"pipes":pipes}}
    _write(out/"simulation_runs.csv",["simulation_run_id","seed","profile","status","start_timestamp","end_timestamp","input_config_json"],[{"simulation_run_id":run,"seed":config.seed,"profile":config.profile,"status":"COMPLETED","start_timestamp":EPOCH,"end_timestamp":end,"input_config_json":json.dumps(run_config,sort_keys=True)}])
    events=[]
    for i,s in enumerate(scenarios,1):
        asset=s["asset_id"];kind=s["kind"]
        if kind=="LEAK":before,after,reason="loss_lpm=0",f"loss_lpm={s['loss']}","injected leak and recovery"
        elif kind=="BLOCKAGE":before,after,reason="resistance_factor=1.0",f"resistance_factor={s['resistance_factor']}","increased pipe resistance and recovery"
        elif kind=="PUMP_DEGRADATION":before,after,reason="efficiency=1.0",f"efficiency={s['efficiency']}","pump degradation and recovery"
        elif kind=="SENSOR_FAULT":before,after,reason="signal=LIVE","signal=STUCK","sensor fault and recovery"
        elif kind=="TANK_OVER_CAPACITY":before,after,reason="level=within_capacity",f"level=capacity_plus_{s['excess_l']}L","over-capacity episode and recovery"
        else:before,after,reason="branch_loss_lpm=0",f"branch_loss_lpm={s['loss']}","flow discrepancy and recovery"
        if kind=="SENSOR_FAULT":asset=s["asset_id"]
        events.append({"event_id":f"EVT-{config.run_number:06d}-{i:06d}","simulation_run_id":run,"asset_id":asset,"previous_state":before,"new_state":after,"effective_timestamp":f"2026-01-01T00:{s['start']:02d}:00+00:00","reason":reason})
        events.append({"event_id":f"EVT-{config.run_number:06d}-{i+len(scenarios):06d}","simulation_run_id":run,"asset_id":asset,"previous_state":after,"new_state":before,"effective_timestamp":f"2026-01-01T00:{s['end']:02d}:00+00:00","reason":f"end {kind} episode and restore baseline"})
    mode_changes=[(25,"NORMAL","HIGH_DEMAND"),(30,"HIGH_DEMAND","MAINTENANCE"),(35,"MAINTENANCE","STARTUP"),(40,"STARTUP","NORMAL")]
    event_no=len(events)+1
    for effective,previous,new in mode_changes:
        if effective>=steps:continue
        for fac in FACILITIES[:config.facilities]:
            events.append({"event_id":f"EVT-{config.run_number:06d}-{event_no:06d}","simulation_run_id":run,"asset_id":fac,"previous_state":previous,"new_state":new,"effective_timestamp":f"2026-01-01T00:{effective:02d}:00+00:00","reason":f"facility demand mode changed to {new}"});event_no+=1
    if speed_change:
        speed_pump=next(p for p in pumps if p["pump_id"]==speed_change["asset_id"])
        speed_transitions=[(speed_change["start"],float(speed_pump["speed_pct"]),float(speed_change["new_speed_pct"]),"scheduled pump speed increase"),(speed_change["end"],float(speed_change["new_speed_pct"]),float(speed_pump["speed_pct"]),"restore configured pump speed")]
        for effective,previous,new,reason in speed_transitions:
            events.append({"event_id":f"EVT-{config.run_number:06d}-{event_no:06d}","simulation_run_id":run,"asset_id":speed_pump["pump_id"],"previous_state":f"speed_pct={previous}","new_state":f"speed_pct={new}","effective_timestamp":f"2026-01-01T00:{effective:02d}:00+00:00","reason":reason});event_no+=1
    _write(out/"simulation_assets.csv",["simulation_run_id","asset_id"],[{"simulation_run_id":run,"asset_id":a["asset_id"]} for a in assets])
    _write(out/"state_events.csv",["event_id","simulation_run_id","asset_id","previous_state","new_state","effective_timestamp","reason"],events)
    _write(out/"ground_truth.csv",["simulation_run_id","scenario_id","affected_asset_id","anomaly_type","start_timestamp","end_timestamp","expected_class","expected_decision","severity","event_refs"],truth)
    checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.csv")) if p.name!="ground_truth.csv"}
    (out/"checksums.json").write_text(json.dumps(checks,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    rows={p.stem:sum(1 for _ in p.open(encoding="utf-8"))-1 for p in out.glob("*.csv")}
    manifest={"generator_version":"2.0.0","seed":config.seed,"parameters":config.__dict__,"row_counts":rows,"sha256":checks,"ground_truth_sha256":hashlib.sha256((out/"ground_truth.csv").read_bytes()).hexdigest()}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (out/"performance.json").write_text(json.dumps({"simulation_seconds":simulation_seconds,"generation_total_seconds":time.perf_counter()-total_started,"telemetry_count":emitted,"simulation_telemetry_per_second":emitted/simulation_seconds if simulation_seconds else None},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    refresh_manifest(out,preserve_declared=False,include_database=False)
    return manifest
