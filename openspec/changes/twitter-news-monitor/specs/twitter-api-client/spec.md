## ADDED Requirements

### Requirement: Fetch tweets by account and time window
The system SHALL fetch all tweets from a specified Twitter account within a given time window via the twitterapi.io `advanced_search` endpoint.

#### Scenario: Successful fetch
- **WHEN** `fetch_tweets("FirstSquawk", since, until)` is called with a valid API key
- **THEN** all tweets from that account in the time window are returned, each containing `text`, `createdAt`, and `author`

#### Scenario: No tweets in window
- **WHEN** the account has no tweets in the specified time window
- **THEN** an empty list is returned without error

### Requirement: Cursor-based pagination
The system SHALL automatically handle `has_next_page` / `next_cursor` pagination to retrieve complete result sets.

#### Scenario: Multi-page results
- **WHEN** the API response includes `has_next_page: true`
- **THEN** the client SHALL continue requesting with `next_cursor` until all pages are fetched

### Requirement: Retry with exponential backoff
The system SHALL retry failed API calls with exponential backoff, up to 3 attempts.

#### Scenario: Transient failure
- **WHEN** the API returns 5xx or a network timeout
- **THEN** the client retries up to 3 times with exponential backoff, then returns an empty result and logs the error

### Requirement: Batch fetch across multiple accounts
The system SHALL support fetching tweets from multiple accounts in a single call, merged and sorted by time descending.

#### Scenario: Multi-account fetch
- **WHEN** `fetch_all_tweets(["FirstSquawk", "DeItaone", "KobeissiLetter"], since, until)` is called
- **THEN** tweets from all accounts are returned in a single list sorted by `createdAt` descending
