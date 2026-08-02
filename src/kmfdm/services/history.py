from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


HISTORY_FILENAME = ".kmfdm-history.jsonl"


@dataclass(frozen=True)
class HistoryEvent:
    timestamp: str
    action: str
    scope: str
    item: str
    field: str = ""
    library: str = ""
    original: Any = ""
    current: Any = ""
    status: str = "saved"
    detail: str = ""
    source_path: str = ""
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        action: str,
        scope: str,
        item: str,
        field: str = "",
        library: str = "",
        original: Any = "",
        current: Any = "",
        status: str = "saved",
        detail: str = "",
        source_path: str | Path = "",
        metadata: dict[str, Any] | None = None,
    ) -> HistoryEvent:
        return cls(
            timestamp=_history_timestamp(),
            action=action,
            scope=scope,
            item=item,
            field=field,
            library=library,
            original=original,
            current=current,
            status=status,
            detail=detail,
            source_path=str(source_path) if source_path else "",
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEvent:
        return cls(
            timestamp=str(data.get("timestamp", "")),
            action=str(data.get("action", "")),
            scope=str(data.get("scope", "")),
            item=str(data.get("item", "")),
            field=str(data.get("field", "")),
            library=str(data.get("library", "")),
            original=data.get("original", ""),
            current=data.get("current", ""),
            status=str(data.get("status", "")),
            detail=str(data.get("detail", "")),
            source_path=str(data.get("source_path", "")),
            metadata=dict(data.get("metadata", {})) if isinstance(data.get("metadata", {}), dict) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "scope": self.scope,
            "item": self.item,
            "field": self.field,
            "library": self.library,
            "original": self.original,
            "current": self.current,
            "status": self.status,
            "detail": self.detail,
            "source_path": self.source_path,
            "metadata": dict(self.metadata),
        }


def history_path_for_workspace(workspace_config_path: Path) -> Path:
    return workspace_config_path.parent / HISTORY_FILENAME


def append_history_events(path: Path, events: list[HistoryEvent]) -> None:
    if not events:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def load_history_events(path: Path) -> list[HistoryEvent]:
    if not path.exists():
        return []

    events: list[HistoryEvent] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                continue
            events.append(HistoryEvent.from_dict(data))
    return events


def _history_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
