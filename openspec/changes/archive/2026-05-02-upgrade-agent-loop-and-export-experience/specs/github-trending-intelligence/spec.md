## ADDED Requirements

### Requirement: Trending query capability SHALL declare its supported time windows truthfully
The system SHALL expose only those GitHub trending time windows and query granularities that are supported by the underlying official source or by a clearly labeled alternative mode.

#### Scenario: Official window is supported
- **WHEN** the user requests a trending window that is supported by the current official trending source
- **THEN** the system returns results using that official source and labels the output accordingly

#### Scenario: Requested window is not officially supported
- **WHEN** the user requests a window or granularity not supported by the official trending source
- **THEN** the system explicitly states the limitation and either offers a labeled alternative query mode or refuses the request

### Requirement: Trending results SHALL carry query provenance
The system SHALL record and present the provenance of trending results, including whether they came from the official trending source or from an alternative approximation path.

#### Scenario: Result provenance is shown
- **WHEN** a trending result is returned
- **THEN** the response includes the source mode or capability label used to produce the ranking

