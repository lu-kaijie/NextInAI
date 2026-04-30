"""Backward-compatible exports for report interpretation types."""

from nextinai.agents.intelligence import (
    OpenAIIntelligenceAgent as OpenAIReportInterpreterAgent,
    ReportInterpretation,
    RuleBasedIntelligenceAgent as RuleBasedReportInterpreterAgent,
)


class ReportInterpreterAgent:
    """Backward-compatible alias type."""
