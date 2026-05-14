"""Shared target action helpers for bulk and context-menu workflows."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from ..models.modlist import ActiveModEntry

T = TypeVar("T")

ROW_ACTIVE = "active"
ROW_LIBRARY_COMPONENT = "component"
ROW_LIBRARY_WORKSHOP = "workshop"

MOD_FILE_SUFFIXES = {".pak", ".ucas", ".utoc"}


@dataclass(frozen=True)
class DroppedModFiles:
    pak_files: list[Path]
    archive_files: list[Path]
    modlist_files: list[Path]
    ignored_files: list[Path]


def selected_active_entries(entries: list[ActiveModEntry], indices: Iterable[int]) -> list[ActiveModEntry]:
    """Return selected active entries in load-order order."""
    valid = sorted({int(index) for index in indices if 0 <= int(index) < len(entries)})
    return [entries[index] for index in valid]


def invert_indices(total: int, selected: Iterable[int]) -> list[int]:
    selected_set = {int(index) for index in selected if 0 <= int(index) < total}
    return [index for index in range(total) if index not in selected_set]


def next_first_letter_index(labels: Sequence[str], letter: str, *, start: int = -1) -> int | None:
    """Return the next row whose display label starts with letter, wrapping once."""
    needle = str(letter or "")[:1].casefold()
    if not needle or not labels:
        return None
    total = len(labels)
    start_index = int(start) if -1 <= int(start) < total else -1
    for offset in range(1, total + 1):
        index = (start_index + offset) % total
        label = str(labels[index] or "").lstrip()
        if label[:1].casefold() == needle:
            return index
    return None


def move_items_to_edge(items: Sequence[T], indices: Iterable[int], *, to_top: bool) -> tuple[list[T], list[int]]:
    """Move selected items to the top or bottom while preserving their relative order."""
    selected = sorted({int(index) for index in indices if 0 <= int(index) < len(items)})
    if not selected:
        return list(items), []
    selected_set = set(selected)
    picked = [item for index, item in enumerate(items) if index in selected_set]
    remaining = [item for index, item in enumerate(items) if index not in selected_set]
    if to_top:
        return picked + remaining, list(range(len(picked)))
    offset = len(remaining)
    return remaining + picked, list(range(offset, offset + len(picked)))


def move_items_to_index(items: Sequence[T], indices: Iterable[int], target_index: int) -> tuple[list[T], list[int]]:
    """Move selected items before target_index while preserving relative order."""
    selected = sorted({int(index) for index in indices if 0 <= int(index) < len(items)})
    if not selected:
        return list(items), []
    selected_set = set(selected)
    picked = [item for index, item in enumerate(items) if index in selected_set]
    remaining = [item for index, item in enumerate(items) if index not in selected_set]
    bounded_target = max(0, min(int(target_index), len(items)))
    adjusted_target = bounded_target - sum(1 for index in selected if index < bounded_target)
    adjusted_target = max(0, min(adjusted_target, len(remaining)))
    reordered = remaining[:adjusted_target] + picked + remaining[adjusted_target:]
    return reordered, list(range(adjusted_target, adjusted_target + len(picked)))


def classify_dropped_mod_files(paths: Iterable[Path]) -> DroppedModFiles:
    pak_files: list[Path] = []
    archive_files: list[Path] = []
    modlist_files: list[Path] = []
    ignored_files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        suffix = path.suffix.casefold()
        if suffix in MOD_FILE_SUFFIXES:
            pak_files.append(path)
        elif suffix == ".zip":
            archive_files.append(path)
        elif path.name.casefold() == "modlist.txt":
            modlist_files.append(path)
        else:
            ignored_files.append(path)
    return DroppedModFiles(
        pak_files=pak_files,
        archive_files=archive_files,
        modlist_files=modlist_files,
        ignored_files=ignored_files,
    )


def context_menu_actions(row_kind: str) -> list[str]:
    """Return semantic action ids available for a row kind.

    The UI maps these ids to platform-specific menu labels and commands.
    Keeping this list in core makes routing testable without constructing Tk widgets.
    """
    if row_kind == ROW_LIBRARY_COMPONENT:
        return [
            "add_active",
            "sync_client",
            "sync_server",
            "sync_both",
            "open_source",
            "open_managed",
        ]
    if row_kind == ROW_LIBRARY_WORKSHOP:
        return [
            "download_update",
            "add_active",
            "sync_client",
            "sync_server",
            "sync_both",
            "copy_workshop_id",
            "open_workshop",
        ]
    if row_kind == ROW_ACTIVE:
        return [
            "enable_disable",
            "remove_active",
            "sync_client",
            "sync_server",
            "sync_both",
            "uninstall_client",
            "uninstall_server",
            "open_source",
        ]
    return []
