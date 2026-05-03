## ADDED Requirements

### Requirement: Chat SHALL use agent loop orchestration for primary intent handling
The system SHALL process chat requests through an agent loop that selects and executes registered tools, instead of relying on hardcoded keyword routing as the primary interaction path.

#### Scenario: Natural language request maps to tool call
- **WHEN** the user asks for a supported capability in natural language
- **THEN** the system executes the request through the agent loop and returns a tool-backed result

#### Scenario: Unsupported or ambiguous request needs clarification
- **WHEN** the user request cannot be mapped to a safe tool action with sufficient confidence
- **THEN** the system asks a clarifying question or returns an explicit limitation instead of guessing silently

### Requirement: High-impact actions SHALL remain confirmation-gated
The system SHALL preserve explicit confirmation for side-effecting actions such as task creation, task deletion, and outbound delivery, even when the action is selected by the agent loop.

#### Scenario: Delivery action requires confirmation
- **WHEN** the agent loop determines that a notification or delivery action should be executed
- **THEN** the system returns a pending confirmation response before executing the action

#### Scenario: Confirmation resumes the planned action
- **WHEN** the user confirms a pending action
- **THEN** the system executes the previously planned tool call without requiring the user to restate the full request

