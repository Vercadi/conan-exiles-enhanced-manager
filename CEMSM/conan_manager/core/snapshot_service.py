"""Backup snapshot browsing and validated restore helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .backup_manager import BackupManager, BackupRecord


@dataclass
class SnapshotValidation:
    ok: bool
    message: str
    record: BackupRecord | None = None


def list_snapshots(backup: BackupManager, *, category: str | None = None) -> list[BackupRecord]:
    return sorted(backup.list_backups(category=category), key=lambda record: record.timestamp, reverse=True)


def validate_snapshot_record(backup: BackupManager, backup_id: str) -> SnapshotValidation:
    record = next((item for item in backup.list_backups() if item.backup_id == backup_id), None)
    if record is None:
        return SnapshotValidation(False, "Backup record is not registered in the app metadata.")
    backup_path = Path(record.backup_path)
    try:
        backup_path.resolve().relative_to(backup.backup_root.resolve())
    except ValueError:
        return SnapshotValidation(False, "Backup file is outside the configured backup root.", record)
    if not backup_path.is_file():
        return SnapshotValidation(False, "Backup file is missing on disk.", record)
    if not record.source_path:
        return SnapshotValidation(False, "Backup record has no source path.", record)
    return SnapshotValidation(True, "Backup record is valid.", record)


def restore_snapshot_record(backup: BackupManager, backup_id: str) -> BackupRecord:
    validation = validate_snapshot_record(backup, backup_id)
    if not validation.ok or validation.record is None:
        raise ValueError(validation.message)
    restored = backup.restore_backup(validation.record)
    if not restored:
        raise ValueError("Restore failed because the backup file could not be copied.")
    return validation.record
