### Requirement: OCR extracts Volume/OI/Expiry from tweet images

The system SHALL use Vision LLM to extract option flow fields from tweet images.

#### Scenario: Successful OCR
- **WHEN** an image contains option flow details
- **THEN** the OCR output SHALL include a JSON array of objects with fields:
  - `symbol`, `option_type`, `expiry`, `strike`, `volume`, `open_interest`

#### Scenario: OCR incomplete
- **WHEN** Flash model output misses key fields
- **THEN** the system SHALL retry using the fallback model

#### Scenario: OCR fails
- **WHEN** OCR returns invalid JSON or empty content
- **THEN** the image result is discarded and the pipeline continues
