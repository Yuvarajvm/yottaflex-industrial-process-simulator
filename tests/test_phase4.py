import csv, json, sqlite3, hashlib
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import pytest

from plant_sim.config import Config
from plant_sim.generator import generate
from plant_sim.detection import detect
import plant_sim.evaluation as evaluation_module
from plant_sim.database import create_database, export_run_snapshot
from plant_sim.manifest import refresh_manifest, verify_manifest
from plant_sim.validation import validate_simulation_config


def _read(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _ready_db(root, telemetry_count=7000):
    generate(Config.for_profile("starter", telemetry_count=telemetry_count), root)
    evaluation_module.evaluate(root)
    return create_database(root)


def test_duplicate_alarm_is_one_true_positive_plus_one_false_positive(tmp_path, monkeypatch):
    generate(Config.for_profile("starter"), tmp_path)
    predictions=detect(tmp_path)
    duplicate=dict(predictions[0]);duplicate["prediction_id"]="PRED-DUPLICATE"
    monkeypatch.setattr(evaluation_module,"write_predictions",lambda _root: predictions+[duplicate])
    monkeypatch.setattr(evaluation_module,"detect",lambda *_args: [])
    result=evaluation_module.evaluate(tmp_path)
    assert (result["event_metrics"]["TP"],result["event_metrics"]["FP"],result["event_metrics"]["FN"])==(12,1,0)
    assert result["duplicate_episode_alarm_count"]==1


def test_normal_false_alarm_metrics_count_windows_and_every_alarm(tmp_path, monkeypatch):
    generate(Config.for_profile("starter"), tmp_path)
    predictions=detect(tmp_path)
    def controls(_root,lo,hi):
        if (lo,hi)==(25,30):return [dict(predictions[0]),dict(predictions[1])]
        if (lo,hi)==(30,35):return [dict(predictions[2])]
        return []
    monkeypatch.setattr(evaluation_module,"detect",controls)
    result=evaluation_module.evaluate(tmp_path)
    metrics=result["normal_window_false_alarm_metrics"]
    assert metrics["normal_windows"]==12
    assert metrics["windows_with_one_or_more_false_alarms"]==2
    assert metrics["false_alarm_window_rate"]==pytest.approx(2/12)
    assert metrics["total_false_alarms"]==3


def test_unmatched_alarm_is_false_positive(tmp_path, monkeypatch):
    generate(Config.for_profile("starter"), tmp_path)
    predictions=detect(tmp_path); stray=dict(predictions[0])
    stray.update(prediction_id="PRED-STRAY",affected_asset_id="PIPE-002")
    monkeypatch.setattr(evaluation_module,"write_predictions",lambda _root: predictions+[stray])
    monkeypatch.setattr(evaluation_module,"detect",lambda *_args: [])
    result=evaluation_module.evaluate(tmp_path)
    assert result["event_metrics"]["FP"]==1 and result["event_metrics"]["TP"]==12


def test_missed_episode_is_false_negative(tmp_path, monkeypatch):
    generate(Config.for_profile("starter"), tmp_path)
    predictions=detect(tmp_path)
    monkeypatch.setattr(evaluation_module,"write_predictions",lambda _root: predictions[1:])
    monkeypatch.setattr(evaluation_module,"detect",lambda *_args: [])
    result=evaluation_module.evaluate(tmp_path)
    assert result["event_metrics"]["TP"]==11 and result["event_metrics"]["FN"]==1


def test_both_latency_conventions_are_reported(tmp_path):
    generate(Config.for_profile("starter"), tmp_path)
    result=evaluation_module.evaluate(tmp_path)
    assert result["latency"]["last_sample_detection_latency_minutes"]["mean"]==4.0
    assert result["latency"]["operational_alert_emission_latency_minutes"]["mean"]==5.0
    assert all(r["alert_emission_timestamp"]>r["detection_timestamp"] for r in result["latency"]["per_episode"])


def test_evaluation_rejects_control_window_with_injected_episode(tmp_path):
    generate(Config.for_profile("starter"),tmp_path)
    rows=_read(tmp_path/"ground_truth.csv")
    rows[0]["start_timestamp"]="2026-01-01T00:25:00+00:00"
    rows[0]["end_timestamp"]="2026-01-01T00:26:00+00:00"
    with (tmp_path/"ground_truth.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match="overlap injected episodes"):
        evaluation_module.evaluate(tmp_path)


def test_database_rejects_invalid_telemetry_foreign_key(tmp_path):
    db=_ready_db(tmp_path);con=sqlite3.connect(db);con.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO telemetry VALUES(?,?,?,?,?,?,?,?,?,?)",("BAD-TEL","SIM-2026-000001","SNS-MISSING","FAC-001","PIPE-001","2026-01-01T00:00:00+00:00","FLOW",1.0,"L/min","GOOD"))
    assert con.execute("SELECT count(*) FROM telemetry WHERE telemetry_id='BAD-TEL'").fetchone()[0]==0
    con.close()


def test_database_rejects_sensor_asset_mismatch(tmp_path):
    db=_ready_db(tmp_path);con=sqlite3.connect(db);con.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO telemetry VALUES(?,?,?,?,?,?,?,?,?,?)",("BAD-MAP","SIM-2026-000001","SNS-001","FAC-001","PIPE-002","2026-01-01T00:00:00+00:00","FLOW",1.0,"L/min","GOOD"))
    assert con.execute("SELECT count(*) FROM telemetry WHERE telemetry_id='BAD-MAP'").fetchone()[0]==0
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE sensor SET asset_id='TANK-001',measurement_type='PRESSURE',unit='kPa' WHERE sensor_id='SNS-001'")
    con.close()


def test_database_rejects_cross_facility_pipe_endpoints(tmp_path):
    db=_ready_db(tmp_path);con=sqlite3.connect(db);con.execute("PRAGMA foreign_keys=ON")
    other=con.execute("SELECT node_id FROM topology_node WHERE facility_id='FAC-002' LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE pipe SET from_node_id=? WHERE pipe_id='PIPE-001'",(other,))
    assert con.execute("SELECT facility_id FROM topology_node WHERE node_id=(SELECT from_node_id FROM pipe WHERE pipe_id='PIPE-001')").fetchone()[0]=="FAC-001"
    con.close()


def test_entity_ids_and_state_event_history_are_immutable(tmp_path):
    db=_ready_db(tmp_path);con=sqlite3.connect(db);con.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):con.execute("UPDATE asset SET asset_id='PIPE-XXX' WHERE asset_id='PIPE-001'")
    before=con.execute("SELECT * FROM state_event LIMIT 1").fetchone()
    with pytest.raises(sqlite3.IntegrityError):con.execute("UPDATE state_event SET reason='edited' WHERE event_id=?",(before[0],))
    with pytest.raises(sqlite3.IntegrityError):con.execute("DELETE FROM state_event WHERE event_id=?",(before[0],))
    assert con.execute("SELECT * FROM state_event WHERE event_id=?",(before[0],)).fetchone()==before
    con.close()


def test_simulation_duration_configuration_must_match_emitted_count():
    cfg=Config.for_profile("full")
    assert cfg.steps==cfg.actual_steps==582
    bad={"sensor_count":172,"telemetry_count":100000,"steps":20,"step_duration_minutes":1}
    with pytest.raises(ValueError,match="steps"):
        validate_simulation_config(bad,172,100000)
    with pytest.raises(ValueError,match="steps"):
        generate(replace(cfg,steps=20),Path("unused-output"))


def test_pump_speed_change_is_simulated_and_event_recorded(tmp_path):
    generate(Config.for_profile("starter",telemetry_count=20000),tmp_path)
    events=[e for e in _read(tmp_path/"state_events.csv") if e["asset_id"]=="PUMP-001" and "speed_pct=" in e["new_state"]]
    assert len(events)==2
    assert events[0]["previous_state"]=="speed_pct=87.38" and events[0]["new_state"]=="speed_pct=100.0"
    assert events[0]["effective_timestamp"].endswith("00:45:00+00:00")
    sensors={s["sensor_id"] for s in _read(tmp_path/"sensors.csv") if s["asset_id"]=="PUMP-001"}
    values=[r for r in _read(tmp_path/"telemetry.csv") if r["sensor_id"] in sensors]
    def avg(lo,hi):
        selected=[r for r in values if lo<=datetime.fromisoformat(r["timestamp"]).hour*60+datetime.fromisoformat(r["timestamp"]).minute<hi]
        return sum(float(r["value"]) for r in selected)/len(selected)
    assert avg(45,50)>avg(40,45)*1.1
    assert events[1]["new_state"]==events[0]["previous_state"]


def test_blockage_changes_pipe_resistance_and_not_valve_state(tmp_path):
    fault=tmp_path/"fault";normal=tmp_path/"normal"
    generate(Config.for_profile("starter",telemetry_count=12000),fault)
    generate(Config.for_profile("starter",telemetry_count=12000,scenario="normal"),normal)
    fault_events=[e for e in _read(fault/"state_events.csv") if e["asset_id"]=="PIPE-002" and "resistance_factor" in e["new_state"]]
    assert fault_events and "6.0" in fault_events[0]["new_state"]
    assert next(v for v in _read(fault/"valves.csv") if v["valve_id"]=="VALVE-002")["state"]=="OPEN"
    def mean(path,typ,lo,hi):
        rows=[r for r in _read(path/"telemetry.csv") if r["asset_id"]=="PIPE-002" and r["measurement_type"]==typ and lo<=int(r["timestamp"][14:16])<hi]
        return sum(float(r["value"]) for r in rows)/len(rows)
    assert mean(fault,"FLOW",5,10)<mean(normal,"FLOW",5,10)
    assert mean(fault,"PRESSURE",5,10)>mean(normal,"PRESSURE",5,10)


def test_manifest_verifies_declared_paths_sizes_and_hashes(tmp_path):
    (tmp_path/"data.csv").write_text("a\n1\n",encoding="utf-8")
    (tmp_path/"manifest.json").write_text(json.dumps({"seed":1}),encoding="utf-8")
    refresh_manifest(tmp_path)
    report=verify_manifest(tmp_path)
    assert report["valid"]
    manifest=json.loads((tmp_path/"manifest.json").read_text())
    for relative,expected in manifest["artifacts"].items():
        path=tmp_path/relative
        assert path.is_file() and path.stat().st_size==expected["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected["sha256"]
    (tmp_path/"data.csv").write_text("a\n2\n",encoding="utf-8")
    assert any("mismatch" in e for e in verify_manifest(tmp_path)["errors"])
    (tmp_path/"data.csv").unlink()
    assert any("missing artifact" in e for e in verify_manifest(tmp_path)["errors"])


def test_verify_manifest_cli_returns_success_for_complete_manifest(tmp_path, capsys):
    from plant_sim.cli import main
    (tmp_path/"evidence.csv").write_text("x\n1\n",encoding="utf-8")
    (tmp_path/"manifest.json").write_text("{}",encoding="utf-8")
    refresh_manifest(tmp_path)
    assert main(["verify-manifest","--input-dir",str(tmp_path)])==0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_cli_selects_requested_run_and_rejects_unknown_id(tmp_path, capsys):
    from plant_sim.cli import main
    cfg=Config.for_profile("starter")
    generate(cfg,tmp_path);evaluation_module.evaluate(tmp_path);create_database(tmp_path)
    second=replace(cfg,run_number=2,seed=cfg.seed+1)
    generate(second,tmp_path);evaluation_module.evaluate(tmp_path);db=create_database(tmp_path)
    generated_pump=next(r for r in _read(tmp_path/"pumps.csv") if r["pump_id"]=="PUMP-001")
    with sqlite3.connect(db) as con:catalog_pump=con.execute("SELECT max_flow_lpm FROM pump WHERE pump_id='PUMP-001'").fetchone()[0]
    assert float(generated_pump["max_flow_lpm"])!=catalog_pump
    snapshot=tmp_path/"run2-snapshot";export_run_snapshot(db,"SIM-2026-000002",snapshot)
    assert next(r for r in _read(snapshot/"pumps.csv") if r["pump_id"]=="PUMP-001")==generated_pump
    main(["evaluate","--input-dir",str(tmp_path),"--run-id","SIM-2026-000001"])
    assert json.loads((tmp_path/"evaluation_summary-SIM-2026-000001.json").read_text())["simulation_run_id"]=="SIM-2026-000001"
    main(["evaluate","--input-dir",str(tmp_path),"--run-id","SIM-2026-000002"])
    assert json.loads((tmp_path/"evaluation_summary-SIM-2026-000002.json").read_text())["simulation_run_id"]=="SIM-2026-000002"
    with pytest.raises(SystemExit) as exc:
        main(["evaluate","--input-dir",str(tmp_path),"--run-id","SIM-2026-999999"])
    assert exc.value.code==2
    assert "unknown simulation run ID" in capsys.readouterr().err
