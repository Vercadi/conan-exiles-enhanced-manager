"""Stable row formatting for large list controls."""
from __future__ import annotations

from pathlib import Path

from .local_mod_library import normalize_mod_display_name
from ..models.modlist import ActiveModEntry


def format_active_mod_row(
    index: int,
    entry: ActiveModEntry,
    *,
    missing: bool = False,
    max_value_length: int = 180,
    show_value: bool = True,
) -> str:
    marker = "Inactive" if not entry.enabled else ("Missing" if missing else "Active")
    source = f"Workshop {entry.workshop_id}" if entry.workshop_id else entry.source_type.replace("_", " ")
    name = _entry_display_name(entry)
    value = _middle_truncate(entry.value, max_value_length)
    row = f"{index:02d}. [{marker}] {name} [{source}]"
    if show_value:
        row += f" :: {value}"
    return row


def _middle_truncate(value: str, max_length: int) -> str:
    text = str(value or "")
    if max_length <= 20 or len(text) <= max_length:
        return text
    keep = max_length - 5
    left = keep // 2
    right = keep - left
    return f"{text[:left]} ... {text[-right:]}"


def _entry_display_name(entry: ActiveModEntry) -> str:
    name = str(entry.display_name or "").strip()
    if entry.workshop_id and name.casefold() == f"workshop {entry.workshop_id}".casefold():
        name = ""
    if not name:
        name = Path(entry.value).stem or "Unnamed mod"
    return normalize_mod_display_name(name)
