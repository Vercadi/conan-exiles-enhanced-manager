"""SteamCMD integration for Conan Exiles Workshop downloads."""
from __future__ import annotations

import os
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from ..models.workshop import (
    WORKSHOP_STATUS_DOWNLOADED,
    WORKSHOP_STATUS_MISSING,
    WorkshopItem,
)
from .subprocess_window import hidden_subprocess_kwargs

CONAN_WORKSHOP_APP_ID = "440900"


@dataclass(frozen=True)
class SteamCmdPathStatus:
    path: Path | None
    ok: bool
    message: str


@dataclass(frozen=True)
class SteamCmdProgress:
    kind: str
    message: str
    workshop_id: str = ""


@dataclass
class SteamCmdRunResult:
    command: list[str]
    returncode: int
    output_lines: list[str] = field(default_factory=list)
    error: str = ""
    canceled: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.canceled

    @property
    def output_text(self) -> str:
        return "\n".join(self.output_lines)


class SteamCmdRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        progress_callback: Callable[[SteamCmdProgress], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> SteamCmdRunResult:
        ...


def validate_steamcmd_path(path: Path | str | None) -> SteamCmdPathStatus:
    if not path:
        return SteamCmdPathStatus(None, False, "SteamCMD path is not configured.")
    candidate = Path(path)
    if not candidate.is_file():
        return SteamCmdPathStatus(candidate, False, f"steamcmd.exe was not found: {candidate}")
    if candidate.name.casefold() != "steamcmd.exe":
        return SteamCmdPathStatus(candidate, False, f"Expected steamcmd.exe, got: {candidate.name}")
    return SteamCmdPathStatus(candidate, True, f"SteamCMD ready: {candidate}")


def detect_steamcmd_path(data_dir: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    env_path = os.environ.get("STEAMCMD_PATH")
    if env_path:
        candidates.append(Path(env_path))
    if data_dir:
        base = Path(data_dir).resolve().parent
        candidates.extend(
            [
                base / "steamcmd" / "steamcmd.exe",
                Path(data_dir).resolve() / "steamcmd" / "steamcmd.exe",
            ]
        )
    candidates.extend(
        [
            Path.cwd() / "steamcmd" / "steamcmd.exe",
            Path("C:/steamcmd/steamcmd.exe"),
            Path("C:/Program Files (x86)/SteamCMD/steamcmd.exe"),
        ]
    )
    for candidate in candidates:
        if validate_steamcmd_path(candidate).ok:
            return candidate
    return None


def steamcmd_workshop_root(steamcmd_path: Path | str | None) -> Path | None:
    status = validate_steamcmd_path(steamcmd_path)
    if not status.ok or status.path is None:
        return None
    return status.path.parent / "steamapps" / "workshop" / "content" / CONAN_WORKSHOP_APP_ID


def build_workshop_download_command(
    steamcmd_path: Path,
    workshop_ids: list[str],
    *,
    username: str = "",
    validate: bool = True,
) -> list[str]:
    ids = _clean_workshop_ids(workshop_ids)
    command = [str(steamcmd_path), "+login", username.strip() or "anonymous"]
    for workshop_id in ids:
        command.extend(["+workshop_download_item", CONAN_WORKSHOP_APP_ID, workshop_id])
        if validate:
            command.append("validate")
    command.append("+quit")
    return command


def run_steamcmd(
    command: list[str],
    *,
    cwd: Path | None = None,
    progress_callback: Callable[[SteamCmdProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> SteamCmdRunResult:
    lines: list[str] = []
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden_subprocess_kwargs(),
        )
    except OSError as exc:
        return SteamCmdRunResult(command=command, returncode=1, error=str(exc))

    canceled = False
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.rstrip("\r\n")
        lines.append(line)
        if progress_callback:
            progress_callback(parse_steamcmd_progress(line))
        if cancel_event is not None and cancel_event.is_set():
            canceled = True
            process.terminate()
            break
    returncode = process.wait()
    if canceled:
        return SteamCmdRunResult(command=command, returncode=returncode, output_lines=lines, canceled=True)
    return SteamCmdRunResult(command=command, returncode=returncode, output_lines=lines)


def run_workshop_download(
    steamcmd_path: Path,
    workshop_ids: list[str],
    *,
    username: str = "",
    runner: SteamCmdRunner = run_steamcmd,
    progress_callback: Callable[[SteamCmdProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> SteamCmdRunResult:
    command = build_workshop_download_command(steamcmd_path, workshop_ids, username=username)
    return runner(
        command,
        cwd=steamcmd_path.parent,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )


def parse_steamcmd_progress(line: str) -> SteamCmdProgress:
    text = str(line or "").strip()
    lowered = text.casefold()
    workshop_id = _first_uint64(text)
    if "success" in lowered and ("download" in lowered or "installed" in lowered):
        return SteamCmdProgress("success", text, workshop_id)
    if "error" in lowered or "failed" in lowered:
        return SteamCmdProgress("error", text, workshop_id)
    if "downloading" in lowered or "workshop_download_item" in lowered:
        return SteamCmdProgress("download", text, workshop_id)
    if "%" in text:
        return SteamCmdProgress("progress", text, workshop_id)
    return SteamCmdProgress("info", text, workshop_id)


def missing_workshop_ids(items: list[WorkshopItem]) -> list[str]:
    return [item.workshop_id for item in items if item.status == WORKSHOP_STATUS_MISSING]


def downloaded_workshop_ids(items: list[WorkshopItem]) -> list[str]:
    return [item.workshop_id for item in items if item.status == WORKSHOP_STATUS_DOWNLOADED]


def _clean_workshop_ids(workshop_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in workshop_ids:
        workshop_id = str(value or "").strip()
        if not workshop_id or not workshop_id.isdigit() or workshop_id in seen:
            continue
        seen.add(workshop_id)
        cleaned.append(workshop_id)
    return cleaned


def _first_uint64(text: str) -> str:
    match = re.search(r"\b\d{5,20}\b", text)
    return match.group(0) if match else ""
