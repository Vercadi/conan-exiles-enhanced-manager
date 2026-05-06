"""Warnings for profile entries whose source paks or Workshop cache items are missing."""
from __future__ import annotations

from ..core.modlist_service import resolve_entry_path
from ..models.modlist import ActiveModEntry
from ..models.workshop import WORKSHOP_STATUS_DOWNLOADED, WorkshopItem


def profile_entry_warnings(entries: list[ActiveModEntry], workshop_items: list[WorkshopItem]) -> list[str]:
    warnings: list[str] = []
    workshop_by_id = {item.workshop_id: item for item in workshop_items}
    for entry in entries:
        if entry.workshop_id:
            item = workshop_by_id.get(entry.workshop_id)
            if item is None:
                warnings.append(f"Workshop {entry.workshop_id} is not in the local cache.")
            elif item.status != WORKSHOP_STATUS_DOWNLOADED:
                warnings.append(f"Workshop {entry.workshop_id} is {item.status}.")
            elif not item.pak_paths:
                warnings.append(f"Workshop {entry.workshop_id} has no detected .pak file.")

        resolved = resolve_entry_path(entry.value)
        if resolved is None or not resolved.is_file():
            warnings.append(f"Missing source pak/archive: {entry.value}")
    return warnings
