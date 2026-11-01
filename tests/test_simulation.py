import csv, json
from pathlib import Path
import pytest
from plant_sim.config import Config
from plant_sim.generator import generate
from plant_sim.validation import (validate_unique_ids,validate_required,validate_pipe_record,validate_tank_level,
    validate_simulation_input,validate_simulation_config,validate_valve_state,validate_valve_configuration,validate_pump_config,validate_event_order,validate_lifecycle_transition)
from plant_sim.physics import pump_flow,tank_delta_l,mass_balance_residual
from plant_sim.detection import detect
from plant_sim.evaluation import evaluate
from plant_sim.database import create_database,validate_database,export_sql,SCHEMA
import sqlite3
from plant_sim.topology import connectivity

def test_equations_and_tolerance():
    assert pump_flow(50,1000)==500
    assert tank_delta_l(20,10,2)==8
    assert abs(mass_balance_residual(20,10,2,8))<1e-9
    assert abs(mass_balance_residual(20,10,2,0))>5

def test_generated_physical_telemetry_schema_and_exact_count(tmp_path):
    manifest=generate(Config.for_profile("starter",telemetry_count=1200),tmp_path)
    with (tmp_path/"telemetry.csv").open() as f:
        reader=csv.DictReader(f); rows=[next(reader) for _ in range(1200)]
    required={"telemetry_id","facility_id","sensor_id","asset_id","timestamp","measurement_type","value","unit","quality_status","simulation_run_id"}
    assert required==set(rows[0]) and len(rows)==1200
    pumps={r["pump_id"]:r for r in csv.DictReader((tmp_path/"pumps.csv").open())}
    pump_sensor=next(r["sensor_id"] for r in csv.DictReader((tmp_path/"sensors.csv").open()) if r["asset_id"]=="PUMP-001")
    pump_reading=next(float(r["value"]) for r in rows if r["sensor_id"]==pump_sensor)
    nominal=float(pumps["PUMP-001"]["max_flow_lpm"])*float(pumps["PUMP-001"]["speed_pct"])/100
    assert abs(pump_reading-nominal)<nominal*.01
    assert manifest["row_counts"]["telemetry"]==1200

def test_topology_rejects_missing_node_and_connected_generation(tmp_path):
    with pytest.raises(ValueError,match="missing node"):
        validate_pipe_record({"pipe_id":"P","facility_id":"F","from_node_id":"N1","to_node_id":"BAD","valve_id":"V"},{"N1"})
    generate(Config.for_profile("starter"),tmp_path)
    import json as js
    nodes=list(csv.DictReader((tmp_path/"nodes.csv").open()));pipes=list(csv.DictReader((tmp_path/"pipes.csv").open()))
    assert all(connectivity(nodes,pipes).values())

def test_required_duplicate_enum_foreign_key_lifecycle_dates_and_configs():
    with pytest.raises(ValueError,match="duplicate"):validate_unique_ids([{"id":"x"},{"id":"x"}],"id")
    with pytest.raises(ValueError,match="missing required"):validate_required({"id":"x"},["id","name"])
    with pytest.raises(ValueError,match="missing node"):validate_pipe_record({"pipe_id":"P","facility_id":"F","from_node_id":"N","to_node_id":"Z","valve_id":"V"},{"N"})
    with pytest.raises(ValueError,match="invalid valve"):validate_valve_state("JAMMED")
    with pytest.raises(ValueError,match="outside"):validate_valve_configuration({"state":"OPEN","opening_pct":101})
    with pytest.raises(ValueError,match="pump configuration"):validate_pump_config({"max_flow_lpm":0,"speed_pct":120})
    with pytest.raises(ValueError,match="required"):validate_simulation_input(None)
    with pytest.raises(ValueError,match="exceeds"):validate_tank_level(101,100)
    with pytest.raises(ValueError,match="end precedes"):validate_event_order("2026-02-01","2026-01-01")
    with pytest.raises(ValueError,match="invalid lifecycle"):validate_lifecycle_transition("ACTIVE","ACTIVE")

def test_injected_scenarios_detected_from_telemetry_and_truth_isolation(tmp_path,monkeypatch):
    generate(Config.for_profile("starter"),tmp_path)
    truth=list(csv.DictReader((tmp_path/"ground_truth.csv").open()))
    assert len(truth)==12 and len({r["affected_asset_id"] for r in truth})==12
    assert {r["severity"] for r in truth}=={"MEDIUM","HIGH"}
    assert {r["start_timestamp"][14:16] for r in truth}=={"05","15"}
    original=Path.open
    def guarded(path,*args,**kwargs):
        if path.name=="ground_truth.csv":raise AssertionError("detector attempted to read ground truth")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"open",guarded)
    preds=detect(tmp_path)
    assert len({p["prediction_id"] for p in preds})==len(preds)
    expected={"LEAK","BLOCKAGE","PUMP_DEGRADATION","SENSOR_FAULT","TANK_OVER_CAPACITY","FLOW_CONSERVATION_VIOLATION"}
    assert {p["detected_class"] for p in preds}==expected
    sensor=[p for p in preds if p["affected_asset_id"] in {"SNS-001","SNS-007"}]
    assert len(sensor)==2 and all(p["detected_class"]=="SENSOR_FAULT" for p in sensor)

def test_evaluation_has_normal_negative_windows_and_no_false_alarms(tmp_path):
    generate(Config.for_profile("starter"),tmp_path)
    result=evaluate(tmp_path)
    assert result["event_metrics"]["TP"]==12 and result["event_metrics"]["FP"]==result["event_metrics"]["FN"]==0
    assert result["normal_window_false_alarm_metrics"]["false_alarm_window_rate"]==0
    assert result["normal_window_false_alarm_metrics"]["normal_windows"]==12
    assert result["normal_control_injection_overlaps"]==[]
    assert result["detected_alarms"]==12

def test_database_batched_persistence_and_relationships(tmp_path):
    generate(Config.for_profile("starter"),tmp_path);evaluate(tmp_path)
    db=create_database(tmp_path);result=validate_database(db)
    assert result["valid"] and result["foreign_key_violations"]==0
    assert result["simulation_asset_rows"]==result["expected_asset_associations"]
    con=sqlite3.connect(db);assert con.execute("SELECT count(*) FROM alarm").fetchone()[0]==12
    assert con.execute("SELECT count(*) FROM ground_truth").fetchone()[0]==12;con.close()

def test_simulation_asset_rejects_missing_and_duplicate_and_preserves_runs(tmp_path):
    config=Config.for_profile("starter")
    generate(config,tmp_path);evaluate(tmp_path);db=create_database(tmp_path)
    con=sqlite3.connect(db);con.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):con.execute("INSERT INTO simulation_asset VALUES('SIM-2026-000001','MISSING-ASSET')")
    with pytest.raises(sqlite3.IntegrityError):con.execute("INSERT INTO simulation_asset SELECT simulation_run_id,asset_id FROM simulation_asset LIMIT 1")
    con.close()
    from dataclasses import replace
    generate(replace(config,run_number=2),tmp_path);evaluate(tmp_path);create_database(tmp_path)
    con=sqlite3.connect(db)
    assert con.execute("SELECT count(*) FROM simulation_run").fetchone()[0]==2
    assert con.execute("SELECT count(DISTINCT simulation_run_id) FROM simulation_asset").fetchone()[0]==2
    assert con.execute("SELECT count(*) FROM telemetry").fetchone()[0]==14000
    con.close()
    history=validate_database(db)
    assert history["valid"] and history["simulation_asset_rows"]==history["expected_asset_associations"]==690

def test_sql_export_import_roundtrip(tmp_path):
    generate(Config.for_profile("starter"),tmp_path);evaluate(tmp_path);source=create_database(tmp_path)
    sql=tmp_path/"seed_data.sql";export_sql(source,sql)
    restored=tmp_path/"restored.sqlite";con=sqlite3.connect(restored)
    schema_path=Path(__file__).parents[1]/"sql"/"schema.sql"
    con.executescript(schema_path.read_text(encoding="utf-8"));con.executescript(sql.read_text(encoding="utf-8"))
    original=sqlite3.connect(source)
    tables=["facility","asset","pump","tank","valve","topology_node","pipe","sensor","simulation_run","operating_mode","state_event","simulation_asset","ground_truth","telemetry","mass_balance","alarm"]
    assert {t:original.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}=={t:con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}
    original_resistance=original.execute("SELECT resistance FROM pipe WHERE pipe_id='PIPE-035'").fetchone()[0]
    restored_resistance=con.execute("SELECT resistance FROM pipe WHERE pipe_id='PIPE-035'").fetchone()[0]
    assert original_resistance==restored_resistance==9.82e-06
    assert con.execute("PRAGMA foreign_key_check").fetchall()==[]
    assert con.execute("SELECT count(*) FROM (SELECT asset_id,count(*) n FROM asset GROUP BY asset_id HAVING n>1)").fetchone()[0]==0
    assert con.execute("SELECT count(*) FROM telemetry").fetchone()==original.execute("SELECT count(*) FROM telemetry").fetchone()
    for table in tables:
        pk=[r[1] for r in con.execute(f"PRAGMA table_info({table})") if r[5]]
        cols=",".join('"'+c+'"' for c in pk)
        assert con.execute(f"SELECT count(*) FROM (SELECT {cols} FROM {table} GROUP BY {cols} HAVING count(*)>1)").fetchone()[0]==0
        order_by=",".join('"'+c+'"' for c in pk)
        source_rows=original.execute(f'SELECT * FROM "{table}" ORDER BY {order_by}').fetchall()
        restored_rows=con.execute(f'SELECT * FROM "{table}" ORDER BY {order_by}').fetchall()
        assert source_rows==restored_rows, f"row-by-row SQL round-trip mismatch in {table}"
    assert con.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    original.close();con.close()

def test_reproducible_seed_and_outputs(tmp_path):
    a,b=tmp_path/"a",tmp_path/"b";generate(Config.for_profile("starter"),a);generate(Config.for_profile("starter"),b)
    assert json.loads((a/"checksums.json").read_text())==json.loads((b/"checksums.json").read_text())
    assert (a/"ground_truth.csv").read_bytes()==(b/"ground_truth.csv").read_bytes()

def test_normal_only_window_has_no_alarms(tmp_path):
    generate(Config.for_profile("starter",scenario="normal"),tmp_path)
    balances=list(csv.DictReader((tmp_path/"mass_balance.csv").open()))
    assert all(float(r["residual_l"])==0 for r in balances)
    sensor=next(r["sensor_id"] for r in csv.DictReader((tmp_path/"sensors.csv").open()) if r["asset_id"]=="TANK-001")
    levels={int(r["timestamp"][14:16]):float(r["value"]) for r in csv.DictReader((tmp_path/"telemetry.csv").open()) if r["sensor_id"]==sensor and int(r["timestamp"][14:16]) in {24,29,34,39}}
    assert len(set(levels.values()))>1
    result=evaluate(tmp_path)
    assert result["detected_alarms"]==0 and result["normal_window_false_alarm_metrics"]["false_alarm_window_rate"]==0
    assert result["event_metrics"]["precision"] is None and result["event_metrics"]["recall"] is None

def test_injected_mass_balance_exceeds_tolerance(tmp_path):
    generate(Config.for_profile("starter"),tmp_path)
    balances=list(csv.DictReader((tmp_path/"mass_balance.csv").open()))
    strong=[r for r in balances if "00:05:" in r["timestamp"]]
    mild=[r for r in balances if "00:15:" in r["timestamp"]]
    assert {r["facility_id"]:float(r["residual_l"]) for r in strong}=={"FAC-001":20.0,"FAC-002":45.0,"FAC-003":0.0}
    assert {r["facility_id"]:float(r["residual_l"]) for r in mild}=={"FAC-001":8.0,"FAC-002":0.0,"FAC-003":20.0}

def test_full_profile_has_exact_telemetry_count(tmp_path):
    manifest=generate(Config.for_profile("full",telemetry_count=100_000),tmp_path)
    assert manifest["row_counts"]["telemetry"]==100_000
