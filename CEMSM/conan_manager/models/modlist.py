from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


TARGET_CLIENT = "client"
TARGET_DEDICATED_SERVER = "dedicated_server"
TARGET_BOTH = "both"

TARGET_LABELS = {
    TARGET_CLIENT: "Client",
    TARGET_DEDICATED_SERVER: "Dedicated Server",
    TARGET_BOTH: "Both",
}


@dataclass
class ActiveModEntry:
    """A mod entry managed by the app's active local profile."""

    value: str
    display_name: str = ""
    source_type: str = "local_pak"
    workshop_id: Optional[str] = None
    notes: str = ""
    component_id: str = ""
    source_id: str = ""
    companion_paths: list[str] = field(default_factory=list)
    enabled: bool = True

    @property
    def normalized_value(self) -> str:
        return normalize_modlist_value(self.value)

    @property
    def requires_target_copy(self) -> bool:
        return self.source_type in {"local_pak", "managed_local", "archive_component", "external_link"}

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "display_name": self.display_name,
            "source_type": self.source_type,
            "workshop_id": self.workshop_id,
            "notes": self.notes,
            "component_id": self.component_id,
            "source_id": self.source_id,
            "companion_paths": list(self.companion_paths),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActiveModEntry":
        value = str(data.get("value") or "")
        return cls(
            value=value,
            display_name=str(data.get("display_name") or display_name_from_value(value)),
            source_type=str(data.get("source_type") or "local_pak"),
            workshop_id=str(data.get("workshop_id")) if data.get("workshop_id") else None,
            notes=str(data.get("notes") or ""),
            component_id=str(data.get("component_id") or ""),
            source_id=str(data.get("source_id") or ""),
            companion_paths=[str(path) for path in data.get("companion_paths", []) if path],
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class ModlistEntry:
    """An entry read from or planned for a Conan modlist.txt file."""

    value: str
    line_number: int = 0
    resolved_path: Optional[Path] = None
    exists: bool = False

    @property
    def normalized_value(self) -> str:
        return normalize_modlist_value(self.value)

    @property
    def display_name(self) -> str:
        return display_name_from_value(self.value)


@dataclass
class ModlistTargetPlan:
    target: str
    label: str
    mods_dir: Path
    modlist_path: Path
    current_entries: list[ModlistEntry] = field(default_factory=list)
    proposed_entries: list[ActiveModEntry] = field(default_factory=list)
    target_modlist_values: list[str] = field(default_factory=list)
    file_copies: list["TargetFileCopy"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def creates_mods_dir(self) -> bool:
        return not self.mods_dir.exists()

    @property
    def backup_needed(self) -> bool:
        return self.modlist_path.is_file()

    @property
    def proposed_values(self) -> list[str]:
        if self.target_modlist_values:
            return [value for value in self.target_modlist_values if value]
        return [entry.normalized_value for entry in self.proposed_entries if entry.enabled and entry.normalized_value]


@dataclass
class TargetFileCopy:
    source_path: Path
    target_path: Path

    @property
    def backup_needed(self) -> bool:
        return self.target_path.is_file()


@dataclass
class ModlistApplyResult:
    written_paths: list[Path] = field(default_factory=list)
    backup_ids: list[str] = field(default_factory=list)
    copied_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ModlistParity:
    matches: bool
    client_count: int
    server_count: int
    missing_on_client: list[str] = field(default_factory=list)
    missing_on_server: list[str] = field(default_factory=list)
    order_mismatch: bool = False

    @property
    def summary(self) -> str:
        if self.matches:
            return f"Client and Dedicated Server match ({self.client_count} mod(s))."
        parts: list[str] = []
        if self.missing_on_client:
            parts.append(f"{len(self.missing_on_client)} server-only")
        if self.missing_on_server:
            parts.append(f"{len(self.missing_on_server)} client-only")
        if self.order_mismatch:
            parts.append("same mods, different order")
        if not parts:
            parts.append("different mod lists")
        return "Mismatch: " + ", ".join(parts)


def normalize_modlist_value(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith("*"):
        value = value[1:].strip()
    return value


def display_name_from_value(value: str) -> str:
    normalized = normalize_modlist_value(value)
    if not normalized:
        return "Unnamed mod"
    return Path(normalized).stem or normalized
