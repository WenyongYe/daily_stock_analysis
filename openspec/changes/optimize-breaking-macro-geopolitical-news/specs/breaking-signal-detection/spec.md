## ADDED Requirements

### Requirement: Breaking/macro/geopolitical signal amplification
The system SHALL prioritize news containing breaking-event and macro/geopolitical risk signals (e.g., war, sanctions, FOMC, inflation, payroll, supply shock).

#### Scenario: Geopolitical escalation headline
- **WHEN** a headline includes conflict/sanction/shipping disruption terms
- **THEN** the scoring model SHALL boost the item and classify it under 地缘风险 when applicable

#### Scenario: Macro policy headline
- **WHEN** a headline includes Fed/FOMC/CPI/payroll/rate language
- **THEN** the scoring model SHALL boost the item and classify it under 央行政策 when applicable

### Requirement: Bounded output with anti-monopoly constraints
The system SHALL enforce per-source and per-category caps so one source or one category cannot dominate the final set.

#### Scenario: Single-source flood
- **WHEN** one feed returns dozens of items
- **THEN** the final output limits items from that source and backfills from other high-score sources/categories
