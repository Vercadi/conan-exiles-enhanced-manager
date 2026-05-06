"""Steam appmanifest parsing."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from ..models.app_paths import SteamAppManifest

log = logging.getLogger(__name__)

TOKEN_RE = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])')


def parse_acf_text(text: str) -> dict[str, Any]:
    """Parse the small VDF/ACF subset used by Steam appmanifest files."""
    tokens = [match.group(1) if match.group(1) is not None else match.group(2) for match in TOKEN_RE.finditer(text)]
    index = 0

    def parse_object() -> dict[str, Any]:
        nonlocal index
        data: dict[str, Any] = {}
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if token == "}":
                break
            if token == "{":
                continue
            key = _unescape(token)
            if index >= len(tokens):
                data[key] = ""
                break
            value = tokens[index]
            index += 1
            if value == "{":
                data[key] = parse_object()
            else:
                data[key] = _unescape(value)
        return data

    parsed = parse_object()
    if "AppState" in parsed and isinstance(parsed["AppState"], dict):
        return parsed["AppState"]
    return parsed


def read_app_manifest(path: Path, *, library_root: Optional[Path] = None) -> Optional[SteamAppManifest]:
    try:
        data = parse_acf_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        log.warning("Could not read Steam appmanifest %s: %s", path, exc)
        return None

    appid = str(data.get("appid") or "")
    if not appid:
        log.warning("Steam appmanifest missing appid: %s", path)
        return None

    return SteamAppManifest(
        appid=appid,
        name=str(data.get("name") or ""),
        installdir=str(data.get("installdir") or ""),
        buildid=str(data.get("buildid") or ""),
        last_updated=str(data.get("LastUpdated") or data.get("lastupdated") or ""),
        size_on_disk=str(data.get("SizeOnDisk") or ""),
        manifest_path=path,
        library_root=library_root,
    )


def _unescape(value: str) -> str:
    return value.replace(r"\\", "\\").replace(r"\"", '"')
