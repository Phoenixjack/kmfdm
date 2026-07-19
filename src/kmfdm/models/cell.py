from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ChangeSource(StrEnum):
    MANUAL = "manual"
    BULK_EDIT = "bulk_edit"
    RULE_GENERATED = "rule_generated"
    FIELD_MOVE = "field_move"
    FIELD_COPY = "field_copy"


class ChangeKind(StrEnum):
    VALUE_CHANGED = "value_changed"
    VALUE_CLEARED = "value_cleared"
    FIELD_ADDED = "field_added"
    FIELD_DELETED = "field_deleted"
    FIELD_RENAMED = "field_renamed"
    VALUE_MOVED = "value_moved"
    VALUE_COPIED = "value_copied"
    AUTOMATIC_NORMALIZATION = "automatic_normalization"


@dataclass(frozen=True)
class Issue:
    severity: IssueSeverity
    title: str
    detail: str
    rule_name: str | None = None


@dataclass
class CellState:
    original_value: str = ""
    working_value: str = ""
    change_source: ChangeSource | None = None
    change_kind: ChangeKind | None = None
    included_in_save: bool = True
    editable: bool = True
    inherited: bool = False
    issues: list[Issue] = field(default_factory=list)
    change_group_id: str | None = None

    @property
    def is_changed(self) -> bool:
        return self.original_value != self.working_value or self.change_kind is not None

    def tooltip_text(self) -> str:
        sections: list[str] = []

        if self.is_changed:
            sections.append(
                "\n".join(
                    [
                        "Change:",
                        f"Original: {self.original_value}",
                        f"Current: {self.working_value}",
                        f"Source: {self.change_source.value if self.change_source else 'unknown'}",
                    ]
                )
            )

        if self.issues:
            issue_lines = ["Issues:"]
            for issue in self.issues:
                issue_lines.append(f"{issue.severity.value.upper()}: {issue.title}")
            sections.append("\n".join(issue_lines))

        return "\n\n".join(sections)
