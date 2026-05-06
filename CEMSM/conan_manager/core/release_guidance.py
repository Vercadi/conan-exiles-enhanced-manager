"""First-run and release-candidate user guidance helpers."""
from __future__ import annotations

from pathlib import Path

from ..models.app_paths import ConanAppPaths
from .steamcmd_workshop import validate_steamcmd_path


def first_run_guidance(paths: ConanAppPaths, *, steamcmd_path: str | Path | None = None) -> list[str]:
    messages: list[str] = []
    if not paths.client_root:
        messages.append("Conan Exiles Enhanced was not detected. Install it through Steam or set the game path after discovery.")
    if not paths.dedicated_server_root:
        messages.append("Conan Exiles Dedicated Server was not detected. Install Steam app 443030 if you want local server management.")
    status = validate_steamcmd_path(steamcmd_path)
    if not status.ok:
        messages.append(steamcmd_setup_guidance(status.message))
    return messages


def steamcmd_setup_guidance(reason: str = "") -> str:
    suffix = f" Current status: {reason}" if reason else ""
    return (
        "SteamCMD is not configured. Download SteamCMD from Valve, extract it to a stable folder, "
        "then set steamcmd.exe in Settings > SteamCMD before using Workshop downloads."
        + suffix
    )


def workshop_download_failure_summary(output_text: str, *, max_length: int = 240) -> str:
    lines = [line.strip() for line in str(output_text or "").splitlines() if line.strip()]
    interesting = [
        line
        for line in lines
        if any(token in line.casefold() for token in ("error", "failed", "timeout", "login", "subscribe", "license"))
    ]
    if interesting:
        return interesting[-1][:max_length]
    if lines:
        return lines[-1][:max_length]
    return "SteamCMD exited without a success result."


def steamcmd_may_need_account(output_text: str) -> bool:
    lowered = str(output_text or "").casefold()
    return any(token in lowered for token in ("login", "subscribe", "subscription", "license", "ownership"))
