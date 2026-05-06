"""Enhanced-era detection and non-blocking mod compatibility warnings."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..models.app_paths import ConanAppPaths
from ..models.modlist import ActiveModEntry
from ..models.workshop import WorkshopItem
from .modlist_service import resolve_entry_path

ENHANCED_BUILD_FLOOR = 23000000
ENHANCED_LAUNCH_WINDOW = datetime(2026, 5, 1, tzinfo=UTC)


@dataclass
class EnhancedStatus:
    label: str = "Unknown"
    confidence: str = "low"
    clues: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.clues:
            return f"{self.label} ({self.confidence} confidence)"
        return f"{self.label} ({self.confidence} confidence): " + "; ".join(self.clues)


def detect_enhanced_status(paths: ConanAppPaths) -> EnhancedStatus:
    clues: list[str] = []
    build_ids = [
        paths.client_manifest.buildid if paths.client_manifest else "",
        paths.dedicated_server_manifest.buildid if paths.dedicated_server_manifest else "",
    ]
    numeric_builds = [int(value) for value in build_ids if str(value).isdigit()]
    if any(value >= ENHANCED_BUILD_FLOOR for value in numeric_builds):
        clues.append("Steam build is in the Enhanced-era range")
    if _logs_contain_enhanced_clue(paths.client_log_dir) or _logs_contain_enhanced_clue(paths.dedicated_server_log_dir):
        clues.append("Recent logs mention UE5/Unreal Engine 5/5.6")
    if clues:
        return EnhancedStatus(label="Enhanced / UE5 likely", confidence="medium", clues=clues)
    if numeric_builds and all(value < ENHANCED_BUILD_FLOOR for value in numeric_builds):
        return EnhancedStatus(label="Legacy / pre-Enhanced likely", confidence="medium", clues=["Steam build predates Enhanced-era range"])
    return EnhancedStatus(label="Unknown", confidence="low", clues=[])


def old_mod_warnings(
    entries: list[ActiveModEntry],
    workshop_items: list[WorkshopItem],
    *,
    cutoff: datetime = ENHANCED_LAUNCH_WINDOW,
) -> list[str]:
    warnings: list[str] = []
    cutoff_ts = cutoff.timestamp()
    for entry in entries:
        resolved = resolve_entry_path(entry.value)
        if resolved and resolved.is_file():
            try:
                if resolved.stat().st_mtime < cutoff_ts:
                    warnings.append(f"{resolved.name} was modified before the Enhanced launch window.")
            except OSError:
                pass
    for item in workshop_items:
        if item.modified_time and item.modified_time < cutoff_ts:
            warnings.append(f"Workshop {item.workshop_id} was modified before the Enhanced launch window.")
    return warnings


def _logs_contain_enhanced_clue(log_dir: Path | None) -> bool:
    if not log_dir or not log_dir.is_dir():
        return False
    for log_path in sorted(log_dir.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)[:3]:
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")[-20000:].casefold()
        except OSError:
            continue
        if "ue5" in text or "unreal engine 5" in text or "5.6" in text:
            return True
    return False
