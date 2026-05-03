## ADDED Requirements

### Requirement: Users SHALL be able to browse reports by source
The system SHALL allow users to list available report sources and retrieve recent reports for a selected source.

#### Scenario: List reports for a selected company or forum
- **WHEN** the user selects or asks for a specific report source
- **THEN** the system returns recent reports associated with that source

### Requirement: Users SHALL be able to open a single report for detailed interpretation
The system SHALL provide a detailed interpretation view for an individual report item, separate from the list summary view.

#### Scenario: Open one report from a list
- **WHEN** the user clicks or references a specific report item
- **THEN** the system returns the detailed interpretation for that report item

#### Scenario: Detail interpretation is not yet available
- **WHEN** the user requests detailed interpretation for a report that has not yet been deeply analyzed
- **THEN** the system generates or completes the detailed interpretation before returning it

### Requirement: Report outputs SHALL support export
The system SHALL support exporting report list summaries and single-report detailed interpretations in supported file formats.

#### Scenario: Export report summary
- **WHEN** the user requests export for a report summary view
- **THEN** the system generates an export file for that summary

#### Scenario: Export report detail
- **WHEN** the user requests export for a single report interpretation
- **THEN** the system generates an export file for that detailed interpretation

