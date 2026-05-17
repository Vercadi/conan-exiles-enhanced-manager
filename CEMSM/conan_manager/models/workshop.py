from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

WORKSHOP_STATUS_DOWNLOADED = "downloaded"
WORKSHOP_STATUS_MISSING = "missing"
WORKSHOP_STATUS_NO_PAK = "no_pak"
WORKSHOP_STATUS_DUPLICATE_PAK = "duplicate_pak"
WORKSHOP_STATUS_UNKNOWN = "unknown"


@dataclass
class WorkshopItem:
    """Local metadata for a Conan Steam Workshop item."""

    workshop_id: str
    title: str = ""
    folder_path: Optional[Path] = None
    pak_paths: list[Path] = field(default_factory=list)
    local_size: int = 0
    modified_time: float = 0.0
    status: str = WORKSHOP_STATUS_UNKNOWN
    compatibility_note: str = "Enhanced compatibility unknown"
    display_name_override: str = ""
    remote_file_size: int = 0
    remote_time_updated: int = 0
    consumer_app_id: int = 0
    creator_app_id: int = 0
    preview_url: str = ""
    tags: list[str] = field(default_factory=list)
    metadata_result: int = 0
    metadata_fetched_at: float = 0.0
    metadata_warning: str = ""

    @property
    def display_title(self) -> str:
        return self.title or self.display_name_override or f"Workshop {self.workshop_id}"

    @property
    def primary_pak(self) -> Optional[Path]:
        if self.pak_paths:
            return self.pak_paths[0]
        return None

    def to_dict(self) -> dict:
        return {
            "workshop_id": self.workshop_id,
            "title": self.title,
            "folder_path": str(self.folder_path) if self.folder_path else None,
            "pak_paths": [str(path) for path in self.pak_paths],
            "local_size": self.local_size,
            "modified_time": self.modified_time,
            "status": self.status,
            "compatibility_note": self.compatibility_note,
            "display_name_override": self.display_name_override,
            "remote_file_size": self.remote_file_size,
            "remote_time_updated": self.remote_time_updated,
            "consumer_app_id": self.consumer_app_id,
            "creator_app_id": self.creator_app_id,
            "preview_url": self.preview_url,
            "tags": list(self.tags),
            "metadata_result": self.metadata_result,
            "metadata_fetched_at": self.metadata_fetched_at,
            "metadata_warning": self.metadata_warning,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkshopItem":
        return cls(
            workshop_id=str(data.get("workshop_id") or ""),
            title=str(data.get("title") or ""),
            folder_path=Path(data["folder_path"]) if data.get("folder_path") else None,
            pak_paths=[Path(value) for value in data.get("pak_paths", []) if value],
            local_size=int(data.get("local_size") or 0),
            modified_time=float(data.get("modified_time") or 0.0),
            status=str(data.get("status") or WORKSHOP_STATUS_UNKNOWN),
            compatibility_note=str(data.get("compatibility_note") or "Enhanced compatibility unknown"),
            display_name_override=str(data.get("display_name_override") or ""),
            remote_file_size=int(data.get("remote_file_size") or 0),
            remote_time_updated=int(data.get("remote_time_updated") or 0),
            consumer_app_id=int(data.get("consumer_app_id") or 0),
            creator_app_id=int(data.get("creator_app_id") or 0),
            preview_url=str(data.get("preview_url") or ""),
            tags=[str(value) for value in data.get("tags", []) if value],
            metadata_result=int(data.get("metadata_result") or 0),
            metadata_fetched_at=float(data.get("metadata_fetched_at") or 0.0),
            metadata_warning=str(data.get("metadata_warning") or ""),
        )


@dataclass
class WorkshopParseResult:
    ids: list[str] = field(default_factory=list)
    invalid_tokens: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.invalid_tokens
