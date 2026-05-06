"""Read-only discovery for Conan Exiles Enhanced installs."""
from __future__ import annotations

import ctypes
import logging
import os
import string
from pathlib import Path
from typing import Iterable, Optional

from ..models.app_paths import ConanAppPaths, SteamAppManifest
from ..utils.filesystem import safe_is_dir, safe_is_file
from .steam_manifest import parse_acf_text, read_app_manifest

log = logging.getLogger(__name__)

CLIENT_APP_ID = "440900"
DEDICATED_SERVER_APP_ID = "443030"
WORKSHOP_APP_ID = CLIENT_APP_ID

CLIENT_FOLDER_NAMES = ("Conan Exiles", "Conan Exiles Enhanced")
DEDICATED_SERVER_FOLDER_NAMES = (
    "Conan Exiles Dedicated Server",
    "Conan Exiles Enhanced Dedicated Server",
)


def discover_all(
    *,
    extra_steamapps_dirs: Iterable[Path] | None = None,
    known_client_root: Optional[Path] = None,
    known_dedicated_server_root: Optional[Path] = None,
) -> ConanAppPaths:
    steamapps_dirs = discover_steamapps_dirs(extra_steamapps_dirs=extra_steamapps_dirs)
    client_manifest = find_app_manifest(CLIENT_APP_ID, steamapps_dirs)
    server_manifest = find_app_manifest(DEDICATED_SERVER_APP_ID, steamapps_dirs)

    client_root = _valid_or_none(known_client_root, validate_client_root)
    if client_root is None:
        client_root = root_from_manifest(client_manifest)
    if client_root is None:
        client_root = find_root_by_folder_names(steamapps_dirs, CLIENT_FOLDER_NAMES, validate_client_root)

    server_root = _valid_or_none(known_dedicated_server_root, validate_dedicated_server_root)
    if server_root is None:
        server_root = root_from_manifest(server_manifest)
    if server_root is None:
        server_root = find_root_by_folder_names(
            steamapps_dirs,
            DEDICATED_SERVER_FOLDER_NAMES,
            validate_dedicated_server_root,
        )

    workshop_dir = discover_workshop_content_dir(steamapps_dirs, client_manifest=client_manifest)

    paths = ConanAppPaths(
        client_root=client_root,
        dedicated_server_root=server_root,
        steamapps_dirs=steamapps_dirs,
        workshop_content_dir=workshop_dir,
        client_manifest=client_manifest,
        dedicated_server_manifest=server_manifest,
    )
    log.info(
        "Discovery complete | client=%s | dedicated_server=%s | workshop=%s",
        client_root,
        server_root,
        workshop_dir,
    )
    return paths


def discover_steamapps_dirs(*, extra_steamapps_dirs: Iterable[Path] | None = None) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        normalized = str(path)
        if normalized not in seen:
            seen.add(normalized)
            candidates.append(path)

    for path in extra_steamapps_dirs or []:
        add(Path(path))

    for env_key in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        base = os.environ.get(env_key)
        if base:
            add(Path(base) / "Steam" / "steamapps")

    for drive_root in available_drive_roots():
        root = Path(drive_root)
        add(root / "SteamLibrary" / "steamapps")
        add(root / "Steam" / "steamapps")

    for path in list(candidates):
        add_libraryfolders(path, add)

    return [path for path in candidates if safe_is_dir(path)]


def add_libraryfolders(steamapps_dir: Path, add) -> None:
    library_file = steamapps_dir / "libraryfolders.vdf"
    if not library_file.is_file():
        return
    try:
        data = parse_acf_text(library_file.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return
    for value in data.values():
        if isinstance(value, dict) and value.get("path"):
            add(Path(str(value["path"])) / "steamapps")


def available_drive_roots() -> list[str]:
    if os.name != "nt":
        return ["/"]
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    except Exception:
        return [f"{letter}:\\" for letter in "CDEFGH"]

    roots: list[str] = []
    for index, letter in enumerate(string.ascii_uppercase):
        if bitmask & (1 << index):
            roots.append(f"{letter}:\\")
    return roots or ["C:\\"]


def find_app_manifest(appid: str, steamapps_dirs: Iterable[Path]) -> Optional[SteamAppManifest]:
    filename = f"appmanifest_{appid}.acf"
    for steamapps_dir in steamapps_dirs:
        candidate = steamapps_dir / filename
        if candidate.is_file():
            manifest = read_app_manifest(candidate, library_root=steamapps_dir.parent)
            if manifest and manifest.appid == appid:
                return manifest
    return None


def root_from_manifest(manifest: Optional[SteamAppManifest]) -> Optional[Path]:
    if not manifest or not manifest.library_root or not manifest.installdir:
        return None
    candidate = manifest.library_root / "steamapps" / "common" / manifest.installdir
    if manifest.appid == CLIENT_APP_ID and validate_client_root(candidate):
        return candidate
    if manifest.appid == DEDICATED_SERVER_APP_ID and validate_dedicated_server_root(candidate):
        return candidate
    return None


def find_root_by_folder_names(steamapps_dirs: Iterable[Path], names: Iterable[str], validator) -> Optional[Path]:
    for steamapps_dir in steamapps_dirs:
        common = steamapps_dir / "common"
        for name in names:
            candidate = common / name
            if validator(candidate):
                return candidate
    return None


def discover_workshop_content_dir(
    steamapps_dirs: Iterable[Path],
    *,
    client_manifest: Optional[SteamAppManifest] = None,
) -> Optional[Path]:
    preferred: list[Path] = []
    if client_manifest and client_manifest.library_root:
        preferred.append(client_manifest.library_root / "steamapps")
    preferred.extend(steamapps_dirs)

    expected: Optional[Path] = None
    for steamapps_dir in preferred:
        candidate = steamapps_dir / "workshop" / "content" / WORKSHOP_APP_ID
        if expected is None:
            expected = candidate
        if candidate.is_dir():
            return candidate
    return expected


def validate_client_root(path: Path | None) -> bool:
    if not safe_is_dir(path):
        return False
    root = Path(path)
    return safe_is_file(root / "ConanSandbox.exe") or safe_is_file(
        root / "ConanSandbox" / "Binaries" / "Win64" / "ConanSandbox-Win64-Shipping.exe"
    )


def validate_dedicated_server_root(path: Path | None) -> bool:
    if not safe_is_dir(path):
        return False
    root = Path(path)
    return safe_is_file(root / "ConanSandboxServer.exe") or safe_is_file(
        root / "ConanSandbox" / "Binaries" / "Win64" / "ConanSandboxServer-Win64-Shipping.exe"
    )


def _valid_or_none(path: Optional[Path], validator) -> Optional[Path]:
    if path and validator(path):
        return Path(path)
    return None
