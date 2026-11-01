# Candidate review: YottaFlex Industrial Process Simulation

## Project overview

I worked on an industrial process simulator for the YottaFlex challenge. It models three connected facilities and creates telemetry that follows a simplified process model. The application can then inject known fault scenarios, look for them using rules, and compare its alerts with separately stored evaluation labels.

The goal is to make the data and the result traceable: a reading belongs to a sensor, asset, facility and simulation run; an alert includes its rule and supporting evidence; and a run can be checked against its exported records. This is an educational simulator, not a digital twin that can predict the behavior of a real plant.

## My contribution and project ownership

My contribution was to set the direction of the project and keep the work tied to the recruitment brief. I broke the challenge into phases: establish the required data model and baseline, make telemetry follow a process simulation, close acceptance gaps, then harden the evaluation and evidence. The prompt history records those changing priorities and the specific follow-up requests.

I directed the architecture toward Python with SQLite as the relational store and CSV, JSON and SQL as exchange and evidence formats. I used the challenge requirements to set priorities for the facility and equipment relationships, connected pipe topology, six anomaly scenarios, separate labels, repeatability and measurable evaluation. Codex carried out substantial implementation work; I did not independently write every application module.

I coordinated iterative development by asking for implementation, tests, technical audits and follow-up hardening. When the audit surfaced issues, I requested specific changes to the physical simulation, blockage behavior, pump operating changes, ground-truth isolation, event matching, latency reporting, database constraints, SQL import and manifest coverage. I also asked for reconciliation evidence and called out results that needed explanation, including evaluation units, asset counts and timing definitions.

I reviewed the reports and acceptance evidence instead of treating an initial successful run as proof that every requirement was met. I asked for limitations and partial criteria to remain visible, and for the small controlled evaluation not to be described as real-world accuracy. I also directed reproducibility, SQL round-trip, manifest and performance checks, then prepared documentation and publication requirements. The reports record those checks; this account does not mean I personally ran every command or independently verified every implementation detail.

ChatGPT assisted with planning, architecture discussions, drafting prompts for Codex and technical reviews. Codex was heavily involved in implementation and testing. The available prompt history is incomplete and does not include an exact ChatGPT transcript.

## How a run works

A run starts with seeded master data: facilities, equipment, sensors, pipe connections and operating settings. The generated topology has 60 pipes, each connecting two different nodes in the same facility. The three facility graphs are connected.

The simulator advances in one-minute steps. It calculates approximate pump output, pipe flow and pressure, tank storage changes and facility mass-balance values. It then creates sensor readings from those process values, with seeded measurement noise. A full run uses 172 sensors and 582 steps to emit exactly 100,000 telemetry records.

For the controlled full scenario, the generator injects 12 anomaly episodes: two severities for each of six anomaly types. It also records injection and recovery events. Ground-truth labels are saved separately from telemetry and detector inputs.

The detector examines telemetry and permitted equipment configuration using fixed rules. It produces alarms with a rule identifier, explanation, supporting measurements, last-sample detection time and alert-emission time. Evaluation runs detection first and reads ground truth afterward. It matches each alarm to at most one expected episode, then reports event results separately from false alarms in normal facility windows.

The application stores run data in SQLite and produces CSV, JSON and SQL outputs. Its manifest records file sizes and SHA-256 hashes for 25 declared artifacts; the manifest does not hash itself.

## Technology and technical decisions

The project uses Python 3.12 or later, a command-line interface, SQLite, CSV and JSON. Pytest is used for automated checks. The core runtime uses the Python standard library, with pytest as the test dependency.

A fixed random seed and deterministic identifiers make generated records repeatable for the same configuration. The simulator derives the number of time steps from the requested telemetry count and sensor inventory, rather than treating the requested row count as the number of steps. Database inserts are batched, and SQL export is streamed in batches. Detection currently reads telemetry from CSV into memory, which is one of the known scaling limits.

SQLite keys, foreign keys, composite constraints and triggers check important relationships. These include sensor and telemetry consistency, typed asset identity, pipe endpoints in the same facility, unique run-to-asset membership, immutable entity IDs, and append-only state-event records. Some lifecycle rules are checked in application validation rather than enforced as a database transition graph.

## Database relationships and topology

The canonical `asset` table holds facilities and typed equipment identities. Pump, tank, valve, pipe and sensor tables hold type-specific fields and refer back to those identities. A pipe connects two topology nodes, uses a controlling valve, and must stay within one facility. Sensors measure a configured asset; telemetry rows must match the sensor’s facility, target asset, measurement type and unit.

A simulation run has many telemetry, ground-truth, mass-balance, alarm and state-event records. Runs and assets have a many-to-many relationship through `simulation_asset`. Its composite key and foreign keys prevent duplicate or invalid memberships. In the full run, there are 345 canonical assets and 345 run-to-asset associations, with no missing, duplicate or invalid associations reported.

The asset total is made up of 3 facilities, 20 pumps, 30 tanks, 60 valves, 60 pipes and 172 sensors. The two extra sensors are redundant flow pickups on PIPE-001 and PIPE-004, used to help tell a sensor fault from a process-flow change.

## Architecture and database design review

I reviewed the architecture and data dictionary to understand how the entities fit together and checked the audit evidence for the important database relationships. The design uses a canonical asset identity with typed pump, tank, valve, pipe and sensor records. Pipes connect distinct topology nodes in the same facility and refer to a controlling valve. Sensors point to the asset they measure; telemetry is constrained to agree with the sensor on facility, asset, measurement type and unit.

I also reviewed the `simulation_asset` bridge design. It links a run to its participating assets with a composite primary key and foreign keys, so a pair cannot be duplicated and both sides must exist. State changes are recorded as append-only `state_event` rows, while primary-key updates are blocked. The schema uses primary keys, foreign keys, composite constraints and triggers to enforce these relationships.

The acceptance audit reports SQLite integrity checks, foreign-key checks, association reconciliation and a fresh SQL import. I reviewed those design documents and reported results as project evidence. That is different from a complete, line-by-line source-code review, which I have not claimed to perform.

## The six anomaly scenarios

- **LEAK:** Pipe flow falls while pressure also drops. The controlled injection adds unexplained branch loss.
- **BLOCKAGE:** Pipe resistance increases and conductance falls while the controlling valve stays open. The detector looks for lower flow and higher upstream pressure.
- **PUMP_DEGRADATION:** Measured pump flow falls below the rule’s threshold relative to rated flow at configured speed.
- **SENSOR_FAULT:** One flow pickup goes flat while a redundant measurement or asset flow changes. The rule classifies the problem as a sensor fault rather than a process fault.
- **TANK_OVER_CAPACITY:** A reported tank level exceeds configured capacity during the injected interval, then returns to its normal range.
- **FLOW_CONSERVATION_VIOLATION:** An unexplained flow drop exceeds the configured threshold without the pressure change expected for blockage, subject to a pump-shortfall exclusion.

Each type has a high and a medium controlled episode in the full run. These cases exercise the documented rules; they do not show how the rules would perform across the full range of real plant conditions.

## Ground truth and evaluation

Ground truth is stored in its own CSV and in run-specific SQLite rows. The detector function does not accept ground truth and does not read the labels file. Evaluation creates predictions first and loads labels afterward. Tests also check that detection does not access the ground-truth file.

One positive evaluation unit is one labeled episode, identified by affected asset, expected class and start time. An episode can match at most one alarm. A matched episode is a true positive; additional alarms for that episode and alarms with no match are false positives; unmatched episodes are false negatives. The reported normal controls use a different unit: a facility-by-control-window. Those false-alarm results are reported separately instead of combining two different units into one confusion matrix.

In the controlled full run, all 12 episodes were detected: 12 true positives, zero event false positives and zero missed episodes. There were zero false alarms across 12 normal facility windows. Each of the six types had two true positives and no false positives or missed episodes. This is a result on the defined test cases, not a general accuracy estimate.

The five-minute observation windows produce two latency measures. The final sample occurs four minutes after the episode start, so last-sample latency is four minutes. The alert is available when the half-open window closes, five minutes after the start, so operational alert-emission latency is five minutes.

## Testing, validation and reproducibility

The latest documented automated test result is **29 passed**. The suite includes checks for negative database cases, event matching, normal-window false alarms, ground-truth separation, configuration consistency, deterministic generation and manifest verification.

The Phase 4 full-run audit records 100,000 telemetry rows and these principal table counts: 3 facilities, 345 assets, 20 pumps, 30 tanks, 60 valves, 50 topology nodes, 60 pipes, 172 sensors, 1 simulation run, 12 ground-truth episodes, 1,746 mass-balance rows, 4 operating modes, 12 alarms, 38 state events and 345 simulation-asset associations.

The audit reports SQLite `integrity_check=ok`, no foreign-key violations, no sensor/telemetry tuple mismatches and no cross-facility pipe endpoint mismatches. A fresh in-memory database was created from the SQL schema and seed; all 16 tables’ source and imported rows matched, including telemetry and simulation-asset associations. The SQL seed file was 30,759,657 bytes. All 25 declared manifest artifacts passed path, size and checksum verification.

The audit also records repeat full runs with the same seed matching the checked deterministic outputs, including telemetry and evaluation artifacts. Runtime measurements can vary, so they are not treated as reproducibility checks. Reproducibility is tied to the same seed and configuration.

## Manual testing and validation

The acceptance audit records successful starter, full-profile, normal-only, anomaly, SQL-import, reproducibility, CLI and documentation checks. It records the automated suite as 29 passed and the full-profile results below. These are reported executions in the project evidence. I cannot claim from those reports alone that I personally ran the commands or inspected every output, so my own direct manual confirmation remains **pending**.

When I complete that confirmation, I can use the documented CLI commands with separate output directories so I do not overwrite the release evidence:

```powershell
python -m plant_sim generate --profile starter --seed 20261022 --output-dir outputs/candidate-check-starter
python -m plant_sim run --profile starter --scenario normal --seed 20261022 --output-dir outputs/candidate-check-normal
python -m plant_sim all --profile full --seed 20261022 --telemetry-count 100000 --output-dir outputs/candidate-check-full
python -m plant_sim validate --input-dir outputs/candidate-check-full
python -m plant_sim evaluate --input-dir outputs/candidate-check-full
python -m plant_sim verify-manifest --input-dir outputs/candidate-check-full
python -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP\plant-sim-candidate-check"
```

My checklist is to confirm that the starter output is produced; the normal run has no injected episodes or alarms; the full run has 100,000 telemetry rows and the six anomaly classes; validation and evaluation reports agree with the CSVs; the manifest checks pass; and the tests finish with the documented result. For SQL, I should import the schema and seed into a fresh database, compare row counts for all 16 tables, run `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, and check telemetry and `simulation_asset` relationships. For reproducibility, I should generate a second run with the same seed and configuration and compare deterministic outputs, not timings. I should also follow the README commands and check that the documented CLI options work.

Until I complete these steps myself, they remain a candidate follow-up checklist, not personal manual-test claims.

## Performance

The measured full run took 13.8953 seconds in the documented environment, with whole-run throughput of 7,196.7 telemetry rows per second. The reported exclusive stages were 0.2090 seconds for generation preparation, 1.9213 seconds for simulation, 6.3095 seconds for detection, 3.6963 seconds for database persistence, and 1.7591 seconds for validation and command-line/output overhead. Generation including simulation was 2.1303 seconds and is informational, not an additional stage to sum into the total. These are measurements from one execution, not a performance promise.

## Technical decisions and reasoning

I chose deterministic generation because a fixed seed and stable IDs make it possible to reproduce a run, compare changes and investigate a reported result. The step count is derived from the requested number of readings and the sensor count, which helps the full profile reach exactly 100,000 telemetry rows without confusing rows with time steps.

Ground truth is separate so the detector cannot use the answer as an input. Detection consumes telemetry and permitted equipment configuration; evaluation loads the labels after predictions have been made. That separation makes the controlled evaluation more meaningful and lets the project keep labels for audit without leaking them into the rules.

Rule-based detection fits this challenge because the six scenarios have observable, explainable signals and the requirement is to show traceable behavior. The rules can state why an alarm fired and can be compared with known injected episodes. The trade-off is that fixed thresholds work on the defined scenarios; they are not evidence of broad real-world detection performance.

A simplified physical model makes it practical to generate a connected, state-derived dataset for the challenge. The implementation weights flows by pipe conductance and uses simplified pressure and tank equations rather than solving network hydraulics. This keeps the model understandable and repeatable, but it omits important real-plant effects and must not be presented as a calibrated digital twin.

SQL export and fresh-database checks matter because they show that the persisted relationships can be reconstructed outside the original SQLite file. Deterministic comparisons and manifest hashes make it easier to identify whether generated evidence changed. Those checks improve traceability; they do not prove that every model assumption is physically correct.

I chose to keep limitations explicit because a small fixed test set cannot support claims of operational accuracy. Documenting the uncalibrated noise, simplified physics, fixed windows, memory use and lifecycle enforcement boundary gives reviewers a clearer account of what the system does and what would need further work.

## Limitations and trade-offs

The flow model allocates flow using conductance weights rather than solving full network hydraulics. Pressure response is simplified and local, tank demand and inflow are split equally, and sensor noise is seeded but not calibrated against real instruments. The model does not represent elevation, fluid properties, transient waves, cavitation, detailed pump curves or closed-loop control.

The anomaly windows and thresholds are fixed. The controlled evaluation has only 12 anomaly episodes and 12 normal facility windows, so it cannot establish operational accuracy. The detector loads the telemetry CSV into memory. Lifecycle transition rules are checked by application code but are not enforced as a full transition graph in SQLite. Performance timings vary between runs and environments.

## AI assistance disclosure

Codex was heavily involved in implementation and testing. I used it to build and revise the simulator, database constraints, anomaly rules, CLI behavior, automated tests and documentation, and to run verification work. ChatGPT assisted with project planning, architecture, drafting implementation prompts for Codex and technical reviews.

The prompt-history document records the available Codex prompts and explains that the exact ChatGPT prompt transcript was unavailable. I am disclosing that limitation rather than presenting the work as independent implementation. The documented test and audit results are evidence from the project; they do not mean I have mastered every part of the implementation or completed an independent code review.

## Final reflection

This project has taught me that coordinating AI-assisted engineering means doing more than asking for code. I had to translate the challenge into phases, keep the requested behavior specific, follow up when audits found gaps, and ask for evidence around data integrity and evaluation. Codex did substantial implementation and testing, and ChatGPT helped me plan and review the work. I still need to study the implementation closely so I can explain the choices and constraints accurately. I can present the reported results, but I will distinguish them from checks I have personally completed and from claims the evidence cannot support.

## My preparation for technical discussion

Before a technical discussion, I need to study and be ready to explain:

- How the simulator’s pump, conductance, pressure, tank and mass-balance calculations work, including where they simplify real physics.
- How sensor-to-asset and telemetry constraints are enforced in SQLite, including the composite keys and triggers.
- How one-to-one event matching handles duplicate alarms, unmatched alarms and missed episodes.
- Why ground truth is kept out of detector inputs and how the tests check that boundary.
- How deterministic IDs, seeded noise, run configuration and manifest checksums support repeatable runs.
- What the pytest suite covers and what remains only partially covered.
- How I would extend the physical model and test the detector on larger, more varied scenarios.
