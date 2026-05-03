## MODIFIED Requirements

### Requirement: Chat SHALL use agent loop orchestration for primary intent handling
The system SHALL process chat requests through an agent loop that selects and executes registered tools, instead of relying on hardcoded keyword routing as the primary interaction path.

该要求进一步收紧为：不仅工具选择由 agent 决定，业务参数也必须由 agent 显式决定。程序不得保留自然语言参数提取或语义补全链路。

#### Scenario: Natural language request maps to tool call
- **WHEN** the user asks for a supported capability in natural language
- **THEN** the system executes the request through the agent loop and returns a tool-backed result
- **AND** the tool call parameters come from the agent decision rather than programmatic phrase mapping

#### Scenario: Unsupported or ambiguous request needs clarification
- **WHEN** the user request cannot be mapped to a safe tool action with sufficient confidence
- **THEN** the system asks a clarifying question or returns an explicit limitation instead of guessing silently
- **AND** the system does not repair the missing intent by hardcoded keyword fallback

### Requirement: High-impact actions SHALL remain confirmation-gated
The system SHALL preserve explicit confirmation for side-effecting actions such as task creation, task deletion, and outbound delivery, even when the action is selected by the agent loop.

该要求保持不变，但增加一条约束：进入确认门之前，动作参数必须已经通过统一校验，程序不得通过待确认逻辑顺便补全业务参数。

#### Scenario: Delivery action requires confirmation
- **WHEN** the agent loop determines that a notification or delivery action should be executed
- **THEN** the system returns a pending confirmation response before executing the action
- **AND** the pending action stores the explicit tool parameters chosen by the agent

#### Scenario: Confirmation resumes the planned action
- **WHEN** the user confirms a pending action
- **THEN** the system executes the previously planned tool call without requiring the user to restate the full request
- **AND** the resumed action uses the already-validated parameters instead of re-deriving them from natural language
