## ADDED Requirements

### Requirement: Three-tier classification framework with quantitative thresholds
The knowledge base SHALL define quantitative thresholds for 🔴🟡🔵 classification tied to expected asset price movements.

#### Scenario: Framework loaded by LLM
- **WHEN** the LLM receives the analysis_framework.md content
- **THEN** it applies the defined thresholds: 🔴 for events likely to move major assets >1%, 🟡 for notable but non-critical updates, 🔵 for commentary and opinions

### Requirement: Multi-source confirmation rules
The knowledge base SHALL define rules for single-source vs multi-source confirmation labeling.

#### Scenario: Single source event
- **WHEN** only one account reports an event
- **THEN** the LLM labels it with a single-source warning indicator

#### Scenario: Multi-source confirmed event
- **WHEN** two or more accounts report the same event
- **THEN** the LLM labels it as multi-source confirmed

### Requirement: Account profiles with source weights
The knowledge base SHALL define each monitored account's type, reliability weight, and content characteristics.

#### Scenario: Source-aware analysis
- **WHEN** the LLM processes tweets from different accounts
- **THEN** it applies source-specific weights: breaking news accounts can trigger 🔴, analysis accounts are limited to 🟡🔵

### Requirement: Few-shot prompt templates
The knowledge base SHALL include at least 3 few-shot examples covering different briefing scenarios.

#### Scenario: Template-guided output
- **WHEN** the LLM generates a briefing
- **THEN** the output format matches the provided templates for structure, tone, and detail level
