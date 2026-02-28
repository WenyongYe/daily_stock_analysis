## ADDED Requirements

### Requirement: Multi-source news fusion with deterministic filtering
The system SHALL aggregate news from RSS primary sources and search providers, deduplicate by normalized title/url, and produce a deterministic ranked list.

#### Scenario: RSS and search both available
- **WHEN** RSS fetch and Tavily search both return results
- **THEN** the system merges both streams and removes duplicate headlines before ranking

#### Scenario: Search provider unavailable
- **WHEN** Tavily/Brave keys are unavailable or search call fails
- **THEN** the system SHALL continue using RSS-only data without terminating the report generation

### Requirement: Priority scoring for each news item
The system SHALL compute an `importance_score` for each item using category weight, source reliability, domain reliability, breaking keywords, macro/geopolitical keywords, and recency.

#### Scenario: High quality source with macro signal
- **WHEN** a Reuters/FT/CNBC article mentions Fed/CPI/rates with recent timestamp
- **THEN** the system assigns a higher importance score than generic index pages or low-context aggregation pages
