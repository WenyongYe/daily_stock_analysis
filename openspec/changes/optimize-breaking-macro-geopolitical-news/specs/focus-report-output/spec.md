## ADDED Requirements

### Requirement: Focused intelligence output for market report
The report SHALL include a curated news section limited to a configurable range (default 15 items), grouped by category and ordered by priority.

#### Scenario: Normal operating day
- **WHEN** multiple sources return large result sets
- **THEN** the report outputs only top-priority items and preserves category grouping order

#### Scenario: Thin-data day
- **WHEN** strict threshold filtering yields too few results
- **THEN** the system performs controlled backfill from ranked candidates while still respecting source/category caps

### Requirement: Reliable fallback behavior
The system SHALL fallback to FT market headlines if both RSS and search sources provide no usable records.

#### Scenario: Multi-source outage
- **WHEN** RSS parsing fails and search provider is unavailable
- **THEN** the report still includes fallback FT headlines instead of leaving an empty news section
