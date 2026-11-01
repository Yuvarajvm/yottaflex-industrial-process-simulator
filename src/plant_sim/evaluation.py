import csv, json
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from .detection import write_predictions, detect


def _prf(tp, fp, fn):
    precision=tp/(tp+fp) if tp+fp else None
    recall=tp/(tp+fn) if tp+fn else None
    f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
    return precision,recall,f1


def evaluate(input_dir, run_id=None):
    root=Path(input_dir)
    with (root/"simulation_runs.csv").open(encoding="utf-8",newline="") as f:
        runs=list(csv.DictReader(f))
    run_ids={r["simulation_run_id"] for r in runs}
    if run_id is None:
        if len(run_ids)!=1:raise ValueError("evaluation input must contain exactly one selected simulation run")
        run_id=next(iter(run_ids))
    elif run_id not in run_ids:
        raise ValueError(f"simulation run {run_id!r} is not present in evaluation input")
    selected_run=next(r for r in runs if r["simulation_run_id"]==run_id)
    duration_minutes=(datetime.fromisoformat(selected_run["end_timestamp"])-datetime.fromisoformat(selected_run["start_timestamp"])).total_seconds()/60
    # Detection on all positive and normal control windows completes before truth is read.
    detection_started=time.perf_counter()
    control_intervals=[(lo,hi) for lo,hi in [(0,5),(25,30),(30,35),(35,40)] if hi<=duration_minutes]
    normal_predictions=[(lo,hi,p) for lo,hi in control_intervals for p in detect(root,lo,hi)]
    predictions=[p for p in write_predictions(root) if p["simulation_run_id"]==run_id]
    detection_seconds=time.perf_counter()-detection_started
    with (root/"ground_truth.csv").open(encoding="utf-8",newline="") as f:
        truth_reader=csv.DictReader(f)
        truth_rows=list(truth_reader)
        truth=[r for r in truth_rows if r.get("simulation_run_id",run_id)==run_id]
    def elapsed_minute(value):
        stamp=datetime.fromisoformat(value)
        return stamp.hour*60+stamp.minute
    control_truth_overlaps=[]
    for label in truth:
        start=elapsed_minute(label["start_timestamp"]);end=elapsed_minute(label["end_timestamp"])
        for lo,hi in control_intervals:
            if max(lo,start)<min(hi,end):
                control_truth_overlaps.append({"scenario_id":label["scenario_id"],"control_start":lo,"control_end_exclusive":hi})
    if control_truth_overlaps:
        raise ValueError(f"normal control windows overlap injected episodes: {control_truth_overlaps}")

    # Greedy one-to-one event matching. Every alarm is consumed once; duplicates
    # and alarms without a matching episode remain false positives.
    unmatched=set(range(len(truth)))
    matches=[];false_alarm_predictions=[]
    for prediction in predictions:
        support=json.loads(prediction["supporting_measurements"])
        key=(prediction["affected_asset_id"],prediction["detected_class"],support.get("episode_start_timestamp"))
        candidate=next((i for i in sorted(unmatched) if (truth[i]["affected_asset_id"],truth[i]["expected_class"],truth[i]["start_timestamp"])==key),None)
        if candidate is None:false_alarm_predictions.append(prediction)
        else:unmatched.remove(candidate);matches.append((candidate,prediction))
    tp=len(matches);event_fp=len(false_alarm_predictions);fn=len(unmatched)
    precision,recall,f1=_prf(tp,event_fp,fn)
    types=sorted({r["expected_class"] for r in truth}|{p["detected_class"] for p in predictions})
    per_type={}
    for kind in types:
        type_tp=sum(1 for i,p in matches if truth[i]["expected_class"]==kind)
        type_fp=sum(1 for p in false_alarm_predictions if p["detected_class"]==kind)
        type_fn=sum(1 for i in unmatched if truth[i]["expected_class"]==kind)
        p,r,f=_prf(type_tp,type_fp,type_fn)
        per_type[kind]={"TP":type_tp,"FP":type_fp,"FN":type_fn,"precision":p,"recall":r,"f1":f}

    with (root/"assets.csv").open(encoding="utf-8",newline="") as f:
        asset_facility={r["asset_id"]:r["facility_id"] for r in csv.DictReader(f)}
    with (root/"facilities.csv").open(encoding="utf-8",newline="") as f:
        facilities={r["facility_id"] for r in csv.DictReader(f)}
    normal_units={(facility,lo,hi) for facility in facilities for lo,hi in control_intervals}
    alarmed_units=set();normal_false_alarms=[]
    for lo,hi,prediction in normal_predictions:
        facility=asset_facility.get(prediction["affected_asset_id"],prediction["affected_asset_id"])
        normal_false_alarms.append(prediction)
        alarmed_units.add((facility,lo,hi))
    normal_windows=len(normal_units);windows_with_alarms=len(alarmed_units & normal_units)
    normal_metrics={
        "normal_windows":normal_windows,
        "windows_with_one_or_more_false_alarms":windows_with_alarms,
        "false_alarm_window_rate":windows_with_alarms/normal_windows if normal_windows else None,
        "total_false_alarms":len(normal_false_alarms),
        "false_alarms_by_class":dict(Counter(p["detected_class"] for p in normal_false_alarms)),
        "control_intervals_minutes":[{"start":lo,"end_exclusive":hi} for lo,hi in control_intervals],
    }
    latencies=[];per_episode=[]
    for truth_index,prediction in matches:
        row=truth[truth_index]
        start=datetime.fromisoformat(row["start_timestamp"])
        last=(datetime.fromisoformat(prediction["detection_timestamp"])-start).total_seconds()/60
        emitted=(datetime.fromisoformat(prediction["alert_emission_timestamp"])-start).total_seconds()/60
        latencies.append((last,emitted))
        per_episode.append({"scenario_id":row["scenario_id"],"affected_asset_id":row["affected_asset_id"],"expected_class":row["expected_class"],"start_timestamp":row["start_timestamp"],"detection_timestamp":prediction["detection_timestamp"],"alert_emission_timestamp":prediction["alert_emission_timestamp"],"last_sample_latency_minutes":last,"alert_emission_latency_minutes":emitted})
    latency_report={
        "last_sample_detection_latency_minutes":{"mean":sum(x[0] for x in latencies)/len(latencies) if latencies else None,"observed_episodes":len(latencies)},
        "operational_alert_emission_latency_minutes":{"mean":sum(x[1] for x in latencies)/len(latencies) if latencies else None,"observed_episodes":len(latencies)},
        "per_episode":per_episode,
        "timestamp_semantics":"Last-sample latency uses the timestamp of the final reading in the half-open observation window. Alert-emission latency uses the exclusive window-close timestamp.",
    }
    result={
        "simulation_run_id":run_id,
        "event_evaluation_unit":"One ground-truth episode identified by affected asset, expected class and start timestamp; each alarm can match at most one episode.",
        "event_metrics":{"ground_truth_episodes":len(truth),"TP":tp,"FP":event_fp,"FN":fn,"precision":precision,"recall":recall,"f1":f1,"per_anomaly_type":per_type},
        "normal_window_false_alarm_metrics":normal_metrics,
        "normal_control_injection_overlaps":control_truth_overlaps,
        "latency":latency_report,
        "detected_alarms":len(predictions),
        "unmatched_alarm_count":event_fp,
        "duplicate_episode_alarm_count":max(0,len(predictions)-len({(p["affected_asset_id"],p["detected_class"],json.loads(p["supporting_measurements"]).get("episode_start_timestamp")) for p in predictions})),
        "mass_balance_violation_alarm_count":sum(1 for p in predictions if p["detected_class"]=="FLOW_CONSERVATION_VIOLATION"),
        "alarm_counts_by_severity":dict(Counter(p["severity"] for p in predictions)),
        "ground_truth_loaded_after_predictions":True,
    }
    (root/"evaluation_summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    perf_path=root/"performance.json";perf=json.loads(perf_path.read_text()) if perf_path.exists() else {}
    perf["detection_seconds"]=detection_seconds;perf["detected_alarm_count"]=len(predictions)
    perf_path.write_text(json.dumps(perf,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    from .manifest import refresh_manifest
    refresh_manifest(root)
    return result
