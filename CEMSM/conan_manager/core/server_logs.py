"""Dedicated server log reading and filtering."""
from __future__ import annotations

from pathlib import Path

from ..models.app_paths import ConanAppPaths
from ..models.server import ServerLogSnapshot

MOD_LOG_PATTERNS = (
    "LogModManager",
    "Mounted Pak",
    "Mounted IoStore",
    "Error",
    "Warning",
)


def read_server_log_snapshot(paths: ConanAppPaths, *, tail_lines: int = 220) -> ServerLogSnapshot:
    log_path = latest_log_file(paths.dedicated_server_log_dir)
    if log_path is None:
        return ServerLogSnapshot()
    tail = read_tail(log_path, tail_lines)
    filtered = filter_mod_related_lines(tail)
    return ServerLogSnapshot(log_path=log_path, tail=tail, filtered=filtered)


def latest_log_file(log_dir: Path | None) -> Path | None:
    if not log_dir or not log_dir.is_dir():
        return None
    logs = [path for path in log_dir.glob("*.log") if path.is_file()]
    if not logs:
        return None
    return max(logs, key=lambda path: path.stat().st_mtime)


def read_tail(path: Path, line_count: int = 220) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-line_count:])


def filter_mod_related_lines(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        if any(pattern.casefold() in line.casefold() for pattern in MOD_LOG_PATTERNS):
            lines.append(line)
    return "\n".join(lines)
