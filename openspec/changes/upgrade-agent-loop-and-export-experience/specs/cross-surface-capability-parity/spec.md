## ADDED Requirements

### Requirement: Chat SHALL be able to trigger all core web capabilities
The system SHALL expose the core web application capabilities through chat so that users can complete equivalent tasks from the conversational interface.

#### Scenario: Chat triggers report browsing workflow
- **WHEN** the user asks in chat to view reports from a specific source
- **THEN** the system performs the same underlying capability as the web report browsing flow

#### Scenario: Chat triggers export workflow
- **WHEN** the user asks in chat to export a generated analysis or report
- **THEN** the system performs the same underlying export capability used by the web interface

### Requirement: Web and chat SHALL share the same backend capability layer
The system SHALL route both web actions and chat actions through a shared backend capability layer rather than duplicating business logic in separate surfaces.

#### Scenario: Capability behavior remains aligned across surfaces
- **WHEN** the same logical operation is triggered from web and from chat
- **THEN** both surfaces produce equivalent outputs and side effects through the same backend capability implementation
