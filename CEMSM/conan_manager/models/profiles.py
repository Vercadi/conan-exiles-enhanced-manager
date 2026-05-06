from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .modlist import ActiveModEntry, TARGET_CLIENT, TARGET_DEDICATED_SERVER

TARGET_HOSTED = "hosted"
PROFILE_TARGETS = (TARGET_CLIENT, TARGET_DEDICATED_SERVER, TARGET_HOSTED)


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_profile_targets(values: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        text = str(value or "").strip().casefold()
        if text in PROFILE_TARGETS and text not in normalized:
            normalized.append(text)
    return normalized or [TARGET_CLIENT]


@dataclass
class ModProfile:
    name: str
    entries: list[ActiveModEntry] = field(default_factory=list)
    target_coverage: list[str] = field(default_factory=lambda: [TARGET_CLIENT, TARGET_DEDICATED_SERVER])
    notes: str = ""
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    @property
    def is_vanilla(self) -> bool:
        return not self.entries

    def normalized(self) -> "ModProfile":
        return ModProfile(
            name=str(self.name or "Unnamed Profile").strip() or "Unnamed Profile",
            entries=list(self.entries),
            target_coverage=normalize_profile_targets(self.target_coverage),
            notes=str(self.notes or ""),
            created_at=str(self.created_at or utc_timestamp()),
            updated_at=str(self.updated_at or utc_timestamp()),
        )

    def to_dict(self) -> dict:
        normalized = self.normalized()
        return {
            "name": normalized.name,
            "entries": [entry.to_dict() for entry in normalized.entries],
            "target_coverage": list(normalized.target_coverage),
            "notes": normalized.notes,
            "created_at": normalized.created_at,
            "updated_at": normalized.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ModProfile":
        if not isinstance(data, dict):
            return cls(name="Unnamed Profile")
        return cls(
            name=str(data.get("name") or "Unnamed Profile"),
            entries=[
                ActiveModEntry.from_dict(item)
                for item in data.get("entries", [])
                if isinstance(item, dict)
            ],
            target_coverage=normalize_profile_targets(data.get("target_coverage")),
            notes=str(data.get("notes") or ""),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        ).normalized()


@dataclass
class ServerProfile:
    name: str
    target_coverage: list[str] = field(default_factory=lambda: [TARGET_DEDICATED_SERVER])
    notes: str = ""
    dedicated_launch_args: str = "-Messaging"
    hosted_profile_name: str = ""
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def normalized(self) -> "ServerProfile":
        return ServerProfile(
            name=str(self.name or "Unnamed Server").strip() or "Unnamed Server",
            target_coverage=normalize_profile_targets(self.target_coverage),
            notes=str(self.notes or ""),
            dedicated_launch_args=str(self.dedicated_launch_args or "-Messaging").strip() or "-Messaging",
            hosted_profile_name=str(self.hosted_profile_name or "").strip(),
            created_at=str(self.created_at or utc_timestamp()),
            updated_at=str(self.updated_at or utc_timestamp()),
        )

    def to_dict(self) -> dict:
        normalized = self.normalized()
        return {
            "name": normalized.name,
            "target_coverage": list(normalized.target_coverage),
            "notes": normalized.notes,
            "dedicated_launch_args": normalized.dedicated_launch_args,
            "hosted_profile_name": normalized.hosted_profile_name,
            "created_at": normalized.created_at,
            "updated_at": normalized.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ServerProfile":
        if not isinstance(data, dict):
            return cls(name="Unnamed Server")
        return cls(
            name=str(data.get("name") or "Unnamed Server"),
            target_coverage=normalize_profile_targets(data.get("target_coverage")),
            notes=str(data.get("notes") or ""),
            dedicated_launch_args=str(data.get("dedicated_launch_args") or "-Messaging"),
            hosted_profile_name=str(data.get("hosted_profile_name") or ""),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        ).normalized()
