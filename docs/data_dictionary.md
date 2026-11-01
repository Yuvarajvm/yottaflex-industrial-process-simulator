# Data dictionary

All SQLite columns below are `NOT NULL` unless noted; `Nullable=no` means NULL is rejected. CSV columns are also emitted on every row. SQLite stores numeric quantities as `REAL` and identifiers/timestamps as `TEXT`. Timestamps are ISO-8601 UTC. Entity IDs are immutable and primary keys are protected from updates by triggers. Foreign keys are enabled for persistence and SQL import.

## Core and supporting relational tables

| Table.field | Type | Required / nullable | Unit or allowed values | Key / uniqueness | Validation and meaning |
|---|---|---|---|---|---|
| `facility.facility_id` | TEXT | yes / no | `FAC-nnn` | PK | Stable facility identity. |
| `facility.name` | TEXT | yes / no | Human-readable | Not unique | Display name. |
| `facility.lifecycle_state` | TEXT | yes / no | `ACTIVE` | — | Current facility state; this schema version persists active facilities. |
| `asset.asset_id` | TEXT | yes / no | Typed ID prefix | PK; composite unique with facility | Canonical ID used by alarms, events, topology and run membership. Immutable. |
| `asset.asset_type` | TEXT | yes / no | FACILITY/PUMP/TANK/VALVE/PIPE/SENSOR | Part of composite unique | Must match the corresponding facility or typed subtype. |
| `asset.facility_id` | TEXT | yes / no | Facility ID | FK → facility | Facility owning the asset; immutable with asset type. |
| `pump.pump_id` | TEXT | yes / no | `PUMP-nnn` | PK/FK → asset | Must refer to a PUMP asset in the same facility. Immutable. |
| `pump.facility_id` | TEXT | yes / no | Facility ID | FK → facility | Owning facility. |
| `pump.max_flow_lpm` | REAL | yes / no | L/min | — | Positive nominal capacity. |
| `pump.speed_pct` | REAL | yes / no | 0–100% | — | Configured speed; operating changes are represented by state events and simulated output. |
| `pump.lifecycle_state` | TEXT | yes / no | ACTIVE in generated baseline | — | Lifecycle state field. |
| `tank.tank_id` | TEXT | yes / no | `TANK-nnn` | PK/FK → asset | Must refer to a TANK asset. Immutable. |
| `tank.facility_id` | TEXT | yes / no | Facility ID | FK → facility | Owning facility. |
| `tank.capacity_l` | REAL | yes / no | L | — | Positive maximum configured volume. |
| `tank.initial_level_l` | REAL | yes / no | L | — | Between zero and capacity, inclusive. |
| `tank.lifecycle_state` | TEXT | yes / no | ACTIVE in generated baseline | — | Lifecycle state field. |
| `valve.valve_id` | TEXT | yes / no | `VALVE-nnn` | PK/FK → asset | Must refer to a VALVE asset. Immutable. |
| `valve.facility_id` | TEXT | yes / no | Facility ID | FK → facility | Owning facility. |
| `valve.state` | TEXT | yes / no | OPEN/CLOSED/THROTTLED | — | Constrained enum. |
| `valve.opening_pct` | REAL | yes / no | 0–100% | — | Bounded valve opening. |
| `valve.lifecycle_state` | TEXT | yes / no | ACTIVE in generated baseline | — | Lifecycle state field. |
| `topology_node.node_id` | TEXT | yes / no | `NODE-<asset-id>` | PK; unique with facility | Immutable node ID. |
| `topology_node.facility_id` | TEXT | yes / no | Facility ID | FK → facility; composite endpoint key | Used to enforce pipe endpoint facility consistency. |
| `topology_node.asset_type` | TEXT | yes / no | PUMP/TANK | — | Must agree with the referenced asset type. |
| `topology_node.asset_id` | TEXT | yes / no | Canonical asset ID | FK → asset | Pump or tank represented by the node. |
| `pipe.pipe_id` | TEXT | yes / no | `PIPE-nnn` | PK/FK → asset | Must refer to a PIPE asset. Immutable. |
| `pipe.facility_id` | TEXT | yes / no | Facility ID | FK → facility | Must match both endpoint nodes and controlling valve. |
| `pipe.from_node_id` | TEXT | yes / no | Node ID | Composite FK with facility → topology node | Must differ from `to_node_id`; same facility. |
| `pipe.to_node_id` | TEXT | yes / no | Node ID | Composite FK with facility → topology node | Must differ from `from_node_id`; same facility. |
| `pipe.valve_id` | TEXT | yes / no | `VALVE-nnn` | Unique FK → valve | One controlling valve per pipe; facility must match. |
| `pipe.diameter_mm` | REAL | yes / no | mm | — | Positive pipe diameter. |
| `pipe.resistance` | REAL | yes / no | Model resistance coefficient | — | Positive coefficient used in simplified pressure/conductance calculations. |
| `pipe.lifecycle_state` | TEXT | yes / no | ACTIVE in generated baseline | — | Lifecycle state field. |
| `sensor.sensor_id` | TEXT | yes / no | `SNS-nnn` | PK/FK → SENSOR asset | Must identify a SENSOR asset in the same facility. Immutable. |
| `sensor.facility_id` | TEXT | yes / no | Facility ID | FK → facility | Must match both sensor identity asset and measured asset. |
| `sensor.asset_id` | TEXT | yes / no | Pump/Tank/Pipe ID | Composite FK → asset | FLOW may measure pump/pipe; PRESSURE pipe; LEVEL tank. |
| `sensor.measurement_type` | TEXT | yes / no | FLOW/PRESSURE/LEVEL | Part of unique sensor tuple | Determines compatible measured asset and unit. |
| `sensor.unit` | TEXT | yes / no | FLOW=`L/min`; PRESSURE=`kPa`; LEVEL=`L` | Part of unique sensor tuple | SQL CHECK and trigger enforce measurement-unit and target consistency. |
| `sensor.lifecycle_state` | TEXT | yes / no | ACTIVE in generated baseline | — | Lifecycle state field. |
| `simulation_run.simulation_run_id` | TEXT | yes / no | `SIM-2026-nnnnnn` | PK | Immutable run ID. |
| `simulation_run.seed` | INTEGER | yes / no | Integer | — | Seed used for deterministic master data and meter noise. |
| `simulation_run.profile` | TEXT | yes / no | starter/full | — | Requested output profile. |
| `simulation_run.status` | TEXT | yes / no | COMPLETED in generated output | — | Outcome of generation. |
| `simulation_run.start_timestamp` | TEXT | yes / no | UTC ISO-8601 | — | Inclusive simulation start. |
| `simulation_run.end_timestamp` | TEXT | yes / no | UTC ISO-8601 | — | Exclusive end; duration equals `steps × step_duration_minutes`. |
| `simulation_run.input_config_json` | TEXT | yes / no | Valid JSON | — | Stores effective steps, sensor/telemetry counts, seed, scenario, pump-speed schedule and run-specific facility/asset/pump/tank/pipe master snapshot for historical evaluation. |
| `ground_truth.simulation_run_id` | TEXT | yes / no | Run ID | Composite PK/FK → run | Associates label with exactly one run. |
| `ground_truth.scenario_id` | TEXT | yes / no | `SCN-...` | Composite PK | Unique scenario within a run. |
| `ground_truth.affected_asset_id` | TEXT | yes / no | Canonical asset ID | FK → asset | Asset associated with the expected episode. |
| `ground_truth.anomaly_type` | TEXT | yes / no | Six supported anomaly classes | — | Injected episode class. |
| `ground_truth.start_timestamp` | TEXT | yes / no | UTC ISO-8601 | — | Inclusive episode start. |
| `ground_truth.end_timestamp` | TEXT | yes / no | UTC ISO-8601 | — | Exclusive end; must follow start. |
| `ground_truth.expected_class` | TEXT | yes / no | Six supported classes | — | Expected detector classification. |
| `ground_truth.expected_decision` | TEXT | yes / no | Class/decision label | — | Expected outcome, retained for evaluation. |
| `ground_truth.severity` | TEXT | yes / no | HIGH/MEDIUM | — | Scenario severity. |
| `ground_truth.event_refs` | TEXT | yes / no | JSON array of event IDs | — | References injection and recovery events; label data is never read by detection. |
| `telemetry.telemetry_id` | TEXT | yes / no | `TEL-run-sequence` | PK | Immutable reading ID. |
| `telemetry.simulation_run_id` | TEXT | yes / no | Run ID | FK → run | Run that emitted the reading. |
| `telemetry.sensor_id` | TEXT | yes / no | Sensor ID | Composite FK → sensor tuple | Must agree with facility, measured asset, measurement type and unit. |
| `telemetry.facility_id` | TEXT | yes / no | Facility ID | FK → facility; composite sensor FK | Sensor’s facility. |
| `telemetry.asset_id` | TEXT | yes / no | Measured asset ID | Composite FK → asset and sensor | Must be the asset configured for that sensor. |
| `telemetry.timestamp` | TEXT | yes / no | UTC ISO-8601 | — | One-minute simulated sampling time. |
| `telemetry.measurement_type` | TEXT | yes / no | FLOW/PRESSURE/LEVEL | Composite FK → sensor | Must match sensor type. |
| `telemetry.value` | REAL | yes / no | Unit from sensor | — | No independent randomized process values; seeded noise is applied to simulated readings. |
| `telemetry.unit` | TEXT | yes / no | L/min, kPa, L | Composite FK → sensor | Must match sensor unit. |
| `telemetry.quality_status` | TEXT | yes / no | GOOD/SUSPECT/BAD | — | SENSOR_FAULT samples are SUSPECT. |
| `mass_balance.simulation_run_id` | TEXT | yes / no | Run ID | Composite PK/FK → run | Interval’s run. |
| `mass_balance.facility_id` | TEXT | yes / no | Facility ID | Composite PK/FK → facility | Facility balance owner. |
| `mass_balance.timestamp` | TEXT | yes / no | UTC ISO-8601 | Composite PK | Interval start. |
| `mass_balance.inflow_lpm` | REAL | yes / no | L/min | — | Simulated facility inflow. |
| `mass_balance.outflow_lpm` | REAL | yes / no | L/min | — | Simulated facility demand/outflow. |
| `mass_balance.storage_change_l` | REAL | yes / no | L per one-minute interval | — | Derived tank storage change. |
| `mass_balance.residual_l` | REAL | yes / no | L per interval | — | Balance residual, including controlled unexplained-loss cases. |
| `mass_balance.tolerance_l` | REAL | yes / no | L per interval | — | Positive configured comparison tolerance. |
| `operating_mode.mode_id` | TEXT | yes / no | `MODE-nn` | PK | Immutable mode ID. |
| `operating_mode.name` | TEXT | yes / no | NORMAL/HIGH_DEMAND/MAINTENANCE/STARTUP | Unique | Supported demand mode. |
| `operating_mode.demand_factor` | REAL | yes / no | Multiplier | — | Positive multiplier applied to modeled demand. |
| `alarm.prediction_id` | TEXT | yes / no | `PRED-run-window-sequence` | PK | Immutable prediction ID. |
| `alarm.simulation_run_id` | TEXT | yes / no | Run ID | FK → run | Run evaluated. |
| `alarm.affected_asset_id` | TEXT | yes / no | Canonical asset ID | FK → asset | Observable entity associated with alarm. |
| `alarm.detected_class` | TEXT | yes / no | Six supported classes | — | Detector output, independent of truth. |
| `alarm.severity` | TEXT | yes / no | HIGH/MEDIUM | — | Rule-derived severity. |
| `alarm.detection_timestamp` | TEXT | yes / no | UTC ISO-8601 | — | Timestamp of last observation sample in window. |
| `alarm.alert_emission_timestamp` | TEXT | yes / no | UTC ISO-8601 | — | Exclusive window-close time when alert becomes available. |
| `alarm.supporting_measurements` | TEXT | yes / no | JSON object | — | Evidence and episode-start timestamp used for event matching. |
| `alarm.rule_triggered` | TEXT | yes / no | Rule key | — | Explainable rule identifier. |
| `alarm.explanation` | TEXT | yes / no | Human-readable | — | Summary of observed evidence. |
| `state_event.event_id` | TEXT | yes / no | `EVT-run-sequence` | PK | Immutable event ID. |
| `state_event.simulation_run_id` | TEXT | yes / no | Run ID | FK → run | Run that experienced transition. |
| `state_event.asset_id` | TEXT | yes / no | Canonical asset ID | FK → asset | Transition owner. |
| `state_event.previous_state` | TEXT | yes / no | State/value text | — | State before transition. |
| `state_event.new_state` | TEXT | yes / no | State/value text | — | State after transition. |
| `state_event.effective_timestamp` | TEXT | yes / no | UTC ISO-8601 | — | Time transition becomes effective. |
| `state_event.reason` | TEXT | yes / no | Human-readable | — | Change reason; event rows cannot be updated or deleted. |
| `simulation_asset.simulation_run_id` | TEXT | yes / no | Run ID | Composite PK/FK → run | Participating run. |
| `simulation_asset.asset_id` | TEXT | yes / no | Canonical asset ID | Composite PK/FK → asset | Participating asset; exactly one pair per run and asset. |

## Sensor inventory and generated files

There are **172 sensors**: 60 pipe flow and 60 pipe pressure sensors, 30 tank level sensors, 20 pump flow sensors, plus redundant flow pickups `SNS-121` on `PIPE-001` and `SNS-172` on `PIPE-004`. The redundant measurements enable flatline-versus-process-change checks. The challenge requires flow, pressure and level sensing, not a fixed sensor total.

`ground_truth.csv` contains the same run and episode fields as the `ground_truth` table. `assets.csv` exports the canonical asset catalog; `simulation_assets.csv` exports run membership. `manifest.json` records generated artifact paths, byte sizes and SHA-256 hashes. The manifest excludes itself by definition; the exception is stated in the manifest. CSV telemetry and database constraints are described above.
