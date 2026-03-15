### Requirement: Generate options flow briefing with news enrichment

The system SHALL aggregate extracted option flow items and generate a briefing with possible drivers based on web search.

#### Scenario: Aggregate and rank
- **WHEN** option flow items are collected
- **THEN** the system SHALL group by ticker/expiry/strike/type
- **AND** rank top symbols by premium/volume/volume-oi ratio

#### Scenario: News enrichment
- **WHEN** top symbols are identified
- **THEN** the system SHALL run web search queries per symbol
- **AND** use LLM to summarize 2-3 possible drivers per symbol

#### Scenario: Report delivery
- **WHEN** the report is generated
- **THEN** it SHALL be saved to `reports/options_flow_YYYYMMDD.md`
- **AND** optionally pushed to Feishu or other configured channels
