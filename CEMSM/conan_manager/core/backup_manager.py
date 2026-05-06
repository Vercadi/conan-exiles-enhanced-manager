"""Backup manager for read-only v0.1 safety operations."""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models.app_paths import ConanAppPaths
from ..utils.filesystem import ensure_dir
from ..utils.json_io import read_json, write_json
from ..utils.naming import timestamp_slug

log = logging.getLogger(__name__)


@dataclass
class BackupRecord:
    backup_id: str
    timestamp: str
    category: str
    source_path: str
    backup_path: str
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "backup_id": self.backup_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "source_path": self.source_path,
            "backup_path": self.backup_path,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupRecord":
        return cls(
            backup_id=str(data.get("backup_id") or ""),
            timestamp=str(data.get("timestamp") or ""),
            category=str(data.get("category") or ""),
            source_path=str(data.get("source_path") or ""),
            backup_path=str(data.get("backup_path") or ""),
            description=str(data.get("description") or ""),
        )


class BackupManager:
    """Creates app-controlled timestamped backups."""

    def __init__(self, backup_root: Path):
        self.backup_root = backup_root
        self.config_dir = backup_root / "configs"
        self.saves_dir = backup_root / "saves"
        self.metadata_dir = backup_root / "metadata"
        self.records_path = self.metadata_dir / "backup_records.json"
        self._records: list[BackupRecord] = []
        self._load_records()

    def backup_file(self, source: Path, *, category: str, description: str = "") -> Optional[BackupRecord]:
        if not source.is_file():
            log.warning("Cannot back up missing file: %s", source)
            return None

        category_dir = self._category_dir(category)
        ensure_dir(category_dir)
        timestamp = timestamp_slug()
        destination = category_dir / f"{timestamp}_{source.name}"
        counter = 1
        while destination.exists():
            destination = category_dir / f"{timestamp}_{source.stem}_{counter}{source.suffix}"
            counter += 1

        shutil.copy2(source, destination)
        record = BackupRecord(
            backup_id=f"{category}_{destination.name}",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            category=category,
            source_path=str(source),
            backup_path=str(destination),
            description=description or f"Backup of {source.name}",
        )
        self._append_record(record)
        log.info("Backed up %s -> %s", source, destination)
        return record

    def backup_configs_and_saves(self, paths: ConanAppPaths) -> list[BackupRecord]:
        records: list[BackupRecord] = []
        for config_file in paths.config_files():
            record = self.backup_file(config_file, category="configs", description="Manual config backup")
            if record:
                records.append(record)
        for save_file in paths.save_database_files():
            record = self.backup_file(save_file, category="saves", description="Manual save database backup")
            if record:
                records.append(record)
        return records

    def list_backups(
        self,
        category: Optional[str] = None,
        source_path: Optional[Path | str] = None,
    ) -> list[BackupRecord]:
        records = list(self._records)
        if category:
            records = [record for record in records if record.category == category]
        if source_path is not None:
            source = str(source_path)
            records = [record for record in records if record.source_path == source]
        return records

    def restore_backup(self, record: BackupRecord, *, dest_path: Optional[Path] = None) -> bool:
        backup_path = Path(record.backup_path)
        destination = dest_path or Path(record.source_path)
        if not backup_path.is_file():
            log.warning("Cannot restore missing backup: %s", backup_path)
            return False
        ensure_dir(destination.parent)
        shutil.copy2(backup_path, destination)
        log.info("Restored backup %s -> %s", backup_path, destination)
        return True

    def _category_dir(self, category: str) -> Path:
        if category == "configs":
            return self.config_dir
        if category == "saves":
            return self.saves_dir
        return self.backup_root / category

    def _load_records(self) -> None:
        data = read_json(self.records_path)
        self._records = [BackupRecord.from_dict(item) for item in data.get("records", []) if isinstance(item, dict)]

    def _save_records(self) -> None:
        write_json(self.records_path, {"records": [record.to_dict() for record in self._records]})

    def _append_record(self, record: BackupRecord) -> None:
        self._records.append(record)
        ensure_dir(self.metadata_dir)
        self._save_records()
