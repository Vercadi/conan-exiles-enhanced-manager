"""Hosted server path detection, inventory, and upload planning."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..models.hosted import (
    HostedInventory,
    HostedPakUpload,
    HostedPathDetection,
    HostedProfile,
    HostedUploadPlan,
    join_remote_path,
    normalize_remote_path,
)
from ..models.modlist import ActiveModEntry, display_name_from_value
from ..utils.filesystem import ensure_dir
from ..utils.naming import timestamp_slug
from .modlist_service import render_modlist_text, resolve_entry_path
from .remote_provider import RemoteProvider, RemoteProviderError, remote_error_summary

HOSTED_DETECTION_PATHS = (
    ".",
    "ConanSandbox",
    "ConanSandbox/Mods",
    "ConanSandbox/Saved/Config/WindowsServer",
    "ConanSandbox/Saved",
    "ConanSandbox/Saved/Logs",
)


def test_remote_connection(provider: RemoteProvider) -> str:
    try:
        provider.connect()
        provider.list_dir(".")
    except RemoteProviderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RemoteProviderError("connection", str(exc)) from exc
    finally:
        provider.close()
    return "Connection succeeded. FTP/SFTP is separate from Conan game, query, and RCON ports."


def detect_hosted_paths(provider: RemoteProvider, profile: HostedProfile) -> HostedPathDetection:
    normalized = profile.normalized()
    try:
        provider.connect()
        detection = _detect_connected(provider, normalized)
    except RemoteProviderError as exc:
        return HostedPathDetection(
            profile_name=normalized.name,
            ok=False,
            message=remote_error_summary(exc),
        )
    finally:
        provider.close()
    return detection


def scan_hosted_inventory(provider: RemoteProvider, profile: HostedProfile) -> HostedInventory:
    normalized = profile.normalized()
    try:
        provider.connect()
        detection = _detect_connected(provider, normalized)
        pak_files = _list_remote_paks(provider, detection.mods_dir) if detection.mods_dir else []
        modlist_text = ""
        if detection.modlist_path and provider.path_exists(detection.modlist_path):
            modlist_text = provider.read_file(detection.modlist_path).decode("utf-8", errors="replace")
        config_files = []
        if detection.config_dir and provider.path_exists(detection.config_dir):
            config_files = [
                entry.path
                for entry in provider.list_dir(detection.config_dir)
                if not entry.is_dir and entry.name.casefold().endswith(".ini")
            ]
        return HostedInventory(
            detection=detection,
            pak_files=pak_files,
            modlist_text=modlist_text,
            config_files=config_files,
            message=f"Found {len(pak_files)} remote pak(s), {len(config_files)} config file(s).",
        )
    except RemoteProviderError as exc:
        return HostedInventory(
            detection=HostedPathDetection(profile_name=normalized.name, ok=False, message=remote_error_summary(exc)),
            message=remote_error_summary(exc),
        )
    finally:
        provider.close()


def build_hosted_upload_plan(
    profile: HostedProfile,
    detection: HostedPathDetection,
    active_mods: list[ActiveModEntry],
) -> HostedUploadPlan:
    mods_dir = detection.mods_dir or profile.normalized().mods_folder_override
    remote_modlist_path = detection.modlist_path or join_remote_path(mods_dir, "modlist.txt")
    warnings: list[str] = []
    if detection.message and not detection.ok:
        warnings.append(detection.message)
    if not mods_dir:
        warnings.append("Remote Mods folder was not detected. Set a Mods folder override before applying.")
    if not active_mods:
        warnings.append("No Active Mods are selected.")

    entries: list[ActiveModEntry] = []
    pak_uploads: list[HostedPakUpload] = []
    missing: list[str] = []
    for entry in active_mods:
        resolved = resolve_entry_path(entry.value)
        if resolved and resolved.is_file() and resolved.suffix.casefold() == ".pak":
            remote_name = resolved.name
            entries.append(replace(entry, value=remote_name, display_name=entry.display_name or resolved.stem))
            pak_uploads.append(HostedPakUpload(local_path=resolved, remote_path=join_remote_path(mods_dir, remote_name)))
            continue

        normalized_value = entry.normalized_value
        if normalized_value.casefold().endswith(".pak"):
            remote_name = Path(normalized_value).name or normalized_value
            entries.append(replace(entry, value=remote_name, display_name=entry.display_name or display_name_from_value(remote_name)))
            missing.append(normalized_value)
        else:
            warnings.append(f"Skipped non-pak entry: {entry.value}")

    text = render_modlist_text(entries)
    return HostedUploadPlan(
        profile_name=profile.normalized().name,
        remote_mods_dir=mods_dir,
        remote_modlist_path=remote_modlist_path,
        modlist_text=text,
        modlist_entries=[entry.normalized_value for entry in entries],
        pak_uploads=pak_uploads,
        missing_local_paks=missing,
        warnings=warnings,
    )


def apply_hosted_upload_plan(provider: RemoteProvider, plan: HostedUploadPlan, *, upload_paks: bool) -> list[str]:
    written: list[str] = []
    if not plan.can_apply:
        raise RemoteProviderError("write", "Upload plan is incomplete.")
    try:
        provider.connect()
        provider.mkdirs(plan.remote_mods_dir)
        provider.write_file(plan.remote_modlist_path, plan.modlist_text)
        written.append(plan.remote_modlist_path)
        if upload_paks:
            for upload in plan.pak_uploads:
                provider.upload_bytes(upload.remote_path, upload.local_path.read_bytes())
                written.append(upload.remote_path)
    finally:
        provider.close()
    return written


def download_hosted_config_backups(
    provider: RemoteProvider,
    profile: HostedProfile,
    backup_root: Path,
) -> list[Path]:
    normalized = profile.normalized()
    saved: list[Path] = []
    try:
        provider.connect()
        detection = _detect_connected(provider, normalized)
        candidates = [detection.config_file, detection.engine_file]
        dest_dir = backup_root / "hosted_configs" / timestamp_slug()
        for remote_path in [candidate for candidate in candidates if candidate]:
            if not provider.path_exists(remote_path):
                continue
            ensure_dir(dest_dir)
            destination = dest_dir / _safe_backup_name(normalized.name, remote_path)
            destination.write_bytes(provider.read_file(remote_path))
            saved.append(destination)
    finally:
        provider.close()
    return saved


def provider_panel_fallback_text(active_mods: list[ActiveModEntry]) -> str:
    workshop_ids = [entry.workshop_id for entry in active_mods if entry.workshop_id]
    pak_names = [Path(entry.normalized_value).name for entry in active_mods if entry.normalized_value.endswith(".pak")]
    return "\n".join(
        [
            "Provider panel fallback",
            "Use this when the host does not expose ConanSandbox/Mods over FTP/SFTP.",
            "",
            "Ordered Workshop IDs:",
            *(workshop_ids or ["(no Workshop IDs on active entries)"]),
            "",
            "Ordered pak filenames:",
            *(pak_names or ["(no pak filenames on active entries)"]),
            "",
            "Restart the hosted server from the provider panel after applying changes.",
        ]
    )


def _detect_connected(provider: RemoteProvider, profile: HostedProfile) -> HostedPathDetection:
    base = normalize_remote_path(profile.server_folder)
    found = {path: provider.path_exists(join_remote_path(base, path)) for path in HOSTED_DETECTION_PATHS}

    server_folder = base
    sandbox_dir = join_remote_path(base, "ConanSandbox")
    if not provider.path_exists(sandbox_dir):
        if provider.path_exists(join_remote_path(base, "Mods")) and provider.path_exists(join_remote_path(base, "Saved")):
            sandbox_dir = base
            server_folder = base
        elif provider.path_exists("ConanSandbox"):
            server_folder = "."
            sandbox_dir = "ConanSandbox"

    mods_dir = profile.mods_folder_override or join_remote_path(sandbox_dir, "Mods")
    config_dir = profile.config_folder_override or join_remote_path(sandbox_dir, "Saved/Config/WindowsServer")
    config_file = profile.config_file_override or join_remote_path(config_dir, "ServerSettings.ini")
    engine_file = join_remote_path(config_dir, "Engine.ini")
    save_dir = profile.save_folder_override or join_remote_path(sandbox_dir, "Saved")
    log_dir = profile.log_folder_override or join_remote_path(save_dir, "Logs")
    found.update(
        {
            "Mods folder": provider.path_exists(mods_dir),
            "ServerSettings.ini": provider.path_exists(config_file),
            "Saves folder": provider.path_exists(save_dir),
            "Logs folder": provider.path_exists(log_dir),
        }
    )
    ok = provider.path_exists(sandbox_dir) or found.get("Mods folder", False)
    missing = [label for label in ("Mods folder", "ServerSettings.ini", "Saves folder", "Logs folder") if not found[label]]
    if ok and missing:
        message = "Connected. Some Conan paths need review: " + ", ".join(missing)
    elif ok:
        message = "Connected and detected Conan hosted folders."
    else:
        message = "Connected, but ConanSandbox paths were not found. Check the Server Folder value."
    return HostedPathDetection(
        profile_name=profile.name,
        server_folder=server_folder,
        mods_dir=mods_dir,
        modlist_path=join_remote_path(mods_dir, "modlist.txt"),
        config_dir=config_dir,
        config_file=config_file,
        engine_file=engine_file,
        save_dir=save_dir,
        log_dir=log_dir,
        found_paths=found,
        ok=ok,
        message=message,
    )


def _list_remote_paks(provider: RemoteProvider, mods_dir: str) -> list[str]:
    if not mods_dir or not provider.path_exists(mods_dir):
        return []
    return sorted(
        entry.path
        for entry in provider.list_dir(mods_dir)
        if not entry.is_dir and entry.name.casefold().endswith(".pak")
    )


def _safe_backup_name(profile_name: str, remote_path: str) -> str:
    safe_profile = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in profile_name).strip("_")
    safe_remote = remote_path.replace("\\", "/").strip("/").replace("/", "__")
    return f"{safe_profile or 'hosted'}__{safe_remote or 'config.ini'}"
