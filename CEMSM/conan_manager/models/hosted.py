from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROTOCOL_FTP = "ftp"
PROTOCOL_SFTP = "sftp"
HOSTED_PROTOCOLS = (PROTOCOL_SFTP, PROTOCOL_FTP)


def default_port(protocol: str) -> int:
    return 21 if str(protocol).casefold() == PROTOCOL_FTP else 22


def normalize_remote_path(value: str | None) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if text in ("", "/"):
        return "."
    return text.rstrip("/")


def join_remote_path(*parts: str | None) -> str:
    cleaned: list[str] = []
    absolute = False
    for part in parts:
        text = str(part or "").strip().replace("\\", "/")
        if not text or text == ".":
            continue
        if text.startswith("/") and not cleaned:
            absolute = True
        cleaned.extend(piece for piece in text.split("/") if piece and piece != ".")
    if not cleaned:
        return "/" if absolute else "."
    return ("/" if absolute else "") + "/".join(cleaned)


def parent_remote_path(path: str) -> str:
    normalized = normalize_remote_path(path)
    if normalized in (".", "/"):
        return normalized
    parts = normalized.split("/")
    if len(parts) <= 1:
        return "."
    if normalized.startswith("/") and len(parts) == 2:
        return "/"
    return "/".join(parts[:-1]) or "."


@dataclass
class HostedProfile:
    """Connection and Conan path settings for a rented/hosted server."""

    name: str = "Default Hosted"
    protocol: str = PROTOCOL_SFTP
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = field(default="", repr=False)
    private_key_path: Optional[Path] = None
    server_folder: str = "."
    mods_folder_override: str = ""
    config_folder_override: str = ""
    config_file_override: str = ""
    save_folder_override: str = ""
    log_folder_override: str = ""

    def normalized(self) -> "HostedProfile":
        protocol = str(self.protocol or PROTOCOL_SFTP).casefold()
        if protocol not in HOSTED_PROTOCOLS:
            protocol = PROTOCOL_SFTP
        port = int(self.port or default_port(protocol))
        if port <= 0:
            port = default_port(protocol)
        return HostedProfile(
            name=str(self.name or "Default Hosted").strip() or "Default Hosted",
            protocol=protocol,
            host=str(self.host or "").strip(),
            port=port,
            username=str(self.username or "").strip(),
            password=str(self.password or ""),
            private_key_path=Path(self.private_key_path) if self.private_key_path else None,
            server_folder=normalize_remote_path(self.server_folder),
            mods_folder_override=normalize_remote_path(self.mods_folder_override)
            if self.mods_folder_override
            else "",
            config_folder_override=normalize_remote_path(self.config_folder_override)
            if self.config_folder_override
            else "",
            config_file_override=normalize_remote_path(self.config_file_override)
            if self.config_file_override
            else "",
            save_folder_override=normalize_remote_path(self.save_folder_override)
            if self.save_folder_override
            else "",
            log_folder_override=normalize_remote_path(self.log_folder_override)
            if self.log_folder_override
            else "",
        )

    def to_dict(self) -> dict:
        normalized = self.normalized()
        return {
            "name": normalized.name,
            "protocol": normalized.protocol,
            "host": normalized.host,
            "port": normalized.port,
            "username": normalized.username,
            "password": "",
            "private_key_path": str(normalized.private_key_path) if normalized.private_key_path else None,
            "server_folder": normalized.server_folder,
            "mods_folder_override": normalized.mods_folder_override,
            "config_folder_override": normalized.config_folder_override,
            "config_file_override": normalized.config_file_override,
            "save_folder_override": normalized.save_folder_override,
            "log_folder_override": normalized.log_folder_override,
        }

    def to_redacted_dict(self) -> dict:
        data = self.to_dict()
        data["password"] = "<not stored>"
        if data.get("private_key_path"):
            data["private_key_path"] = "<configured>"
        return data

    @classmethod
    def from_dict(cls, data: dict | None) -> "HostedProfile":
        if not isinstance(data, dict):
            return cls()
        return cls(
            name=str(data.get("name") or "Default Hosted"),
            protocol=str(data.get("protocol") or PROTOCOL_SFTP),
            host=str(data.get("host") or ""),
            port=int(data.get("port") or default_port(str(data.get("protocol") or PROTOCOL_SFTP))),
            username=str(data.get("username") or ""),
            password="",
            private_key_path=Path(data["private_key_path"]) if data.get("private_key_path") else None,
            server_folder=str(data.get("server_folder") or "."),
            mods_folder_override=str(data.get("mods_folder_override") or ""),
            config_folder_override=str(data.get("config_folder_override") or ""),
            config_file_override=str(data.get("config_file_override") or ""),
            save_folder_override=str(data.get("save_folder_override") or ""),
            log_folder_override=str(data.get("log_folder_override") or ""),
        ).normalized()


@dataclass
class HostedPathDetection:
    profile_name: str
    server_folder: str = "."
    mods_dir: str = ""
    modlist_path: str = ""
    config_dir: str = ""
    config_file: str = ""
    engine_file: str = ""
    save_dir: str = ""
    log_dir: str = ""
    found_paths: dict[str, bool] = field(default_factory=dict)
    ok: bool = False
    message: str = ""

    @property
    def missing_labels(self) -> list[str]:
        return [label for label, exists in self.found_paths.items() if not exists]


@dataclass
class HostedInventory:
    detection: HostedPathDetection
    pak_files: list[str] = field(default_factory=list)
    modlist_text: str = ""
    config_files: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class HostedPakUpload:
    local_path: Path
    remote_path: str


@dataclass
class HostedUploadPlan:
    profile_name: str
    remote_mods_dir: str
    remote_modlist_path: str
    modlist_text: str
    modlist_entries: list[str] = field(default_factory=list)
    pak_uploads: list[HostedPakUpload] = field(default_factory=list)
    missing_local_paks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    restart_required: bool = True

    @property
    def can_apply(self) -> bool:
        return bool(self.remote_mods_dir and self.remote_modlist_path and self.modlist_entries)
