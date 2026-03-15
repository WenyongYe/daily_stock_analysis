## ADDED Requirements

### Requirement: Persist daily yield curve snapshots for history tracking
The system SHALL persist each daily yield-curve snapshot into SQLite for traceability and backtesting.

#### Scenario: New daily snapshot arrives
- **WHEN** MacroProvider receives a valid `yield_curve` payload
- **THEN** it upserts one row keyed by `observation_date` into `yield_curve_daily`

#### Scenario: Snapshot for existing date re-fetched
- **WHEN** a snapshot with an existing `observation_date` is fetched again
- **THEN** the row is updated in-place and `updated_at` is refreshed

### Requirement: Persist validation and raw payload
The history table SHALL preserve validation context for audit and diagnosis.

#### Scenario: Snapshot persisted
- **WHEN** writing to `yield_curve_daily`
- **THEN** the record stores `validation_json` and `raw_json` fields in addition to rates/spreads
