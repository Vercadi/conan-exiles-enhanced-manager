"""Bounded activity timeline for user-visible recovery history."""
from __future__ import annotations

from pathlib import Path

from ..models.activity import ActivityRecord
from ..utils.json_io import read_json, write_json


class ActivityLog:
    def __init__(self, data_dir: Path, *, limit: int = 200):
        self.path = data_dir / "activity_timeline.json"
        self.limit = limit
        self._records: list[ActivityRecord] = []
        self.load()

    def load(self) -> list[ActivityRecord]:
        data = read_json(self.path)
        self._records = [
            ActivityRecord.from_dict(item)
            for item in data.get("records", [])
            if isinstance(item, dict)
        ][-self.limit :]
        return self.list_records()

    def append(self, *, action: str, result: str, target: str = "", details: str = "") -> ActivityRecord:
        record = ActivityRecord(action=action, result=result, target=target, details=details)
        self._records.append(record)
        self._records = self._records[-self.limit :]
        self._save()
        return record

    def list_records(self, *, limit: int | None = None) -> list[ActivityRecord]:
        records = list(reversed(self._records))
        return records[:limit] if limit else records

    def _save(self) -> None:
        write_json(self.path, {"records": [record.to_dict() for record in self._records]})
