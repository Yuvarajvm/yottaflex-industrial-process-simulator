# Final technical acceptance audit

Audit target: the Phase 4 full run in `outputs/phase4-audit-release`, generated with seed 20261022 and 100,000 requested telemetry rows. Statuses describe evidence in the implementation and generated artifacts, not a claim of production-grade physical accuracy.

## Original YottaFlex challenge requirement matrix

| Original requirement | Status | Evidence and remaining limit |
|---|---|---|
| Industrial process simulation, monitoring, traceability and measurable evaluation | PASS | Generator, detector, validation, event scoring and separate ground truth are implemented. |
| Python 3.12+, SQLite, CSV, JSON and pytest; standard-library core | PASS | `pyproject.toml` requires Python >=3.12; runtime audit used Python 3.13.5. Pytest is the only runtime test dependency. |
| 3 facilities, 20 pumps, 30 tanks, 60 valves, 60 pipes and at least 60 connections | PASS | Full output has exact master counts and 60 valid pipe connections. |
| Sensors for flow, pressure and level | PASS | 172 total: 60 pipe flow, 60 pipe pressure, 30 tank level, 20 pump flow, and 2 redundant pipe flow pickups. No exact sensor count is prescribed by the original challenge. |
| Exactly 100,000 full-profile telemetry readings and a smaller same-logic starter | PASS | Full run has exactly 100,000; starter run has 7,000. Both use the same time-stepped generator. |
| Fixed-seed generation, deterministic zero-padded IDs and stable references | PASS | Seed 20261022 and deterministic ID functions; repeated full runs match deterministic CSV hashes, truth, alarms, evaluation, validation and run configuration. IDs are protected against key updates in SQLite. |
| Ten core relational entities plus topology, bridge and event support | PASS | SQLite contains Facility, Asset, Pump, Tank, Valve, Pipe, Sensor, Telemetry, OperatingMode, Alarm, SimulationRun, TopologyNode, GroundTruth, SimulationAsset, StateEvent and MassBalance. |
| Primary/foreign keys and valid joins | PASS | Fresh schema has PK/FKs, composite sensor/telemetry identity, run/asset bridge, same-facility endpoints, and typed-asset consistency triggers. Direct SQLite rejection tests cover invalid telemetry references, sensor/asset mismatch, and cross-facility pipe endpoints. |
| Optionality, relationship cardinality, lifecycle and effective-time documentation | PARTIAL | Cardinalities and effective timestamps are documented. Generated relational columns are required. Lifecycle transition policy is application-validated; SQLite stores lifecycle values but does not enforce the transition graph. |
| Explicit units and UTC timestamps | PASS | L/min, kPa, L, mm, percent and ISO-8601 UTC are documented and checked for sensor/unit consistency. |
| Connected topology; reject self-links, missing nodes and invalid references | PASS | All three generated facility graphs connect; validator and SQL constraints/triggers reject invalid endpoints and cross-facility joins. |
| Derived pump, pipe, pressure, tank, facility flow and balance values | PARTIAL | Values derive from simplified conductance, resistance, pump output, operating modes and tank storage equations. Equal tank allocation, simplified local pressure response and uncalibrated noise mean this is not a full hydraulic solver. |
| Baseline before operating changes; preserve input config and state history | PASS | Initial five minutes precede fault episodes. Effective step count, sensor/telemetry counts and detector-relevant master snapshot are persisted per run. Pump speed, blockage, mode, injection and recovery transitions are recorded. State events are append-only in SQLite. |
| Pump speed, valve and operating-mode changes | PASS | Blockage changes pipe resistance while its controlling valve stays OPEN. A distinct PUMP-001 speed increase and restoration are modeled and event-recorded when the run is long enough. Modes are NORMAL, HIGH_DEMAND, MAINTENANCE and STARTUP. |
| Six required anomaly scenarios, deterministic injection and explanations | PASS | LEAK, BLOCKAGE, PUMP_DEGRADATION, SENSOR_FAULT, TANK_OVER_CAPACITY and FLOW_CONSERVATION_VIOLATION each have high and mild telemetry episodes, labels, rule evidence and recovery events. Two detections per class in the full controlled run. |
| Ground truth separate from detector input | PASS | Ground truth is stored separately in CSV and per-run SQLite records. A test guards detector file access; evaluation calls prediction generation before reading labels. |
| Required malformed inputs, negative cases, and failure/recovery tests | PARTIAL | Tests cover missing nodes/config/required fields, duplicate IDs and bridge pairs, bad valve/pump values, over-capacity level, mass residual, lifecycle/date validation, invalid SQLite FKs/relationships, immutable IDs/events, sensor-fault classification, normal false alarms and scenario recovery records. Some validator cases are helper-level rather than a dedicated end-to-end malformed database fixture; lifecycle transition rules are not database triggers. |
| Event TP/FP/FN, per-class metrics, normal false alarms and latency | PASS | One-to-one event matching; duplicate and unmatched alarms are FPs, missed episodes are FNs. Normal facility-window false alarms are reported separately, with total alarms and hit-window rate. Per-class precision/recall/F1 and both latency definitions are reported. |
| Evaluation duration, throughput, connectivity, integrity and reconciliation | PARTIAL | Duration/throughput are in `performance.json`; topology and database checks are in validation/database summaries rather than the evaluation JSON itself. Full records reconcile and those reports are included. |
| CSV/JSON exports, SQLite, SQL schema/seed, manifest and reproducibility hashes | PASS | Full output includes CSV data, ground truth, alarms, evaluation/validation/performance JSON, SQLite, checksums, and a manifest. After SQL export the manifest covers both SQL files. Manifest self-hash is documented as excluded. |
| Batched inserts and avoid loading telemetry fully into memory | PARTIAL | Telemetry and mass-balance DB inserts are streamed in batches of 10,000; SQL export streams 5,000 rows at a time. The detector currently loads the input telemetry CSV fully into memory, so the requirement to avoid full-memory telemetry loading is not met. |
| Professional src project, CLI, README and documentation | PASS | CLI help and all documented app commands were exercised. Data dictionary covers every core/supporting relational field and documents the 172-sensor inventory. |
| Repeat generation and compare deterministic outcomes | PASS | Two 100,000-row full runs matched checksums, telemetry, ground truth, alarms, evaluation, validation, state events, bridges and run configuration. Performance timings are excluded from deterministic comparisons. |
| Complete automated coverage and actual full-scale evidence | PARTIAL | 29 tests pass, including exact full telemetry count and a starter SQL round-trip; this audit additionally ran a fresh full-profile SQL import. The complete original negative-case list is not represented by a separate end-to-end test for every possible malformed value. |
| README installation, commands, examples, database, metrics and limitations; complete data dictionary | PASS | README and the requested architecture, assumptions, rules, data dictionary and acceptance audit are updated. Physical limitations and controlled-set limits are explicit. |
| Do not invent licensing/ownership | PASS | No LICENSE file is included. |

## Phase 4 full-run evidence

### Dataset and database counts

| Table | Rows |
|---|---:|
| facility | 3 |
| asset | 345 |
| pump | 20 |
| tank | 30 |
| valve | 60 |
| topology_node | 50 |
| pipe | 60 |
| sensor | 172 |
| simulation_run | 1 |
| ground_truth | 12 |
| telemetry | 100,000 |
| mass_balance | 1,746 |
| operating_mode | 4 |
| alarm | 12 |
| state_event | 38 |
| simulation_asset | 345 |

Canonical asset types are FACILITY=3, PUMP=20, TANK=30, VALVE=60, PIPE=60, SENSOR=172, total=345. Every participating asset has exactly one association in the one full-run bridge. Duplicate, missing and invalid bridge references are all zero. Database validation reports `integrity_check=ok`, zero foreign-key violations, zero sensor/telemetry tuple mismatches and zero cross-facility pipe endpoint mismatches. The 10 over-capacity readings are the expected controlled tank episode. There are 15 mass-balance intervals beyond the 10 L tolerance and 2 corresponding detected violation alarms.

The run configuration reports 172 sensors and **582 one-minute steps**, derived as `ceil(100,000 / 172)`. The run starts at 00:00 UTC and ends at the exclusive 09:42 UTC boundary. `steps=20` is no longer emitted as the effective count.

### Evaluation evidence

Event unit: one labeled episode `(affected asset, expected class, start timestamp)`. An alarm can match at most one episode. A first matching alert is a TP; another alert for that episode or an unmatched alert is an FP; an unmatched ground-truth episode is an FN.

Event metrics: **12 TP, 0 FP, 0 FN**, precision=1.0, recall=1.0 and F1=1.0. Each of the six classes has TP=2, FP=0 and FN=0. These are deliberately controlled cases, not general accuracy evidence.

Normal controls are a separate unit: facility × control interval. There are **12 normal windows**, 0 with alarms, a 0.0 false-alarm window rate, and 0 total normal false alarms. No conventional confusion matrix combines normal-window units with event units.

All 12 event latencies are 4 minutes to the last sample (minute 9 or 19) and 5 minutes to operational alert emission (the exclusive window close at minute 10 or 20). The four-to-five-minute difference is the final interval between the last sample and window close.

### SQL import and manifest

`sql/seed_data.sql` is 30,759,657 bytes. It was imported with `sql/schema.sql` into a fresh in-memory SQLite database. Source and imported row counts and complete rows match in all 16 tables; every primary key is unique; `foreign_key_check` is empty; `integrity_check` returns `ok`. Telemetry reconciles at 100,000 rows and simulation-asset pairs at 345. Ground truth is included as the run-specific `ground_truth` table and is also exported as CSV.

The manifest has **25 declared artifacts** and verifies every path, byte size and SHA-256 value, including CSVs, ground truth, evaluation/validation/performance JSON, SQLite, SQL schema and SQL seed. `verify-manifest` reports valid with no errors. `manifest.json` itself is deliberately not hashed.

### Automated and CLI verification

The suite result is **29 passed** using a unique temporary directory. In this Windows environment, pytest’s default temporary directory returned `WinError 5`; rerunning with an explicit temporary base succeeded. Direct SQLite tests reject invalid telemetry FKs, sensor/asset mismatch, cross-facility pipe endpoints, primary-key changes, and state-event update/delete. Evaluation tests verify duplicate alarms, unmatched alarms, missed episodes and normal false-alarm-window aggregation. Run-ID tests evaluate two historical runs with different seeds from each run’s master snapshot and reject an unknown ID.

The documented `generate`, normal-only `run`, full `all`, `validate`, run-selected `evaluate`, `export-sql`, `verify-manifest`, and help commands were exercised. Ground-truth isolation and full-seed reproducibility were checked. A normal-only run emitted 7,000 telemetry rows, no ground-truth episodes, no alarms and zero mass-balance intervals over tolerance.

### Measured full-run performance

| Exclusive stage | Seconds |
|---|---:|
| Generation preparation | 0.2090 |
| Simulation | 1.9213 |
| Detection | 6.3095 |
| Database persistence | 3.6963 |
| Validation and CLI/output overhead | 1.7591 |
| **Total** | **13.8953** |

Whole-run telemetry throughput was 7,196.7 rows/s. Generation inclusive of simulation was 2.1303 s and is informational, not additive. These are measured values from this execution, not a performance guarantee.

## Remaining limitations

The flow and pressure model is an educational conductance approximation; tank allocation is equal, local blockage head response is simplified, and noise is uncalibrated. Scenario windows and thresholds are fixed and the evaluation set is small. Lifecycle-transition rules are validated in application code but not enforced as a transition graph in SQLite. Detection currently loads the telemetry CSV into memory. These limits do not invalidate the controlled evidence above, but they prevent a claim of production accuracy or complete general-purpose acceptance.
