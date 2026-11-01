import csv, sqlite3, json
from pathlib import Path

_BASE_SCHEMA = """PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS facility(facility_id TEXT PRIMARY KEY,name TEXT NOT NULL,lifecycle_state TEXT NOT NULL CHECK(lifecycle_state='ACTIVE'));
CREATE TABLE IF NOT EXISTS asset(asset_id TEXT PRIMARY KEY,asset_type TEXT NOT NULL CHECK(asset_type IN ('FACILITY','PUMP','TANK','VALVE','PIPE','SENSOR')),facility_id TEXT NOT NULL REFERENCES facility,UNIQUE(asset_id,facility_id));
CREATE TABLE IF NOT EXISTS pump(pump_id TEXT PRIMARY KEY REFERENCES asset(asset_id),facility_id TEXT NOT NULL REFERENCES facility,max_flow_lpm REAL NOT NULL CHECK(max_flow_lpm>0),speed_pct REAL NOT NULL CHECK(speed_pct BETWEEN 0 AND 100),lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('ACTIVE','MAINTENANCE','INACTIVE')));
CREATE TABLE IF NOT EXISTS tank(tank_id TEXT PRIMARY KEY REFERENCES asset(asset_id),facility_id TEXT NOT NULL REFERENCES facility,capacity_l REAL NOT NULL CHECK(capacity_l>0),initial_level_l REAL NOT NULL CHECK(initial_level_l>=0 AND initial_level_l<=capacity_l),lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('ACTIVE','MAINTENANCE','INACTIVE')));
CREATE TABLE IF NOT EXISTS valve(valve_id TEXT PRIMARY KEY REFERENCES asset(asset_id),facility_id TEXT NOT NULL REFERENCES facility,state TEXT NOT NULL CHECK(state IN ('OPEN','CLOSED','THROTTLED')),opening_pct REAL NOT NULL CHECK(opening_pct BETWEEN 0 AND 100),lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('ACTIVE','MAINTENANCE','INACTIVE')));
CREATE TABLE IF NOT EXISTS topology_node(node_id TEXT PRIMARY KEY,facility_id TEXT NOT NULL REFERENCES facility,asset_type TEXT NOT NULL,asset_id TEXT NOT NULL REFERENCES asset(asset_id),UNIQUE(node_id,facility_id));
CREATE TABLE IF NOT EXISTS pipe(pipe_id TEXT PRIMARY KEY REFERENCES asset(asset_id),facility_id TEXT NOT NULL REFERENCES facility,from_node_id TEXT NOT NULL,to_node_id TEXT NOT NULL,valve_id TEXT NOT NULL UNIQUE REFERENCES valve(valve_id),diameter_mm REAL NOT NULL CHECK(diameter_mm>0),resistance REAL NOT NULL CHECK(resistance>0),lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('ACTIVE','MAINTENANCE','INACTIVE')),CHECK(from_node_id<>to_node_id),FOREIGN KEY(from_node_id,facility_id) REFERENCES topology_node(node_id,facility_id),FOREIGN KEY(to_node_id,facility_id) REFERENCES topology_node(node_id,facility_id));
CREATE TABLE IF NOT EXISTS sensor(sensor_id TEXT PRIMARY KEY REFERENCES asset(asset_id),facility_id TEXT NOT NULL REFERENCES facility,asset_id TEXT NOT NULL,measurement_type TEXT NOT NULL CHECK(measurement_type IN ('FLOW','PRESSURE','LEVEL')),unit TEXT NOT NULL CHECK((measurement_type='FLOW' AND unit='L/min') OR (measurement_type='PRESSURE' AND unit='kPa') OR (measurement_type='LEVEL' AND unit='L')),lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('ACTIVE','MAINTENANCE','INACTIVE')),FOREIGN KEY(asset_id,facility_id) REFERENCES asset(asset_id,facility_id),UNIQUE(sensor_id,asset_id,facility_id,measurement_type,unit));
CREATE TABLE IF NOT EXISTS simulation_run(simulation_run_id TEXT PRIMARY KEY,seed INTEGER NOT NULL,profile TEXT NOT NULL,status TEXT NOT NULL,start_timestamp TEXT NOT NULL,end_timestamp TEXT NOT NULL,input_config_json TEXT NOT NULL CHECK(json_valid(input_config_json)),CHECK(start_timestamp<=end_timestamp));
CREATE TABLE IF NOT EXISTS ground_truth(simulation_run_id TEXT NOT NULL REFERENCES simulation_run,scenario_id TEXT NOT NULL,affected_asset_id TEXT NOT NULL REFERENCES asset(asset_id),anomaly_type TEXT NOT NULL,start_timestamp TEXT NOT NULL,end_timestamp TEXT NOT NULL,expected_class TEXT NOT NULL,expected_decision TEXT NOT NULL,severity TEXT NOT NULL,event_refs TEXT NOT NULL,PRIMARY KEY(simulation_run_id,scenario_id),CHECK(start_timestamp<end_timestamp));
CREATE TABLE IF NOT EXISTS telemetry(telemetry_id TEXT PRIMARY KEY,simulation_run_id TEXT NOT NULL REFERENCES simulation_run,sensor_id TEXT NOT NULL,facility_id TEXT NOT NULL,asset_id TEXT NOT NULL,timestamp TEXT NOT NULL,measurement_type TEXT NOT NULL,value REAL NOT NULL,unit TEXT NOT NULL,quality_status TEXT NOT NULL CHECK(quality_status IN ('GOOD','SUSPECT','BAD')),FOREIGN KEY(sensor_id,asset_id,facility_id,measurement_type,unit) REFERENCES sensor(sensor_id,asset_id,facility_id,measurement_type,unit),FOREIGN KEY(asset_id,facility_id) REFERENCES asset(asset_id,facility_id));
CREATE TABLE IF NOT EXISTS mass_balance(simulation_run_id TEXT NOT NULL REFERENCES simulation_run,facility_id TEXT NOT NULL REFERENCES facility,timestamp TEXT NOT NULL,inflow_lpm REAL NOT NULL,outflow_lpm REAL NOT NULL,storage_change_l REAL NOT NULL,residual_l REAL NOT NULL,tolerance_l REAL NOT NULL CHECK(tolerance_l>0),PRIMARY KEY(simulation_run_id,facility_id,timestamp));
CREATE TABLE IF NOT EXISTS operating_mode(mode_id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL CHECK(name IN ('NORMAL','HIGH_DEMAND','MAINTENANCE','STARTUP')),demand_factor REAL NOT NULL CHECK(demand_factor>0));
CREATE TABLE IF NOT EXISTS alarm(prediction_id TEXT PRIMARY KEY,simulation_run_id TEXT NOT NULL REFERENCES simulation_run,affected_asset_id TEXT NOT NULL REFERENCES asset(asset_id),detected_class TEXT NOT NULL CHECK(detected_class IN ('LEAK','BLOCKAGE','PUMP_DEGRADATION','SENSOR_FAULT','TANK_OVER_CAPACITY','FLOW_CONSERVATION_VIOLATION')),severity TEXT NOT NULL CHECK(severity IN ('HIGH','MEDIUM')),detection_timestamp TEXT NOT NULL,alert_emission_timestamp TEXT NOT NULL,supporting_measurements TEXT NOT NULL CHECK(json_valid(supporting_measurements)),rule_triggered TEXT NOT NULL,explanation TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS state_event(event_id TEXT PRIMARY KEY,simulation_run_id TEXT NOT NULL REFERENCES simulation_run,asset_id TEXT NOT NULL REFERENCES asset(asset_id),previous_state TEXT NOT NULL,new_state TEXT NOT NULL,effective_timestamp TEXT NOT NULL,reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS simulation_asset(simulation_run_id TEXT NOT NULL REFERENCES simulation_run,asset_id TEXT NOT NULL REFERENCES asset(asset_id),PRIMARY KEY(simulation_run_id,asset_id));
CREATE INDEX IF NOT EXISTS telemetry_time_idx ON telemetry(timestamp);
CREATE TRIGGER IF NOT EXISTS sensor_target_type_insert BEFORE INSERT ON sensor BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset a WHERE a.asset_id=NEW.asset_id AND a.facility_id=NEW.facility_id AND ((NEW.measurement_type='FLOW' AND a.asset_type IN ('PIPE','PUMP')) OR (NEW.measurement_type='PRESSURE' AND a.asset_type='PIPE') OR (NEW.measurement_type='LEVEL' AND a.asset_type='TANK'))) THEN RAISE(ABORT,'sensor target asset/type/facility mismatch') END; SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset a WHERE a.asset_id=NEW.sensor_id AND a.facility_id=NEW.facility_id AND a.asset_type='SENSOR') THEN RAISE(ABORT,'sensor identity asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS sensor_target_type_update BEFORE UPDATE OF sensor_id,asset_id,facility_id,measurement_type,unit ON sensor BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset a WHERE a.asset_id=NEW.asset_id AND a.facility_id=NEW.facility_id AND ((NEW.measurement_type='FLOW' AND a.asset_type IN ('PIPE','PUMP')) OR (NEW.measurement_type='PRESSURE' AND a.asset_type='PIPE') OR (NEW.measurement_type='LEVEL' AND a.asset_type='TANK'))) THEN RAISE(ABORT,'sensor target asset/type/facility mismatch') END; SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset a WHERE a.asset_id=NEW.sensor_id AND a.facility_id=NEW.facility_id AND a.asset_type='SENSOR') THEN RAISE(ABORT,'sensor identity asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS asset_facility_asset_insert BEFORE INSERT ON asset WHEN NEW.asset_type='FACILITY' BEGIN SELECT CASE WHEN NEW.asset_id<>NEW.facility_id THEN RAISE(ABORT,'facility asset ID must match facility ID') END; END;
CREATE TRIGGER IF NOT EXISTS pump_asset_type_update BEFORE UPDATE OF pump_id,facility_id ON pump BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.pump_id AND facility_id=NEW.facility_id AND asset_type='PUMP') THEN RAISE(ABORT,'pump asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS tank_asset_type_update BEFORE UPDATE OF tank_id,facility_id ON tank BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.tank_id AND facility_id=NEW.facility_id AND asset_type='TANK') THEN RAISE(ABORT,'tank asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS valve_asset_type_update BEFORE UPDATE OF valve_id,facility_id ON valve BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.valve_id AND facility_id=NEW.facility_id AND asset_type='VALVE') THEN RAISE(ABORT,'valve asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS pipe_asset_type_update BEFORE UPDATE OF pipe_id,facility_id,valve_id ON pipe BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.pipe_id AND facility_id=NEW.facility_id AND asset_type='PIPE') THEN RAISE(ABORT,'pipe asset mismatch') END; SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM valve WHERE valve_id=NEW.valve_id AND facility_id=NEW.facility_id) THEN RAISE(ABORT,'pipe controlling valve facility mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS topology_node_asset_update BEFORE UPDATE OF facility_id,asset_type,asset_id ON topology_node BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.asset_id AND facility_id=NEW.facility_id AND asset_type=NEW.asset_type) THEN RAISE(ABORT,'topology node asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS telemetry_tuple_insert BEFORE INSERT ON telemetry BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM sensor s JOIN asset a ON a.asset_id=s.asset_id AND a.facility_id=s.facility_id WHERE s.sensor_id=NEW.sensor_id AND s.asset_id=NEW.asset_id AND s.facility_id=NEW.facility_id AND s.measurement_type=NEW.measurement_type AND s.unit=NEW.unit) THEN RAISE(ABORT,'telemetry sensor/asset/facility/type/unit mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS telemetry_tuple_update BEFORE UPDATE OF sensor_id,asset_id,facility_id,measurement_type,unit ON telemetry BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM sensor s JOIN asset a ON a.asset_id=s.asset_id AND a.facility_id=s.facility_id WHERE s.sensor_id=NEW.sensor_id AND s.asset_id=NEW.asset_id AND s.facility_id=NEW.facility_id AND s.measurement_type=NEW.measurement_type AND s.unit=NEW.unit) THEN RAISE(ABORT,'telemetry sensor/asset/facility/type/unit mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS pipe_facility_insert BEFORE INSERT ON pipe BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM topology_node WHERE node_id=NEW.from_node_id AND facility_id=NEW.facility_id) OR NOT EXISTS(SELECT 1 FROM topology_node WHERE node_id=NEW.to_node_id AND facility_id=NEW.facility_id) THEN RAISE(ABORT,'pipe endpoints must belong to pipe facility') END; END;
CREATE TRIGGER IF NOT EXISTS pipe_facility_update BEFORE UPDATE OF facility_id,from_node_id,to_node_id ON pipe BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM topology_node WHERE node_id=NEW.from_node_id AND facility_id=NEW.facility_id) OR NOT EXISTS(SELECT 1 FROM topology_node WHERE node_id=NEW.to_node_id AND facility_id=NEW.facility_id) THEN RAISE(ABORT,'pipe endpoints must belong to pipe facility') END; END;
CREATE TRIGGER IF NOT EXISTS pump_asset_type_insert BEFORE INSERT ON pump BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.pump_id AND facility_id=NEW.facility_id AND asset_type='PUMP') THEN RAISE(ABORT,'pump asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS tank_asset_type_insert BEFORE INSERT ON tank BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.tank_id AND facility_id=NEW.facility_id AND asset_type='TANK') THEN RAISE(ABORT,'tank asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS valve_asset_type_insert BEFORE INSERT ON valve BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.valve_id AND facility_id=NEW.facility_id AND asset_type='VALVE') THEN RAISE(ABORT,'valve asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS pipe_asset_type_insert BEFORE INSERT ON pipe BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.pipe_id AND facility_id=NEW.facility_id AND asset_type='PIPE') THEN RAISE(ABORT,'pipe asset mismatch') END; SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM valve WHERE valve_id=NEW.valve_id AND facility_id=NEW.facility_id) THEN RAISE(ABORT,'pipe controlling valve facility mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS topology_node_asset_insert BEFORE INSERT ON topology_node BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM asset WHERE asset_id=NEW.asset_id AND facility_id=NEW.facility_id AND asset_type=NEW.asset_type) THEN RAISE(ABORT,'topology node asset mismatch') END; END;
CREATE TRIGGER IF NOT EXISTS asset_identity_immutable BEFORE UPDATE OF asset_type,facility_id ON asset BEGIN SELECT RAISE(ABORT,'canonical asset type and facility are immutable'); END;
CREATE TRIGGER IF NOT EXISTS state_event_no_update BEFORE UPDATE ON state_event BEGIN SELECT RAISE(ABORT,'state_event history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS state_event_no_delete BEFORE DELETE ON state_event BEGIN SELECT RAISE(ABORT,'state_event history is append-only'); END;
"""

_IMMUTABLE_KEYS = {
    "facility": ("facility_id",), "asset": ("asset_id",), "pump": ("pump_id",), "tank": ("tank_id",),
    "valve": ("valve_id",), "topology_node": ("node_id",), "pipe": ("pipe_id",), "sensor": ("sensor_id",),
    "simulation_run": ("simulation_run_id",), "ground_truth": ("simulation_run_id", "scenario_id"),
    "telemetry": ("telemetry_id",), "mass_balance": ("simulation_run_id", "facility_id", "timestamp"),
    "operating_mode": ("mode_id",), "alarm": ("prediction_id",), "state_event": ("event_id",),
    "simulation_asset": ("simulation_run_id", "asset_id"),
}
_IMMUTABLE_SQL = "\n".join(
    f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_key BEFORE UPDATE OF {','.join(keys)} ON {table} "
    f"WHEN {' OR '.join(f'NEW.{key} IS NOT OLD.{key}' for key in keys)} "
    "BEGIN SELECT RAISE(ABORT,'entity IDs and primary keys are immutable'); END;"
    for table, keys in _IMMUTABLE_KEYS.items()
)
SCHEMA = _BASE_SCHEMA + "\n" + _IMMUTABLE_SQL


def create_database(output_dir):
    root=Path(output_dir); db=root/"simulation.sqlite"
    con=sqlite3.connect(db); con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    # Additive compatibility for prior Phase 3 databases.
    alarm_cols={r[1] for r in con.execute("PRAGMA table_info(alarm)")}
    if "alert_emission_timestamp" not in alarm_cols:
        con.execute("ALTER TABLE alarm ADD COLUMN alert_emission_timestamp TEXT NOT NULL DEFAULT ''")
    mapping={
        "facilities":("facility","facility_id,name,lifecycle_state"),
        "assets":("asset","asset_id,asset_type,facility_id"),
        "pumps":("pump","pump_id,facility_id,max_flow_lpm,speed_pct,lifecycle_state"),
        "tanks":("tank","tank_id,facility_id,capacity_l,initial_level_l,lifecycle_state"),
        "valves":("valve","valve_id,facility_id,state,opening_pct,lifecycle_state"),
        "nodes":("topology_node","node_id,facility_id,asset_type,asset_id"),
        "pipes":("pipe","pipe_id,facility_id,from_node_id,to_node_id,valve_id,diameter_mm,resistance,lifecycle_state"),
        "sensors":("sensor","sensor_id,facility_id,asset_id,measurement_type,unit,lifecycle_state"),
        "simulation_runs":("simulation_run","simulation_run_id,seed,profile,status,start_timestamp,end_timestamp,input_config_json"),
        "operating_modes":("operating_mode","mode_id,name,demand_factor"),
        "state_events":("state_event","event_id,simulation_run_id,asset_id,previous_state,new_state,effective_timestamp,reason"),
        "simulation_assets":("simulation_asset","simulation_run_id,asset_id"),
        "ground_truth":("ground_truth","simulation_run_id,scenario_id,affected_asset_id,anomaly_type,start_timestamp,end_timestamp,expected_class,expected_decision,severity,event_refs"),
        "alarms":("alarm","prediction_id,simulation_run_id,affected_asset_id,detected_class,severity,detection_timestamp,alert_emission_timestamp,supporting_measurements,rule_triggered,explanation"),
    }
    try:
        for file,(table,cols) in mapping.items():
            if not (root/f"{file}.csv").exists(): continue
            with (root/f"{file}.csv").open(encoding="utf-8",newline="") as f:
                reader=csv.DictReader(f); names=cols.split(",")
                sql=f"INSERT OR IGNORE INTO {table}({cols}) VALUES({','.join('?' for _ in names)})"
                con.executemany(sql,([r[c] for c in names] for r in reader))
        for filename,table,cols in [
            ("telemetry.csv","telemetry","telemetry_id,simulation_run_id,sensor_id,facility_id,asset_id,timestamp,measurement_type,value,unit,quality_status"),
            ("mass_balance.csv","mass_balance","simulation_run_id,facility_id,timestamp,inflow_lpm,outflow_lpm,storage_change_l,residual_l,tolerance_l"),
        ]:
            with (root/filename).open(encoding="utf-8",newline="") as f:
                reader=csv.DictReader(f); names=cols.split(",")
                sql=f"INSERT OR IGNORE INTO {table}({cols}) VALUES({','.join('?' for _ in names)})"
                while batch:=list(__import__('itertools').islice(reader,10000)):
                    con.executemany(sql,([r[c] for c in names] for r in batch))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally: con.close()
    return db


def validate_database(path):
    con=sqlite3.connect(path); con.execute("PRAGMA foreign_keys=ON")
    fk=con.execute("PRAGMA foreign_key_check").fetchall()
    integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
    tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    association_count=con.execute("SELECT count(*) FROM simulation_asset").fetchone()[0]
    duplicate_count=con.execute("SELECT count(*) FROM (SELECT simulation_run_id,asset_id,count(*) n FROM simulation_asset GROUP BY 1,2 HAVING n>1)").fetchone()[0]
    invalid_assoc=con.execute("SELECT count(*) FROM simulation_asset sa LEFT JOIN simulation_run r USING(simulation_run_id) LEFT JOIN asset a USING(asset_id) WHERE r.simulation_run_id IS NULL OR a.asset_id IS NULL").fetchone()[0]
    per_run=con.execute("SELECT r.simulation_run_id,r.input_config_json,count(sa.asset_id) FROM simulation_run r LEFT JOIN simulation_asset sa USING(simulation_run_id) GROUP BY r.simulation_run_id,r.input_config_json").fetchall()
    expected_asset_associations=0;missing_assoc=0
    for _run,config_json,actual in per_run:
        try:expected=int(json.loads(config_json)["participating_asset_count"])
        except (KeyError,ValueError,TypeError):expected=actual
        expected_asset_associations+=expected;missing_assoc+=max(0,expected-actual)
    mismatches={
        "sensor_asset_facility_type_unit":con.execute("SELECT count(*) FROM telemetry t LEFT JOIN sensor s ON s.sensor_id=t.sensor_id AND s.asset_id=t.asset_id AND s.facility_id=t.facility_id AND s.measurement_type=t.measurement_type AND s.unit=t.unit WHERE s.sensor_id IS NULL").fetchone()[0],
        "pipe_endpoint_facility":con.execute("SELECT count(*) FROM pipe p JOIN topology_node a ON a.node_id=p.from_node_id JOIN topology_node b ON b.node_id=p.to_node_id WHERE a.facility_id<>p.facility_id OR b.facility_id<>p.facility_id").fetchone()[0],
    }
    con.close(); bridge_ok=not (duplicate_count or invalid_assoc or missing_assoc or association_count>expected_asset_associations)
    return {"foreign_key_violations":len(fk),"integrity_check":integrity,"simulation_asset_rows":association_count,"expected_asset_associations":expected_asset_associations,"duplicate_associations":duplicate_count,"invalid_associations":invalid_assoc,"missing_associations":missing_assoc,"relationship_mismatches":mismatches,"bridge_valid":bridge_ok,"valid":not fk and integrity=="ok" and bridge_ok and not any(mismatches.values()),"tables":tables}


def export_sql(database_path, output_path):
    """Export INSERT-only SQL from the persisted SQLite database in FK dependency order."""
    order=["facility","asset","pump","tank","valve","topology_node","pipe","sensor","simulation_run","operating_mode","state_event","simulation_asset","ground_truth","telemetry","mass_balance","alarm"]
    con=sqlite3.connect(database_path); con.row_factory=sqlite3.Row
    try:
        existing={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with Path(output_path).open("w",encoding="utf-8",newline="\n") as f:
            f.write("-- Generated from persisted plant_sim SQLite database. Apply sql/schema.sql first.\nPRAGMA foreign_keys=ON;\nBEGIN;\n")
            for table in order:
                if table not in existing:continue
                cols=[r[1] for r in con.execute(f"PRAGMA table_info({table})")]
                col_sql=",".join('"'+c+'"' for c in cols)
                cur=con.execute(f"SELECT * FROM {table}")
                while batch:=cur.fetchmany(5000):
                    for row in batch:
                        values=[]
                        for value in row:
                            if value is None:values.append("NULL")
                            elif isinstance(value,int):values.append(str(value))
                            elif isinstance(value,float):values.append(format(value,".17g"))
                            elif isinstance(value,bytes):values.append("X'"+value.hex()+"'")
                            else:values.append("'"+str(value).replace("'","''")+"'")
                        f.write(f"INSERT INTO \"{table}\" ({col_sql}) VALUES ({','.join(values)});\n")
            f.write("COMMIT;\n")
    finally:con.close()
    return Path(output_path)


def export_run_snapshot(database_path, run_id, output_dir):
    """Materialize one persisted run and its labels as detector/evaluator CSV inputs."""
    root=Path(output_dir);root.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(database_path);con.row_factory=sqlite3.Row
    mapping={
        "facility":("facilities.csv",None),"asset":("assets.csv",None),"pump":("pumps.csv",None),
        "tank":("tanks.csv",None),"valve":("valves.csv",None),"pipe":("pipes.csv",None),
        "topology_node":("nodes.csv",None),"sensor":("sensors.csv",None),
        "operating_mode":("operating_modes.csv",None),"simulation_run":("simulation_runs.csv","simulation_run_id"),
        "state_event":("state_events.csv","simulation_run_id"),"simulation_asset":("simulation_assets.csv","simulation_run_id"),
        "ground_truth":("ground_truth.csv","simulation_run_id"),"telemetry":("telemetry.csv","simulation_run_id"),
        "mass_balance":("mass_balance.csv","simulation_run_id"),
    }
    try:
        if con.execute("SELECT 1 FROM simulation_run WHERE simulation_run_id=?",(run_id,)).fetchone() is None:
            raise ValueError(f"unknown simulation run ID: {run_id}")
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ground_truth'").fetchone():
            raise ValueError(f"ground-truth evidence for simulation run {run_id} is unavailable in this database")
        run_config=con.execute("SELECT input_config_json FROM simulation_run WHERE simulation_run_id=?",(run_id,)).fetchone()[0]
        master_snapshot=json.loads(run_config).get("master_snapshot",{})
        snapshot_names={"facility":"facilities","asset":"assets","pump":"pumps","tank":"tanks","pipe":"pipes"}
        for table,(filename,filter_col) in mapping.items():
            snapshot_key=snapshot_names.get(table)
            if snapshot_key in master_snapshot:
                records=master_snapshot[snapshot_key]
                with (root/filename).open("w",encoding="utf-8",newline="") as f:
                    if records:
                        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
                continue
            cols=[r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            if filter_col:
                cur=con.execute(f"SELECT * FROM {table} WHERE {filter_col}=?",(run_id,))
            else:
                cur=con.execute(f"SELECT * FROM {table}")
            with (root/filename).open("w",encoding="utf-8",newline="") as f:
                writer=csv.writer(f);writer.writerow(cols);writer.writerows(cur)
    finally:con.close()
    return root
