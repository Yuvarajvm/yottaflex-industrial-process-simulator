# YottaFlex Round 2: Industrial Process Monitoring & Simulation

A deterministic educational simulator for connected process networks. It generates physical-state-derived telemetry, injects controlled scenarios, detects anomalies without reading ground truth, evaluates event-level performance, and persists run-specific evidence in SQLite. It is not a calibrated plant digital twin.

## Install and run

Requires Python 3.12 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m plant_sim generate --profile starter --seed 20261022 --output-dir outputs/phase4-starter
python -m plant_sim run --profile starter --scenario normal --seed 20261022 --output-dir outputs/phase4-normal-accepted
python -m plant_sim all --profile full --seed 20261022 --telemetry-count 100000 --output-dir outputs/reproduced-full
python -m plant_sim validate --input-dir outputs/reproduced-full
python -m plant_sim evaluate --input-dir outputs/reproduced-full --run-id SIM-2026-000001
python -m plant_sim export-sql --db outputs/reproduced-full/simulation.sqlite --output outputs/reproduced-full/seed_data.sql
python -m plant_sim verify-manifest --input-dir outputs/reproduced-full
python -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP\plant-sim-phase4-tests"
```

The full profile emits exactly 100,000 telemetry rows. With the current 172-sensor inventory, that requires 582 one-minute steps. Starter defaults to 7,000 rows and 41 steps. The step count is derived from requested telemetry and sensor inventory and is recorded in the run configuration. A fixed seed of `20261022` is the default. Repeated runs with the same configuration reproduce deterministic data and checksums; measured timings are expected to vary.

The inventory has 3 facilities, 20 pumps, 30 tanks, 60 valves, 60 pipes, and 172 sensors. Two additional flow pickups on `PIPE-001` and `PIPE-004` provide redundant measurements for the two sensor-fault episodes. The challenge does not require a fixed sensor count.

## Simulation and operating changes

The simulation advances in one-minute intervals. Flow is in L/min, stored volume in L, pressure in kPa, diameter in mm, pump speed in percent, and timestamps are ISO-8601 UTC. Pump output follows rated capacity × speed × efficiency. Pipe conductance weights use diameter, resistance, topology degree and valve state. Pressure includes a simplified resistance-based drop. Tank levels and facility residuals are derived from process flows, losses and storage change. A seeded random generator adds noise to readings after physical values are calculated.

Each anomaly class has high and mild injected episodes with recovery events. Blockage raises effective pipe resistance and reduces conductance; its controlling valve remains OPEN. A separate scheduled operating change raises `PUMP-001` speed from its configured value to 100% during minutes 45–50, then restores it, with both transitions recorded as events. It is only present when the generated run is long enough to contain the full change and recovery.

The detector reads telemetry and permitted equipment configuration. It never opens `ground_truth.csv`. Evaluation creates predictions first, then loads labels. Positive evaluation is one ground-truth episode matched to at most one alarm. Duplicate and unmatched alarms count as event-level false positives; missed episodes count as false negatives. Normal controls are reported separately as facility-by-window false-alarm metrics, not combined into the event confusion matrix.

Latency has two meanings: last-sample latency timestamps the final sample in the half-open observation window (4 minutes here); operational alert-emission latency timestamps the window close (5 minutes here). The latter includes the remaining minute after the last sample.

Current controlled evaluation results are 12 TP, 0 event FP, and 0 FN across 12 injected episodes, plus 0 false alarms across 12 normal facility windows. Those results are evidence that the defined cases work; the sample is too small and structured to establish operational accuracy.

## Outputs and integrity

Generation writes master, topology, telemetry, mass-balance, state-event, simulation-asset, and separate ground-truth CSVs. The `all` command adds alarms, evaluation, validation, performance and manifest JSON, plus SQLite. Ground truth is also persisted in SQLite per run so `evaluate --run-id` can select historical run evidence. Unknown run IDs return an error.

The relational schema enforces run/asset bridge uniqueness, sensor-to-observed-asset and measurement consistency, same-facility pipe endpoints, immutable primary keys, and append-only state-event history. SQL export is generated from persisted SQLite rows. The reproduction commands write generated SQL to `outputs/reproduced-full/seed_data.sql` so they do not overwrite the bundled seed or Phase 4 release evidence. To import the bundled SQL into a fresh database, apply `sql/schema.sql`, then execute `sql/seed_data.sql`.

The manifest lists artifact paths, sizes and SHA-256 checksums for generated CSV/JSON/SQLite files and, after SQL export, the SQL schema and seed. It excludes itself because a file cannot contain its own stable hash. `python -m plant_sim verify-manifest --input-dir outputs/full` verifies all declared artifact paths, sizes and hashes.

See [architecture](docs/architecture.md), [data dictionary](docs/data_dictionary.md), [simulation assumptions](docs/simulation_assumptions.md), [anomaly rules](docs/anomaly_detection_rules.md), and the [acceptance audit](docs/acceptance_audit.md). The [AI prompt history](docs/ai_prompt_history.md) distinguishes recovered prompts from unavailable history.

Limitations include approximate network flow weighting rather than a hydraulic solver, equal tank allocation, independent uncalibrated sensor noise, fixed scenario windows, and rules tuned to the controlled cases.
