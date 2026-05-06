"""Profile load/apply diff rendering."""
from __future__ import annotations

from difflib import unified_diff

from ..models.modlist import ActiveModEntry


def render_profile_modlist_diff(current: list[ActiveModEntry], proposed: list[ActiveModEntry]) -> str:
    current_lines = [entry.normalized_value for entry in current if entry.normalized_value]
    proposed_lines = [entry.normalized_value for entry in proposed if entry.normalized_value]
    diff = list(
        unified_diff(
            current_lines,
            proposed_lines,
            fromfile="current active mods",
            tofile="profile mods",
            lineterm="",
        )
    )
    if not diff:
        return "(no modlist changes)"
    return "\n".join(diff)
