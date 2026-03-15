## ADDED Requirements

### Requirement: Skill triggers on twitter news analysis requests
The system SHALL activate the twitter-news-briefing skill when the user requests twitter financial news analysis, briefing generation, or tweet summarization.

#### Scenario: User requests briefing
- **WHEN** user says "分析推特快讯" or "生成推特简报" or "twitter news briefing"
- **THEN** the skill activates and follows the defined analysis workflow

### Requirement: Skill loads references dynamically
The system SHALL load analysis framework, account profiles, and prompt templates from references/ files at runtime.

#### Scenario: References available
- **WHEN** the skill is triggered and references/ files exist
- **THEN** the analysis uses the loaded framework, profiles, and templates

#### Scenario: References missing fallback
- **WHEN** references/ files are missing or corrupted
- **THEN** the system falls back to a built-in default prompt without error

### Requirement: Skill integrates with existing CLI pipeline
The system SHALL support both agent-triggered and CLI-triggered execution paths using the same skill references.

#### Scenario: CLI execution
- **WHEN** `twitter_news_run.py` is executed via CLI or cron
- **THEN** `analyzer.py` loads the same references/ files used by the skill

### Requirement: financialjuice added as default source
The system SHALL include @financialjuice in the default monitored accounts list.

#### Scenario: Default accounts include financialjuice
- **WHEN** no custom TWITTER_MONITOR_ACCOUNTS is set
- **THEN** the default list includes FirstSquawk, DeItaone, KobeissiLetter, and financialjuice
