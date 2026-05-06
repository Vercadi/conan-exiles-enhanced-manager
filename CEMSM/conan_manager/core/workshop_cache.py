"""Persistent Steam Workshop metadata cache."""
from __future__ import annotations

from pathlib import Path

from ..models.workshop import WorkshopItem
from ..utils.json_io import read_json, write_json


class WorkshopCache:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "workshop_cache.json"
        self._items: list[WorkshopItem] = []
        self.load()

    def load(self) -> list[WorkshopItem]:
        data = read_json(self.path)
        self._items = [
            WorkshopItem.from_dict(item)
            for item in data.get("items", [])
            if isinstance(item, dict) and str(item.get("workshop_id") or "").strip()
        ]
        return self.list_items()

    def save(self, items: list[WorkshopItem]) -> None:
        self._items = list(items)
        write_json(self.path, {"items": [item.to_dict() for item in self._items]})

    def list_items(self) -> list[WorkshopItem]:
        return list(self._items)

    def get(self, workshop_id: str) -> WorkshopItem | None:
        for item in self._items:
            if item.workshop_id == workshop_id:
                return item
        return None
