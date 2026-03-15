## ADDED Requirements

### Requirement: Official rates snapshot with single-source consistency
The system SHALL provide a unified rates snapshot using official sources, where 2Y/10Y/3M are derived from the same source family and the same observation date.

#### Scenario: FRED available
- **WHEN** FRED series `DGS3MO`, `DGS2`, `DGS10` are available
- **THEN** the system returns a snapshot with `source_primary=fred` and shared `observation_date`

#### Scenario: Treasury validation available
- **WHEN** Treasury daily curve data is available for the same date
- **THEN** the snapshot includes validation metadata (`matched_date`, rate diffs in bp)

#### Scenario: Official sources unavailable
- **WHEN** both FRED and Treasury fetch fail
- **THEN** the system falls back to yfinance and marks `quality=fallback`

### Requirement: Explicit rate metadata for downstream consumers
The snapshot SHALL include source/date/quality metadata required for auditability.

#### Scenario: Snapshot produced
- **WHEN** a rates snapshot is returned
- **THEN** it includes `source_primary`, `source_secondary`, `observation_date`, `asof_utc`, `quality`, and `stale_days`
