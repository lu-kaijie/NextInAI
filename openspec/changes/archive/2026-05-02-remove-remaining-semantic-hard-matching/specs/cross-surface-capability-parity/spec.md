## MODIFIED Requirements

### Requirement: Chat SHALL be able to trigger all core web capabilities
The system SHALL expose the core web application capabilities through chat so that users can complete equivalent tasks from the conversational interface.

该要求进一步收紧为：chat 触发这些能力时，不得依赖 web 之外额外存在的自然语言补参逻辑；两者都必须遵守同一工具参数边界。

#### Scenario: Chat triggers report browsing workflow
- **WHEN** the user asks in chat to view reports from a specific source
- **THEN** the system performs the same underlying capability as the web report browsing flow
- **AND** the selected source parameter is represented as explicit structured input rather than program-side phrase matching

#### Scenario: Chat triggers export workflow
- **WHEN** the user asks in chat to export a generated analysis or report
- **THEN** the system performs the same underlying export capability used by the web interface
- **AND** the export format must be supplied through the agent-selected tool parameters

### Requirement: Web and chat SHALL share the same backend capability layer
The system SHALL route both web actions and chat actions through a shared backend capability layer rather than duplicating business logic in separate surfaces.

该要求进一步收紧为：共享的不仅是业务执行逻辑，也包括参数校验和错误语义；任何入口都不得单独维护一套自然语言补参分支。

#### Scenario: Capability behavior remains aligned across surfaces
- **WHEN** the same logical operation is triggered from web and from chat
- **THEN** both surfaces produce equivalent outputs and side effects through the same backend capability implementation
- **AND** both surfaces observe the same validation constraints and structured errors for invalid inputs
