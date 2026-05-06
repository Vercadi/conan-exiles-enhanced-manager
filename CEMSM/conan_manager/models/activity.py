from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def activity_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class ActivityRecord:
    action: str
    result: str
    target: str = ""
    details: str = ""
    timestamp: str = field(default_factory=activity_timestamp)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "target": self.target,
            "result": self.result,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActivityRecord":
        return cls(
            timestamp=str(data.get("timestamp") or activity_timestamp()),
            action=str(data.get("action") or ""),
            target=str(data.get("target") or ""),
            result=str(data.get("result") or ""),
            details=str(data.get("details") or ""),
        )

    @property
    def summary(self) -> str:
        pieces = [self.timestamp, self.action]
        if self.target:
            pieces.append(self.target)
        pieces.append(self.result)
        if self.details:
            pieces.append(self.details)
        return " | ".join(pieces)
