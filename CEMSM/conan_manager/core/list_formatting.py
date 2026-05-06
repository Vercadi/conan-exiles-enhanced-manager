"""Stable row formatting for large list controls."""
from __future__ import annotations

from pathlib import Path

from ..models.modlist import ActiveModEntry


def format_active_mod_row(
    index: int,
    entry: ActiveModEntry,
    *,
    missing: bool = False,
    max_value_length: int = 180,
) -> str:
    marker = "off" if not entry.enabled else ("!" if missing else " ")
    source = f"Workshop {entry.workshop_id}" if entry.workshop_id else entry.source_type.replace("_", " ")
    name = entry.display_name or Path(entry.value).stem or "Unnamed mod"
    value = _middle_truncate(entry.value, max_value_length)
    return f"{index:02d}. [{marker}] {name} [{source}] :: {value}"


def _middle_truncate(value: str, max_length: int) -> str:
    text = str(value or "")
    if max_length <= 20 or len(text) <= max_length:
        return text
    keep = max_length - 5
    left = keep // 2
    right = keep - left
    return f"{text[:left]} ... {text[-right:]}"
