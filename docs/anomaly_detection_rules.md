# Anomaly detection rules and evaluation

`plant_sim.detection.detect` reads telemetry, run metadata, sensor inventory, pump nominal capacity/speed, tank capacities and pipe configuration. It never accepts or opens ground truth. `evaluate` completes predictions first and loads labels afterward.

The detector scans the five-minute half-open episodes beginning at minutes 5 and 15, using the preceding five minutes as the reference. Normal controls are evaluated separately in minutes 0–5, 25–30, 30–35 and 35–40.

| Class | Observable rule |
|---|---|
| LEAK | Pipe flow drops by more than 1.5% and pressure drops by more than 10 kPa. |
| BLOCKAGE | Pipe flow drops by more than 20% and upstream pressure rises by more than 25 kPa. Injection raises pipe resistance/reduces conductance; the valve remains OPEN. |
| PUMP_DEGRADATION | Pump meter mean is below 90% of rated flow at configured speed. |
| SENSOR_FAULT | One flow sensor is flat over the episode while redundant pickup/asset flow changes beyond `max(2 L/min, 1.5%)`. It is classified as sensor fault rather than process fault. |
| TANK_OVER_CAPACITY | Any measured tank level exceeds configured capacity. |
| FLOW_CONSERVATION_VIOLATION | Unexplained branch flow drop exceeds 10 L/min without corresponding pressure change, excluding facilities already showing a nominal pump-curve shortfall. |

An alarm has `detection_timestamp` at the final observation sample and `alert_emission_timestamp` at the exclusive window close. Thus these five-minute windows report four-minute last-sample latency and five-minute operational emission latency from the episode start.

## Scoring units

Positive event scoring uses one ground-truth episode identified by `(affected_asset_id, expected_class, start_timestamp)`. An alarm matches at most one episode. A first matching alarm is a TP; additional alarms for that same event and any unmatched alarm are FPs; unmatched episodes are FNs. Duplicate alarms are not collapsed. Precision, recall and F1 are calculated from these event-level counts, including per-class values.

Normal controls are not combined with episode counts in a conventional confusion matrix. Their separate metrics count all false-alarm predictions, the number of facility/control windows with at least one alarm, and the false-alarm window rate. This avoids mixing an episode unit with a facility-window unit.

The full controlled run has 12 injected episodes (two per class), 12 normal facility/control windows, TP=12, event FP=0, FN=0, and zero false alarms across the normal windows. The set is intentionally small and fixed; it demonstrates rule paths, not general detection accuracy.
