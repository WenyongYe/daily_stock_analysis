## ADDED Requirements

### Requirement: Structured briefing format
The system SHALL generate a fixed-format financial briefing containing title, timestamp, three-tier classified content, and next push time.

#### Scenario: Normal briefing output
- **WHEN** AI analysis is complete with categorized news items
- **THEN** the system outputs a Feishu Markdown briefing with 🔴/🟡/🔵 sections, source attribution, and next scheduled push time

### Requirement: Feishu webhook delivery
The system SHALL deliver the briefing via the existing Feishu webhook notification channel.

#### Scenario: Successful push
- **WHEN** the briefing is generated and Feishu webhook is configured
- **THEN** the message is sent to the configured Feishu group or user

### Requirement: CLI interface
The system SHALL provide a CLI entry point supporting `--output`, `--feishu`, and `--dry-run` flags.

#### Scenario: Dry-run mode
- **WHEN** the user runs `python3 twitter_news_run.py --dry-run`
- **THEN** tweets are fetched and printed to stdout without LLM analysis or Feishu push

### Requirement: Scheduled execution
The system SHALL run automatically every 8 hours via cron job at Beijing time 00:00, 08:00, and 16:00.

#### Scenario: Cron trigger
- **WHEN** the cron schedule `0 0,8,16 * * *` fires
- **THEN** the full pipeline executes: fetch → analyze → format → push

### Requirement: Configurable account list
The system SHALL support adding or removing monitored accounts via configuration without code changes.

#### Scenario: Add new account
- **WHEN** the user adds "NickTimiraos" to `TWITTER_MONITOR_ACCOUNTS` environment variable
- **THEN** the next scheduled run includes tweets from the new account in its analysis
