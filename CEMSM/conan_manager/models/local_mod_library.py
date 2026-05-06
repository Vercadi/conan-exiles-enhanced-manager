from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


SOURCE_LOCAL_FILES = "local_files"
SOURCE_ARCHIVE = "archive"
SOURCE_EXTERNAL_LINK = "external_link"
SOURCE_WORKSHOP = "workshop"

COMPONENT_AVAILABLE = "available"
COMPONENT_ACTIVE = "active"
COMPONENT_DISABLED = "disabled"
COMPONENT_MISSING_MANAGED = "missing_managed_file"
COMPONENT_MISSING_SOURCE = "missing_source"


def _path_to_str(path: Path | None) -> str:
    return str(path) if path else ""


def _path_from_str(value: str | None) -> Path | None:
    return Path(value) if value else None


@dataclass
class ModFile:
    path: Path
    role: str = "companion"
    original_path: Path | None = None
    size: int = 0
    modified_time: float = 0.0
    sha256: str = ""

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "role": self.role,
            "original_path": _path_to_str(self.original_path),
            "size": self.size,
            "modified_time": self.modified_time,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModFile":
        return cls(
            path=Path(str(data.get("path") or "")),
            role=str(data.get("role") or "companion"),
            original_path=_path_from_str(data.get("original_path")),
            size=int(data.get("size") or 0),
            modified_time=float(data.get("modified_time") or 0.0),
            sha256=str(data.get("sha256") or ""),
        )


@dataclass
class ModComponent:
    component_id: str
    source_id: str
    display_name: str
    source_type: str
    primary_file: ModFile
    companion_files: list[ModFile] = field(default_factory=list)
    variant_group_id: str = ""
    selected_variant: bool = True
    enabled: bool = True
    notes: str = ""

    @property
    def primary_pak_path(self) -> Path:
        return self.primary_file.path

    @property
    def companion_paths(self) -> list[Path]:
        return [file.path for file in self.companion_files]

    @property
    def status(self) -> str:
        managed_missing = not self.primary_file.path.is_file() or any(
            not file.path.is_file() for file in self.companion_files
        )
        source_missing = bool(self.primary_file.original_path and not self.primary_file.original_path.is_file()) or any(
            bool(file.original_path and not file.original_path.is_file())
            for file in self.companion_files
        )
        if managed_missing and self.source_type != SOURCE_EXTERNAL_LINK:
            return COMPONENT_MISSING_MANAGED
        if source_missing and self.source_type == SOURCE_EXTERNAL_LINK:
            return COMPONENT_MISSING_SOURCE
        if not self.enabled:
            return COMPONENT_DISABLED
        return COMPONENT_AVAILABLE

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "source_id": self.source_id,
            "display_name": self.display_name,
            "source_type": self.source_type,
            "primary_file": self.primary_file.to_dict(),
            "companion_files": [file.to_dict() for file in self.companion_files],
            "variant_group_id": self.variant_group_id,
            "selected_variant": self.selected_variant,
            "enabled": self.enabled,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModComponent":
        return cls(
            component_id=str(data.get("component_id") or ""),
            source_id=str(data.get("source_id") or ""),
            display_name=str(data.get("display_name") or ""),
            source_type=str(data.get("source_type") or SOURCE_LOCAL_FILES),
            primary_file=ModFile.from_dict(data.get("primary_file") or {}),
            companion_files=[
                ModFile.from_dict(item)
                for item in data.get("companion_files", [])
                if isinstance(item, dict)
            ],
            variant_group_id=str(data.get("variant_group_id") or ""),
            selected_variant=bool(data.get("selected_variant", True)),
            enabled=bool(data.get("enabled", True)),
            notes=str(data.get("notes") or ""),
        )


@dataclass
class ModSource:
    source_id: str
    source_type: str
    display_name: str
    original_path: Path | None = None
    managed_path: Path | None = None
    component_ids: list[str] = field(default_factory=list)
    size: int = 0
    modified_time: float = 0.0
    sha256: str = ""
    import_status: str = COMPONENT_AVAILABLE

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "display_name": self.display_name,
            "original_path": _path_to_str(self.original_path),
            "managed_path": _path_to_str(self.managed_path),
            "component_ids": list(self.component_ids),
            "size": self.size,
            "modified_time": self.modified_time,
            "sha256": self.sha256,
            "import_status": self.import_status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModSource":
        return cls(
            source_id=str(data.get("source_id") or ""),
            source_type=str(data.get("source_type") or SOURCE_LOCAL_FILES),
            display_name=str(data.get("display_name") or ""),
            original_path=_path_from_str(data.get("original_path")),
            managed_path=_path_from_str(data.get("managed_path")),
            component_ids=[str(value) for value in data.get("component_ids", []) if value],
            size=int(data.get("size") or 0),
            modified_time=float(data.get("modified_time") or 0.0),
            sha256=str(data.get("sha256") or ""),
            import_status=str(data.get("import_status") or COMPONENT_AVAILABLE),
        )


@dataclass
class ModLibraryState:
    sources: list[ModSource] = field(default_factory=list)
    components: list[ModComponent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sources": [source.to_dict() for source in self.sources],
            "components": [component.to_dict() for component in self.components],
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ModLibraryState":
        if not isinstance(data, dict):
            return cls()
        return cls(
            sources=[
                ModSource.from_dict(item)
                for item in data.get("sources", [])
                if isinstance(item, dict)
            ],
            components=[
                ModComponent.from_dict(item)
                for item in data.get("components", [])
                if isinstance(item, dict)
            ],
        )
