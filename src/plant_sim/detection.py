"""Rule detector over telemetry and permitted asset configuration. No truth input exists in this API."""
import csv, json, hashlib
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

def _detect_window(input_dir, window_start, window_end):
    root=Path(input_dir)
    with (root/"telemetry.csv").open(encoding="utf-8",newline="") as f: rows=list(csv.DictReader(f))
    with (root/"tanks.csv").open(encoding="utf-8",newline="") as f: tanks={r["tank_id"]:float(r["capacity_l"]) for r in csv.DictReader(f)}
    with (root/"pipes.csv").open(encoding="utf-8",newline="") as f: pipe_fac={r["pipe_id"]:r["facility_id"] for r in csv.DictReader(f)}
    with (root/"pumps.csv").open(encoding="utf-8",newline="") as f: pumps={r["pump_id"]:r for r in csv.DictReader(f)}
    with (root/"simulation_runs.csv").open(encoding="utf-8",newline="") as f: run=next(csv.DictReader(f))["simulation_run_id"]
    values=defaultdict(dict); meta={}
    for r in rows:
        dt=datetime.fromisoformat(r["timestamp"]); minute=dt.hour*60+dt.minute; key=(r["sensor_id"],minute)
        values[key]=float(r["value"]); meta[r["sensor_id"]]=(r["asset_id"],r["measurement_type"],r["facility_id"],r["unit"])
    by_asset=defaultdict(lambda:defaultdict(list))
    for (sid,minute),value in values.items():
        asset,typ,fac,unit=meta[sid];by_asset[asset][(typ,minute)].append((sid,value))
    def series(asset,typ,minute):return [v for _,v in by_asset[asset].get((typ,minute),[])]
    def means(asset,typ,lo,hi):
        vals=[v for m in range(lo,hi) for _,v in by_asset[asset].get((typ,m),[])]
        return sum(vals)/len(vals) if vals else None
    preds=[]
    def add(kind,asset,minute,measurements,rule,explanation,severity="HIGH"):
        run_no=run.rsplit("-",1)[-1]
        episode_start=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=minute)).isoformat()
        observed_at=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=max(minute,obs_end-1))).isoformat()
        emitted_at=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=window_end)).isoformat()
        evidence={**measurements,"episode_start_timestamp":episode_start}
        preds.append({"prediction_id":f"PRED-{run_no}-{minute:06d}-{len(preds)+1:06d}","simulation_run_id":run,"affected_asset_id":asset,"detected_class":kind,"severity":severity,"detection_timestamp":observed_at,"alert_emission_timestamp":emitted_at,"supporting_measurements":json.dumps(evidence,sort_keys=True),"rule_triggered":rule,"explanation":explanation})
    if window_start>=5: base_start,base_end=window_start-5,window_start; obs_start,obs_end=window_start,window_end
    else: base_start,base_end=window_start,window_start+2; obs_start,obs_end=window_start+2,window_end
    for tank,capacity in tanks.items():
        now=max((v for (typ,m),vs in by_asset[tank].items() if typ=="LEVEL" and obs_start<=m<obs_end for _,v in vs),default=0)
        if now>capacity:add("TANK_OVER_CAPACITY",tank,obs_start,{"level_l":now,"capacity_l":capacity},"level > capacity","Measured tank volume exceeds configured capacity","HIGH" if now-capacity>200 else "MEDIUM")
    # Flatline meter signals are classified separately from process faults.
    for asset in pipe_fac:
        sensor_ids=sorted({sid for (typ,m),samples in by_asset[asset].items() if typ=="FLOW" and obs_start<=m<obs_end for sid,_ in samples})
        for sid in sensor_ids:
            samples=[values[(sid,m)] for m in range(obs_start,obs_end) if (sid,m) in values]
            baseline=means(asset,"FLOW",base_start,base_end);during=means(asset,"FLOW",obs_start,obs_end)
            if len(samples)>=2 and len(set(samples))==1 and baseline is not None and during is not None and abs(during-baseline)>max(2.0,baseline*.015):
                add("SENSOR_FAULT",sid,obs_start,{"stuck_value_lpm":samples[0],"asset_flow_before_lpm":baseline,"asset_flow_during_lpm":during},"flatline_with_redundant_disagreement","Sensor stayed fixed while redundant process flow changed","HIGH" if abs(during-baseline)>baseline*.08 else "MEDIUM")
    degraded_facilities=set()
    for pump_id,pump in pumps.items():
        expected=float(pump["max_flow_lpm"])*float(pump["speed_pct"])/100
        measured=[v for m in range(obs_start,obs_end) for _,v in by_asset[pump_id].get(("FLOW",m),[])]
        ratio=(sum(measured)/len(measured)/expected) if measured and expected else None
        if ratio is not None and ratio<.9:
            degraded_facilities.add(pump["facility_id"])
            add("PUMP_DEGRADATION",pump_id,obs_start,{"nominal_expected_lpm":expected,"observed_mean_lpm":sum(measured)/len(measured),"delivery_ratio":ratio,"speed_pct":float(pump["speed_pct"])},"observed_flow_below_pump_curve","Measured pump delivery is below nominal capacity at configured speed","HIGH" if ratio<.65 else "MEDIUM")
    for asset in pipe_fac:
        flow0=means(asset,"FLOW",base_start,base_end);flow1=means(asset,"FLOW",obs_start,obs_end);press0=means(asset,"PRESSURE",base_start,base_end);press1=means(asset,"PRESSURE",obs_start,obs_end)
        if None in (flow0,flow1,press0,press1) or flow0<=0:continue
        drop=(flow0-flow1)/flow0; dp=press1-press0
        facility=pipe_fac[asset]
        if drop>.20 and dp>25:
            add("BLOCKAGE",asset,obs_start,{"flow_before_lpm":flow0,"flow_during_lpm":flow1,"flow_drop_fraction":drop,"pressure_change_kpa":dp},"flow_drop_and_upstream_pressure_rise","Downstream flow fell while upstream pressure rose","HIGH" if drop>.45 or dp>60 else "MEDIUM")
        elif drop>.015 and dp < -10:
            add("LEAK",asset,obs_start,{"flow_before_lpm":flow0,"flow_during_lpm":flow1,"flow_drop_fraction":drop,"pressure_change_kpa":dp},"flow_imbalance_and_pressure_drop","Pipe flow imbalance coincides with pressure reduction","HIGH" if drop>.06 or dp < -25 else "MEDIUM")
        elif flow0-flow1>10 and abs(dp)<10 and facility not in degraded_facilities:
            add("FLOW_CONSERVATION_VIOLATION",facility,obs_start,{"pipe_flow_before_lpm":flow0,"pipe_flow_during_lpm":flow1,"pressure_change_kpa":dp,"residual_lpm":flow0-flow1},"residual_over_tolerance","Unexplained branch flow discrepancy exceeds the configured tolerance","HIGH" if flow0-flow1>35 else "MEDIUM")
    return preds

def detect(input_dir, window_start=None, window_end=None):
    """Scan fixed time windows from observables; no anomaly labels or truth file are read."""
    if window_start is not None:return _detect_window(input_dir,window_start,window_end)
    return [p for start in (5,15) for p in _detect_window(input_dir,start,start+5)]

def write_predictions(input_dir):
    root=Path(input_dir);preds=detect(root)
    fields=["prediction_id","simulation_run_id","affected_asset_id","detected_class","severity","detection_timestamp","alert_emission_timestamp","supporting_measurements","rule_triggered","explanation"]
    with (root/"alarms.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(preds)
    # Refresh deterministic output inventory after prediction CSV is materialized.
    checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.csv")) if p.name!="ground_truth.csv"}
    (root/"checksums.json").write_text(json.dumps(checks,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest_path=root/"manifest.json"
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text());manifest["sha256"]=checks
        manifest["row_counts"]={p.stem:sum(1 for _ in p.open(encoding="utf-8"))-1 for p in root.glob("*.csv")}
        (root/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return preds

def predict(observations):
    """Small pure rule primitive retained for unit tests; accepts signal evidence, never labels."""
    result=[]
    for row in observations:
        if row.get("flatline") and row.get("redundant_disagreement"): result.append("SENSOR_FAULT")
        elif row.get("flow_drop") and row.get("pressure_drop"):result.append("LEAK")
        elif row.get("flow_drop") and row.get("pressure_rise"):result.append("BLOCKAGE")
    return result
