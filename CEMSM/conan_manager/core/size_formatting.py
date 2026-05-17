"""Readable file-size formatting helpers."""
from __future__ import annotations


def format_bytes(size: int | float | None) -> str:
    if size is None:
        return "unknown"
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} B"
    if value >= 100:
        return f"{value:.0f} {units[unit_index]}"
    if value >= 10:
        return f"{value:.1f} {units[unit_index]}"
    return f"{value:.2f} {units[unit_index]}"
