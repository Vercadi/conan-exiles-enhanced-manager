"""Filesystem helpers."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_exists(path: Path | None) -> bool:
    try:
        return bool(path and path.exists())
    except OSError:
        return False


def safe_is_dir(path: Path | None) -> bool:
    try:
        return bool(path and path.is_dir())
    except OSError:
        return False


def safe_is_file(path: Path | None) -> bool:
    try:
        return bool(path and path.is_file())
    except OSError:
        return False
