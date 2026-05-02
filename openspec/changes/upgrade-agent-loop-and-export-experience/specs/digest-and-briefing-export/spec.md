## ADDED Requirements

### Requirement: Export capability SHALL cover multiple intelligence content types
The system SHALL support exporting GitHub update summaries, trending analyses, report summaries, detailed report interpretations, and digest/briefing outputs through a unified export capability.

#### Scenario: Export GitHub repository summary
- **WHEN** the user requests export after generating a repository update summary
- **THEN** the system produces an export artifact for that summary

#### Scenario: Export trending analysis
- **WHEN** the user requests export after generating a trending analysis
- **THEN** the system produces an export artifact for that trending output

#### Scenario: Export digest or briefing
- **WHEN** the user requests export after generating a digest or briefing
- **THEN** the system produces an export artifact for that digest or briefing

### Requirement: Export outputs SHALL use consistent format contracts
The system SHALL apply consistent naming, metadata, and supported format rules across all exportable intelligence content.

#### Scenario: Export metadata is consistent
- **WHEN** two different content types are exported
- **THEN** both outputs follow the same format contract for filename structure and content metadata

