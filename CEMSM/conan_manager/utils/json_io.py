"""JSON read/write helpers."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .filesystem import ensure_dir

log = logging.getLogger(__name__)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.debug("JSON file not found: %s", path)
        return {}
    except json.JSONDecodeError as exc:
        log.error("Invalid JSON in %s: %s", path, exc)
        return {}


def write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        log.info("Wrote JSON to %s", path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
