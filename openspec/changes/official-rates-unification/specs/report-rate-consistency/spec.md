## ADDED Requirements

### Requirement: Report-level consistency check for 2Y-10Y spread
The market report SHALL verify that displayed spread equals `(10Y - 2Y) * 100` under the same snapshot.

#### Scenario: Complete rates available
- **WHEN** `2Y`, `10Y`, and `spread_2y10y_bp` are all present
- **THEN** report output includes pass/fail consistency status and the bp delta

#### Scenario: Missing key tenor
- **WHEN** `2Y` or `10Y` is missing
- **THEN** report output explicitly states spread is unavailable due to missing same-source tenors

### Requirement: Explicit source/date annotation in rate section
The report SHALL print rate source and observation date to prevent mixed-timestamp interpretation.

#### Scenario: Yield curve section rendered
- **WHEN** market daily report builds bond section
- **THEN** it includes `source` and `observation_date` (and stale days when available)

### Requirement: Theme analysis uses bp field consistently
Theme generation SHALL use `spread_2y10y_bp` (not percent-style fields) to avoid unit mismatch.

#### Scenario: Curve inversion detected
- **WHEN** `spread_2y10y_bp < 0`
- **THEN** theme/watch text displays inversion in bp units
