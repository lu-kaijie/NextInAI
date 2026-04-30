"""Structured digest document representation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DigestSection:
    title: str
    entries: list[str] = field(default_factory=list)
    unavailable_reason: str | None = None


@dataclass(slots=True)
class DigestDocument:
    title: str
    scope: str
    summary: str
    highlights: list[str]
    sections: list[DigestSection]

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", "", self.summary, ""]
        if self.highlights:
            lines.append("## 重点")
            for item in self.highlights:
                lines.append(f"- {item}")
            lines.append("")
        for section in self.sections:
            lines.append(f"## {section.title}")
            if section.unavailable_reason:
                lines.append(f"- 不可用：{section.unavailable_reason}")
                lines.append("")
                continue
            if not section.entries:
                lines.append("- 无")
                lines.append("")
                continue
            for entry in section.entries:
                lines.append(entry)
                if not entry.endswith("\n"):
                    lines.append("")
        return "\n".join(lines).strip()
