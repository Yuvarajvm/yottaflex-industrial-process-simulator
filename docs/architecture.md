# Architecture

`config.py` derives the one-minute step count from requested telemetry and the deterministic sensor inventory. `generator.py` creates master data, a connected topology, physical-state-derived telemetry, mass-balance intervals, state events, run-specific ground truth and deterministic hashes. `physics.py` contains pump, valve, pipe, tank and residual equations. `topology.py` checks facility graphs. `validation.py` checks generated records, membership and duration/configuration consistency.

`detection.py` consumes telemetry and permitted equipment configuration only. It has no ground-truth parameter. Each alarm stores the last sample timestamp and the exclusive observation-window close timestamp. `evaluation.py` completes detection before reading labels, performs one-to-one episode matching, and reports positive event metrics separately from negative facility-window false-alarm metrics.

`database.py` persists canonical entities and telemetry in batches. Each run stores its detector-relevant master-data snapshot and its own `ground_truth` rows, so historical `evaluate --run-id` calls use that run’s telemetry, equipment configuration and labels even if later runs use different seeds. It enforces composite sensor/telemetry consistency, same-facility pipe endpoints, unique run/asset associations, immutable primary keys, and append-only state events. The INSERT-only SQL exporter emits tables in foreign-key dependency order.

`manifest.py` lists important generated artifact paths, byte sizes and SHA-256 hashes. The final `all` output includes CSVs, evaluation/validation/performance JSON and SQLite. SQL schema and seed files are added to the manifest when SQL export runs. `manifest.json` excludes itself because it cannot contain its own stable hash.

## Relational relationships

- Facility 1:N canonical Asset; Facility 1:N typed equipment and topology nodes.
- Asset 1:1 typed Pump, Tank, Valve, Pipe or Sensor by shared immutable ID.
- Pipe N:1 controlling Valve; each pipe has two different same-facility topology nodes.
- Sensor 1:N Telemetry. A composite relationship enforces the sensor, measured asset, facility, measurement type and unit as one consistent tuple.
- SimulationRun 1:N Telemetry, GroundTruth, MassBalance, Alarm and StateEvent.
- SimulationRun N:M Asset through `simulation_asset`, which has a composite primary key and both foreign keys.
- GroundTruth references its affected asset and run; event references are retained as JSON IDs for audit.
- OperatingMode is a reusable lookup; facility mode transitions are recorded as immutable events.

All current entity/association fields are required. State events have effective timestamps; run end time is exclusive and equals one-minute steps times step duration. Lifecycle validation is application-level for transitions, while state-event storage is append-only in SQLite.
