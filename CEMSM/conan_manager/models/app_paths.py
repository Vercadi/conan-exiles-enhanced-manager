from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _path_to_str(path: Optional[Path]) -> Optional[str]:
    return str(path) if path else None


def _path_from_str(value: Optional[str]) -> Optional[Path]:
    return Path(value) if value else None


@dataclass
class SteamAppManifest:
    """Small subset of a Steam appmanifest needed by the manager."""

    appid: str
    name: str = ""
    installdir: str = ""
    buildid: str = ""
    last_updated: str = ""
    size_on_disk: str = ""
    manifest_path: Optional[Path] = None
    library_root: Optional[Path] = None

    def to_dict(self) -> dict:
        return {
            "appid": self.appid,
            "name": self.name,
            "installdir": self.installdir,
            "buildid": self.buildid,
            "last_updated": self.last_updated,
            "size_on_disk": self.size_on_disk,
            "manifest_path": _path_to_str(self.manifest_path),
            "library_root": _path_to_str(self.library_root),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> Optional["SteamAppManifest"]:
        if not isinstance(data, dict) or not data.get("appid"):
            return None
        return cls(
            appid=str(data.get("appid") or ""),
            name=str(data.get("name") or ""),
            installdir=str(data.get("installdir") or ""),
            buildid=str(data.get("buildid") or ""),
            last_updated=str(data.get("last_updated") or ""),
            size_on_disk=str(data.get("size_on_disk") or ""),
            manifest_path=_path_from_str(data.get("manifest_path")),
            library_root=_path_from_str(data.get("library_root")),
        )


@dataclass
class ConanAppPaths:
    """Resolved paths and Steam metadata for the local Conan setup."""

    client_root: Optional[Path] = None
    dedicated_server_root: Optional[Path] = None
    steamapps_dirs: list[Path] = field(default_factory=list)
    workshop_content_dir: Optional[Path] = None
    client_manifest: Optional[SteamAppManifest] = None
    dedicated_server_manifest: Optional[SteamAppManifest] = None
    backup_dir: Optional[Path] = None
    data_dir: Optional[Path] = None

    @property
    def client_config_dir(self) -> Optional[Path]:
        if self.client_root:
            return self.client_root / "ConanSandbox" / "Saved" / "Config" / "Windows"
        return None

    @property
    def dedicated_server_config_dir(self) -> Optional[Path]:
        if self.dedicated_server_root:
            return self.dedicated_server_root / "ConanSandbox" / "Saved" / "Config" / "WindowsServer"
        return None

    @property
    def client_save_root(self) -> Optional[Path]:
        if self.client_root:
            return self.client_root / "ConanSandbox" / "Saved"
        return None

    @property
    def dedicated_server_save_root(self) -> Optional[Path]:
        if self.dedicated_server_root:
            return self.dedicated_server_root / "ConanSandbox" / "Saved"
        return None

    @property
    def client_log_dir(self) -> Optional[Path]:
        if self.client_save_root:
            return self.client_save_root / "Logs"
        return None

    @property
    def dedicated_server_log_dir(self) -> Optional[Path]:
        if self.dedicated_server_save_root:
            return self.dedicated_server_save_root / "Logs"
        return None

    @property
    def client_mods_dir(self) -> Optional[Path]:
        if self.client_root:
            return self.client_root / "ConanSandbox" / "Mods"
        return None

    @property
    def client_modlist_path(self) -> Optional[Path]:
        if self.client_mods_dir:
            return self.client_mods_dir / "modlist.txt"
        return None

    @property
    def dedicated_server_mods_dir(self) -> Optional[Path]:
        if self.dedicated_server_root:
            return self.dedicated_server_root / "ConanSandbox" / "Mods"
        return None

    @property
    def dedicated_server_modlist_path(self) -> Optional[Path]:
        if self.dedicated_server_mods_dir:
            return self.dedicated_server_mods_dir / "modlist.txt"
        return None

    @property
    def client_server_settings(self) -> Optional[Path]:
        config = self.client_config_dir
        return config / "ServerSettings.ini" if config else None

    @property
    def dedicated_server_settings(self) -> Optional[Path]:
        config = self.dedicated_server_config_dir
        return config / "ServerSettings.ini" if config else None

    @property
    def dedicated_server_engine_ini(self) -> Optional[Path]:
        config = self.dedicated_server_config_dir
        return config / "Engine.ini" if config else None

    @property
    def dedicated_server_game_ini(self) -> Optional[Path]:
        config = self.dedicated_server_config_dir
        return config / "Game.ini" if config else None

    @property
    def dedicated_server_game_user_settings(self) -> Optional[Path]:
        config = self.dedicated_server_config_dir
        return config / "GameUserSettings.ini" if config else None

    def client_save_databases(self) -> list[Path]:
        return _database_files(self.client_save_root)

    def dedicated_server_save_databases(self) -> list[Path]:
        return _database_files(self.dedicated_server_save_root)

    def config_files(self) -> list[Path]:
        roots = [self.client_config_dir, self.dedicated_server_config_dir]
        files: list[Path] = []
        for root in roots:
            if root and root.is_dir():
                files.extend(sorted(root.glob("*.ini")))
        return files

    def save_database_files(self) -> list[Path]:
        return self.client_save_databases() + self.dedicated_server_save_databases()

    def to_dict(self) -> dict:
        return {
            "client_root": _path_to_str(self.client_root),
            "dedicated_server_root": _path_to_str(self.dedicated_server_root),
            "steamapps_dirs": [str(path) for path in self.steamapps_dirs],
            "workshop_content_dir": _path_to_str(self.workshop_content_dir),
            "client_manifest": self.client_manifest.to_dict() if self.client_manifest else None,
            "dedicated_server_manifest": (
                self.dedicated_server_manifest.to_dict() if self.dedicated_server_manifest else None
            ),
            "backup_dir": _path_to_str(self.backup_dir),
            "data_dir": _path_to_str(self.data_dir),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ConanAppPaths":
        if not isinstance(data, dict):
            return cls()
        return cls(
            client_root=_path_from_str(data.get("client_root")),
            dedicated_server_root=_path_from_str(data.get("dedicated_server_root")),
            steamapps_dirs=[Path(value) for value in data.get("steamapps_dirs", []) if value],
            workshop_content_dir=_path_from_str(data.get("workshop_content_dir")),
            client_manifest=SteamAppManifest.from_dict(data.get("client_manifest")),
            dedicated_server_manifest=SteamAppManifest.from_dict(data.get("dedicated_server_manifest")),
            backup_dir=_path_from_str(data.get("backup_dir")),
            data_dir=_path_from_str(data.get("data_dir")),
        )


def _database_files(root: Optional[Path]) -> list[Path]:
    if not root or not root.is_dir():
        return []
    return sorted(path for path in root.glob("*.db") if path.is_file())
