### Requirement: Fetch tweets with media for last US trading session

The system SHALL fetch all tweets from the configured accounts within the last completed US trading session (NY 09:30–16:00) using twitterapi.io `advanced_search`.

#### Scenario: Pull FL0WG0D tweets with images
- **WHEN** `fetch_tweets("FL0WG0D", since, until)` is called
- **THEN** tweets are returned with `text`, `createdAt`, `author`, `url`, and `media_urls` fields
- **AND** `media_urls` SHALL include `entities.media[].media_url_https` values when present

#### Scenario: No tweets in window
- **WHEN** the account has no tweets in the time window
- **THEN** an empty list is returned and processing continues without error
