"""Persistent local active mod profile."""
from __future__ import annotations

from pathlib import Path

from ..models.modlist import ActiveModEntry
from ..utils.json_io import read_json, write_json


class ModProfileStore:
    """Stores the v0.2 local active mod list."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "active_mods.json"
        self._entries: list[ActiveModEntry] = []
        self.load()

    def load(self) -> list[ActiveModEntry]:
        data = read_json(self.path)
        self._entries = [
            ActiveModEntry.from_dict(item)
            for item in data.get("entries", [])
            if isinstance(item, dict) and str(item.get("value") or "").strip()
        ]
        return list(self._entries)

    def save(self, entries: list[ActiveModEntry]) -> None:
        self._entries = list(entries)
        write_json(self.path, {"entries": [entry.to_dict() for entry in self._entries]})

    def list_entries(self) -> list[ActiveModEntry]:
        return list(self._entries)
