from __future__ import annotations

from pathlib import Path

from conan_manager.core.hosted_profile_store import HostedProfileStore
from conan_manager.core.hosted_service import (
    apply_hosted_upload_plan,
    build_hosted_upload_plan,
    detect_hosted_paths,
    download_hosted_config_backups,
    scan_hosted_inventory,
)
from conan_manager.core.remote_provider import (
    FtpRemoteProvider,
    RemoteEntry,
    RemoteProvider,
    RemoteProviderError,
    SftpRemoteProvider,
    create_remote_provider,
    remote_error_summary,
)
from conan_manager.models.hosted import HostedPathDetection, HostedProfile, join_remote_path, parent_remote_path
from conan_manager.models.modlist import ActiveModEntry


def test_hosted_profile_serialization_does_not_store_plaintext_password(tmp_path) -> None:
    store = HostedProfileStore(tmp_path)
    profile = HostedProfile(
        name="My Host",
        protocol="sftp",
        host="example.invalid",
        username="admin",
        password="top-secret",
        private_key_path=tmp_path / "id_ed25519",
        server_folder="server",
    )

    saved = store.upsert(profile)
    raw = (tmp_path / "hosted_profiles.json").read_text(encoding="utf-8")
    loaded = HostedProfileStore(tmp_path).get("My Host")

    assert saved.password == "top-secret"
    assert "top-secret" not in raw
    assert loaded is not None
    assert loaded.password == ""
    assert "top-secret" not in str(profile.to_redacted_dict())
    assert str(tmp_path / "id_ed25519") not in str(profile.to_redacted_dict())


def test_fake_remote_provider_path_detection_finds_conan_layout() -> None:
    provider = FakeRemoteProvider.with_conan_layout(HostedProfile(name="Host"))

    detection = detect_hosted_paths(provider, provider.profile)

    assert detection.ok
    assert detection.mods_dir == "ConanSandbox/Mods"
    assert detection.config_file == "ConanSandbox/Saved/Config/WindowsServer/ServerSettings.ini"
    assert detection.found_paths["Mods folder"]


def test_remote_provider_factory_returns_protocol_provider_types() -> None:
    assert isinstance(create_remote_provider(HostedProfile(protocol="ftp", host="host")), FtpRemoteProvider)
    assert isinstance(create_remote_provider(HostedProfile(protocol="sftp", host="host")), SftpRemoteProvider)


def test_hosted_upload_plan_uses_remote_pak_names_and_reports_missing(tmp_path) -> None:
    existing = tmp_path / "First.pak"
    missing = tmp_path / "Missing.pak"
    existing.write_bytes(b"pak")
    detection = HostedPathDetection(
        profile_name="Host",
        mods_dir="ConanSandbox/Mods",
        modlist_path="ConanSandbox/Mods/modlist.txt",
        ok=True,
    )

    plan = build_hosted_upload_plan(
        HostedProfile(name="Host"),
        detection,
        [ActiveModEntry(str(existing)), ActiveModEntry(str(missing))],
    )

    assert plan.modlist_entries == ["First.pak", "Missing.pak"]
    assert plan.modlist_text == "First.pak\nMissing.pak\n"
    assert plan.pak_uploads[0].remote_path == "ConanSandbox/Mods/First.pak"
    assert plan.missing_local_paks == [str(missing)]


def test_apply_hosted_upload_plan_writes_modlist_and_selected_paks(tmp_path) -> None:
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak-bytes")
    provider = FakeRemoteProvider.with_conan_layout(HostedProfile(name="Host"))
    detection = detect_hosted_paths(provider, provider.profile)
    plan = build_hosted_upload_plan(provider.profile, detection, [ActiveModEntry(str(pak))])

    written = apply_hosted_upload_plan(provider, plan, upload_paks=True)

    assert "ConanSandbox/Mods/modlist.txt" in written
    assert "ConanSandbox/Mods/Example.pak" in written
    assert provider.files["ConanSandbox/Mods/modlist.txt"] == b"Example.pak\n"
    assert provider.files["ConanSandbox/Mods/Example.pak"] == b"pak-bytes"


def test_scan_hosted_inventory_reads_remote_modlist_and_ini_files() -> None:
    provider = FakeRemoteProvider.with_conan_layout(HostedProfile(name="Host"))
    provider.files["ConanSandbox/Mods/Example.pak"] = b"pak"
    provider.files["ConanSandbox/Mods/modlist.txt"] = b"Example.pak\n"

    inventory = scan_hosted_inventory(provider, provider.profile)

    assert inventory.detection.ok
    assert inventory.pak_files == ["ConanSandbox/Mods/Example.pak"]
    assert inventory.modlist_text == "Example.pak\n"
    assert "ServerSettings.ini" in inventory.config_files[0]


def test_download_hosted_config_backups_saves_server_and_engine_files(tmp_path) -> None:
    provider = FakeRemoteProvider.with_conan_layout(HostedProfile(name="Host"))
    provider.files["ConanSandbox/Saved/Config/WindowsServer/Engine.ini"] = b"[RConPlugin]\n"

    backups = download_hosted_config_backups(provider, provider.profile, tmp_path / "backups")

    assert len(backups) == 2
    assert all(path.is_file() for path in backups)
    assert any(path.read_bytes() == b"[ServerSettings]\n" for path in backups)


def test_connection_and_path_error_wording_is_actionable() -> None:
    connection = remote_error_summary(RemoteProviderError("connection", "No route to host"))
    path = remote_error_summary(RemoteProviderError("path", "Missing ConanSandbox"))

    assert connection.startswith("Connection failed:")
    assert path.startswith("Remote path check failed:")

    provider = FailingProvider(HostedProfile(name="Broken"))
    detection = detect_hosted_paths(provider, provider.profile)

    assert not detection.ok
    assert detection.message.startswith("Connection failed:")


class FakeRemoteProvider(RemoteProvider):
    def __init__(self, profile: HostedProfile, *, dirs: set[str] | None = None, files: dict[str, bytes] | None = None):
        super().__init__(profile)
        self.dirs = {self._n(path) for path in (dirs or {"."})}
        self.files = {self._n(path): data for path, data in (files or {}).items()}
        self.connected = False

    @classmethod
    def with_conan_layout(cls, profile: HostedProfile) -> "FakeRemoteProvider":
        return cls(
            profile,
            dirs={
                ".",
                "ConanSandbox",
                "ConanSandbox/Mods",
                "ConanSandbox/Saved",
                "ConanSandbox/Saved/Config",
                "ConanSandbox/Saved/Config/WindowsServer",
                "ConanSandbox/Saved/Logs",
            },
            files={
                "ConanSandbox/Saved/Config/WindowsServer/ServerSettings.ini": b"[ServerSettings]\n",
                "ConanSandbox/Saved/Logs/ConanSandbox.log": b"log\n",
            },
        )

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def list_dir(self, path: str) -> list[RemoteEntry]:
        parent = self._n(path)
        prefix = "" if parent == "." else parent + "/"
        entries: list[RemoteEntry] = []
        names: set[str] = set()
        for directory in self.dirs:
            if directory == parent or not directory.startswith(prefix):
                continue
            name = directory[len(prefix) :].split("/", 1)[0]
            names.add(name)
        for file_path in self.files:
            if not file_path.startswith(prefix):
                continue
            name = file_path[len(prefix) :].split("/", 1)[0]
            names.add(name)
        for name in sorted(names):
            child_path = join_remote_path(parent, name)
            entries.append(
                RemoteEntry(
                    path=child_path,
                    name=name,
                    is_dir=child_path in self.dirs,
                    size=len(self.files[child_path]) if child_path in self.files else None,
                )
            )
        return entries

    def path_exists(self, path: str) -> bool:
        normalized = self._n(path)
        return normalized in self.dirs or normalized in self.files

    def read_file(self, path: str) -> bytes:
        normalized = self._n(path)
        if normalized not in self.files:
            raise RemoteProviderError("path", f"Missing remote file {path}")
        return self.files[normalized]

    def upload_bytes(self, path: str, data: bytes) -> None:
        normalized = self._n(path)
        self.mkdirs(parent_remote_path(normalized))
        self.files[normalized] = data

    def mkdirs(self, path: str) -> None:
        normalized = self._n(path)
        if normalized in ("", "."):
            self.dirs.add(".")
            return
        current = "." if not normalized.startswith("/") else "/"
        for part in [piece for piece in normalized.split("/") if piece]:
            current = join_remote_path(current, part)
            self.dirs.add(current)

    @staticmethod
    def _n(path: str) -> str:
        text = str(path or ".").replace("\\", "/").rstrip("/")
        return text or "."


class FailingProvider(FakeRemoteProvider):
    def connect(self) -> None:
        raise RemoteProviderError("connection", "No route to host")
