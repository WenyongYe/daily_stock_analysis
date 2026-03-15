## ADDED Requirements

### Requirement: Deduplicate cross-account events
The system SHALL identify when multiple accounts report the same event and merge them into a single entry with multi-source attribution.

#### Scenario: Same event from two accounts
- **WHEN** @FirstSquawk and @DeItaone both report a Fed rate cut
- **THEN** the analysis produces one merged event entry noting both sources

### Requirement: Three-tier news classification
The system SHALL classify filtered news into three tiers: 🔴 critical events, 🟡 important updates, 🔵 market commentary.

#### Scenario: Classification criteria
- **WHEN** the AI analyzes a batch of tweets
- **THEN** 🔴 is assigned to events likely to move major assets >1%, 🟡 to significant non-breaking updates, 🔵 to analyst opinions and commentary

### Requirement: Chinese translation and impact analysis
The system SHALL translate English tweets to Chinese and append market impact analysis for each item.

#### Scenario: Translation with context
- **WHEN** the AI processes "Fed cuts rates by 25bp"
- **THEN** the output includes Chinese translation and impact analysis on relevant asset classes

### Requirement: Empty window handling
The system SHALL produce a concise "no significant events" briefing when no important news exists in the time window.

#### Scenario: Quiet period
- **WHEN** no tweets of significance are found in the 8-hour window
- **THEN** the system outputs a brief "过去8小时无重大金融事件" message instead of an empty report
