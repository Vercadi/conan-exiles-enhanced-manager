"""Local Steam Workshop scanning and cache updates."""
from __future__ import annotations

import logging
from pathlib import Path

from ..models.workshop import (
    WORKSHOP_STATUS_DOWNLOADED,
    WORKSHOP_STATUS_DUPLICATE_PAK,
    WORKSHOP_STATUS_MISSING,
    WORKSHOP_STATUS_NO_PAK,
    WorkshopItem,
)
from .local_mod_library import normalize_mod_display_name
from .workshop_cache import WorkshopCache
from .workshop_metadata import CONAN_WORKSHOP_APP_ID, WorkshopMetadata

log = logging.getLogger(__name__)


class WorkshopService:
    def __init__(self, cache: WorkshopCache):
        self.cache = cache

    def list_items(self) -> list[WorkshopItem]:
        return self.cache.list_items()

    def remove_ids(self, workshop_ids: list[str]) -> int:
        removed = 0
        for workshop_id in dict.fromkeys(str(value).strip() for value in workshop_ids):
            if workshop_id and self.cache.remove(workshop_id):
                removed += 1
        return removed

    def add_ids(self, workshop_ids: list[str], workshop_root: Path | None) -> list[WorkshopItem]:
        items = self.cache.list_items()
        by_id = {item.workshop_id: item for item in items}
        changed = False
        for workshop_id in workshop_ids:
            if workshop_id in by_id:
                continue
            item = self._item_from_folder(workshop_id, workshop_root)
            items.append(item)
            by_id[workshop_id] = item
            changed = True
        if changed:
            self.cache.save(items)
        return items

    def merge_metadata(self, metadata_items: list[WorkshopMetadata]) -> list[WorkshopItem]:
        items = self.cache.list_items()
        by_id = {item.workshop_id: item for item in items}
        ordered_ids = [item.workshop_id for item in items]
        changed = False
        for metadata in metadata_items:
            if not metadata.workshop_id:
                continue
            item = by_id.get(metadata.workshop_id)
            if item is None:
                item = WorkshopItem(workshop_id=metadata.workshop_id)
                by_id[metadata.workshop_id] = item
                ordered_ids.append(metadata.workshop_id)
            _apply_metadata(item, metadata)
            changed = True
        if changed:
            items = [by_id[workshop_id] for workshop_id in ordered_ids if workshop_id in by_id]
            self.cache.save(items)
            return items
        return self.cache.list_items()

    def scan(self, workshop_root: Path | None) -> list[WorkshopItem]:
        return self.scan_roots([workshop_root])

    def scan_roots(self, workshop_roots: list[Path | None]) -> list[WorkshopItem]:
        current = self.cache.list_items()
        by_id = {item.workshop_id: item for item in current}
        ordered_ids = [item.workshop_id for item in current]

        roots = [root for root in workshop_roots if root and root.is_dir()]
        for workshop_root in roots:
            for folder in sorted(path for path in workshop_root.iterdir() if path.is_dir() and path.name.isdigit()):
                if folder.name not in ordered_ids:
                    ordered_ids.append(folder.name)
                existing = by_id.get(folder.name)
                by_id[folder.name] = self._item_from_folder(folder.name, workshop_root, existing=existing)

        for workshop_id in list(ordered_ids):
            existing = by_id[workshop_id]
            if existing.folder_path and existing.folder_path.is_dir():
                root = _root_for_existing_or_default(existing, roots)
                by_id[workshop_id] = self._item_from_folder(workshop_id, root, existing=existing)
            else:
                root = _root_for_existing_or_default(existing, roots)
                by_id[workshop_id] = self._missing_item(workshop_id, root, existing=existing)

        updated = [by_id[workshop_id] for workshop_id in ordered_ids if workshop_id in by_id]
        self.cache.save(updated)
        log.info("Scanned Workshop content: %s item(s)", len(updated))
        return updated

    def _item_from_folder(
        self,
        workshop_id: str,
        workshop_root: Path | None,
        *,
        existing: WorkshopItem | None = None,
    ) -> WorkshopItem:
        folder = workshop_root / workshop_id if workshop_root else None
        if not folder or not folder.is_dir():
            return self._missing_item(workshop_id, workshop_root, existing=existing)

        pak_paths = sorted(path for path in folder.rglob("*.pak") if path.is_file())
        file_paths = [path for path in folder.rglob("*") if path.is_file()]
        local_size = sum(_safe_size(path) for path in file_paths)
        modified_time = max((_safe_mtime(path) for path in file_paths), default=_safe_mtime(folder))
        if not pak_paths:
            status = WORKSHOP_STATUS_NO_PAK
        elif len(pak_paths) == 1:
            status = WORKSHOP_STATUS_DOWNLOADED
        else:
            status = WORKSHOP_STATUS_DUPLICATE_PAK
        return WorkshopItem(
            workshop_id=workshop_id,
            title=existing.title if existing else "",
            folder_path=folder,
            pak_paths=pak_paths,
            local_size=local_size,
            modified_time=modified_time,
            status=status,
            compatibility_note=(existing.compatibility_note if existing else "Enhanced compatibility unknown"),
        )

    @staticmethod
    def _missing_item(
        workshop_id: str,
        workshop_root: Path | None,
        *,
        existing: WorkshopItem | None = None,
    ) -> WorkshopItem:
        folder = workshop_root / workshop_id if workshop_root else None
        return WorkshopItem(
            workshop_id=workshop_id,
            title=existing.title if existing else "",
            folder_path=folder,
            pak_paths=[],
            local_size=0,
            modified_time=0.0,
            status=WORKSHOP_STATUS_MISSING,
            compatibility_note=(existing.compatibility_note if existing else "Enhanced compatibility unknown"),
        )


def workshop_display_name(item: WorkshopItem) -> str:
    """Return a readable display name from cache metadata or local pak names."""
    title = str(item.title or item.display_name_override or "").strip()
    if title and title.casefold() != f"workshop {item.workshop_id}".casefold():
        return normalize_mod_display_name(title)
    if item.primary_pak:
        return normalize_mod_display_name(item.primary_pak.stem)
    return f"Workshop {item.workshop_id}"


def _apply_metadata(item: WorkshopItem, metadata: WorkshopMetadata) -> None:
    if metadata.title:
        item.title = metadata.title
    item.remote_file_size = metadata.file_size
    item.remote_time_updated = metadata.time_updated
    item.consumer_app_id = metadata.consumer_app_id
    item.creator_app_id = metadata.creator_app_id
    item.preview_url = metadata.preview_url
    item.tags = list(metadata.tags)
    item.metadata_result = metadata.result
    item.metadata_fetched_at = metadata.fetched_at
    item.metadata_warning = metadata.warning
    if metadata.consumer_app_id and metadata.consumer_app_id != CONAN_WORKSHOP_APP_ID:
        item.compatibility_note = metadata.warning or item.compatibility_note


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _root_for_existing_or_default(existing: WorkshopItem, roots: list[Path]) -> Path | None:
    if existing.folder_path:
        for root in roots:
            try:
                existing.folder_path.relative_to(root)
                return root
            except ValueError:
                continue
        return existing.folder_path.parent
    return roots[0] if roots else None
