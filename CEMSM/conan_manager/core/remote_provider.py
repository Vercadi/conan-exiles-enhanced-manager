"""FTP/SFTP provider abstraction for hosted Conan servers."""
from __future__ import annotations

import ftplib
import io
import stat
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..models.hosted import HostedProfile, PROTOCOL_FTP, PROTOCOL_SFTP, join_remote_path, parent_remote_path


class RemoteProviderError(RuntimeError):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class RemoteEntry:
    path: str
    name: str
    is_dir: bool = False
    size: int | None = None


class RemoteProvider(ABC):
    def __init__(self, profile: HostedProfile):
        self.profile = profile.normalized()

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_dir(self, path: str) -> list[RemoteEntry]:
        raise NotImplementedError

    @abstractmethod
    def path_exists(self, path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def read_file(self, path: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def upload_bytes(self, path: str, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    def mkdirs(self, path: str) -> None:
        raise NotImplementedError

    def write_file(self, path: str, text: str, *, encoding: str = "utf-8") -> None:
        self.upload_bytes(path, text.encode(encoding))

    def __enter__(self) -> "RemoteProvider":
        self.connect()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()


class FtpRemoteProvider(RemoteProvider):
    def __init__(self, profile: HostedProfile):
        super().__init__(profile)
        self._ftp: ftplib.FTP | None = None

    def connect(self) -> None:
        try:
            ftp = ftplib.FTP()
            ftp.connect(self.profile.host, self.profile.port, timeout=20)
            ftp.login(self.profile.username, self.profile.password or "")
            self._ftp = ftp
        except Exception as exc:  # noqa: BLE001 - normalize provider-specific failures
            raise RemoteProviderError("connection", f"FTP connection failed: {exc}") from exc

    def close(self) -> None:
        if not self._ftp:
            return
        try:
            self._ftp.quit()
        except Exception:
            self._ftp.close()
        finally:
            self._ftp = None

    def list_dir(self, path: str) -> list[RemoteEntry]:
        ftp = self._require()
        remote_path = _ftp_path(path)
        entries: list[RemoteEntry] = []
        try:
            for name, facts in ftp.mlsd(remote_path):
                if name in (".", ".."):
                    continue
                kind = str(facts.get("type") or "").casefold()
                size_text = facts.get("size")
                entries.append(
                    RemoteEntry(
                        path=join_remote_path(path, name),
                        name=name,
                        is_dir=kind == "dir",
                        size=int(size_text) if size_text and str(size_text).isdigit() else None,
                    )
                )
            return entries
        except Exception:
            try:
                names = ftp.nlst(remote_path)
            except Exception as exc:  # noqa: BLE001
                raise RemoteProviderError("path", f"Could not list remote path {path}: {exc}") from exc
            return [
                RemoteEntry(path=join_remote_path(path, PurePosixPath(name).name), name=PurePosixPath(name).name)
                for name in names
                if PurePosixPath(name).name not in (".", "..")
            ]

    def path_exists(self, path: str) -> bool:
        ftp = self._require()
        remote_path = _ftp_path(path)
        current = "."
        try:
            current = ftp.pwd()
            ftp.cwd(remote_path)
            ftp.cwd(current)
            return True
        except Exception:
            try:
                parent = _ftp_path(parent_remote_path(path))
                name = PurePosixPath(remote_path).name
                return name in [PurePosixPath(item).name for item in ftp.nlst(parent)]
            except Exception:
                try:
                    ftp.cwd(current)
                except Exception:
                    pass
                return False

    def read_file(self, path: str) -> bytes:
        ftp = self._require()
        output = io.BytesIO()
        try:
            ftp.retrbinary(f"RETR {_ftp_path(path)}", output.write)
        except Exception as exc:  # noqa: BLE001
            raise RemoteProviderError("path", f"Could not read remote file {path}: {exc}") from exc
        return output.getvalue()

    def upload_bytes(self, path: str, data: bytes) -> None:
        ftp = self._require()
        self.mkdirs(parent_remote_path(path))
        try:
            ftp.storbinary(f"STOR {_ftp_path(path)}", io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001
            raise RemoteProviderError("write", f"Could not upload remote file {path}: {exc}") from exc

    def mkdirs(self, path: str) -> None:
        ftp = self._require()
        normalized = _ftp_path(path)
        if normalized in (".", "/"):
            return
        current = ftp.pwd()
        try:
            if normalized.startswith("/"):
                ftp.cwd("/")
                parts = [part for part in normalized.split("/") if part]
            else:
                parts = [part for part in normalized.split("/") if part]
            for part in parts:
                try:
                    ftp.cwd(part)
                except Exception:
                    ftp.mkd(part)
                    ftp.cwd(part)
        except Exception as exc:  # noqa: BLE001
            raise RemoteProviderError("write", f"Could not create remote folder {path}: {exc}") from exc
        finally:
            try:
                ftp.cwd(current)
            except Exception:
                pass

    def _require(self) -> ftplib.FTP:
        if self._ftp is None:
            raise RemoteProviderError("connection", "FTP provider is not connected.")
        return self._ftp


class SftpRemoteProvider(RemoteProvider):
    def __init__(self, profile: HostedProfile):
        super().__init__(profile)
        self._ssh = None
        self._sftp = None

    def connect(self) -> None:
        try:
            import paramiko

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = {
                "hostname": self.profile.host,
                "port": self.profile.port,
                "username": self.profile.username,
                "timeout": 20,
            }
            if self.profile.private_key_path:
                kwargs["key_filename"] = str(self.profile.private_key_path)
            if self.profile.password:
                kwargs["password"] = self.profile.password
            ssh.connect(**kwargs)
            self._ssh = ssh
            self._sftp = ssh.open_sftp()
        except ImportError as exc:
            raise RemoteProviderError("connection", "SFTP support requires paramiko to be installed.") from exc
        except Exception as exc:  # noqa: BLE001
            raise RemoteProviderError("connection", f"SFTP connection failed: {exc}") from exc

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
        if self._ssh:
            self._ssh.close()
        self._sftp = None
        self._ssh = None

    def list_dir(self, path: str) -> list[RemoteEntry]:
        sftp = self._require()
        try:
            attrs = sftp.listdir_attr(_sftp_path(path))
        except Exception as exc:  # noqa: BLE001
            raise RemoteProviderError("path", f"Could not list remote path {path}: {exc}") from exc
        return [
            RemoteEntry(
                path=join_remote_path(path, item.filename),
                name=item.filename,
                is_dir=stat.S_ISDIR(item.st_mode or 0),
                size=int(item.st_size) if item.st_size is not None else None,
            )
            for item in attrs
            if item.filename not in (".", "..")
        ]

    def path_exists(self, path: str) -> bool:
        sftp = self._require()
        try:
            sftp.stat(_sftp_path(path))
            return True
        except Exception:
            return False

    def read_file(self, path: str) -> bytes:
        sftp = self._require()
        try:
            with sftp.open(_sftp_path(path), "rb") as handle:
                return handle.read()
        except Exception as exc:  # noqa: BLE001
            raise RemoteProviderError("path", f"Could not read remote file {path}: {exc}") from exc

    def upload_bytes(self, path: str, data: bytes) -> None:
        sftp = self._require()
        self.mkdirs(parent_remote_path(path))
        try:
            with sftp.open(_sftp_path(path), "wb") as handle:
                handle.write(data)
        except Exception as exc:  # noqa: BLE001
            raise RemoteProviderError("write", f"Could not upload remote file {path}: {exc}") from exc

    def mkdirs(self, path: str) -> None:
        sftp = self._require()
        normalized = _sftp_path(path)
        if normalized in (".", "/"):
            return
        current = "/" if normalized.startswith("/") else "."
        for part in [piece for piece in normalized.split("/") if piece]:
            current = join_remote_path(current, part)
            if not self.path_exists(current):
                try:
                    sftp.mkdir(_sftp_path(current))
                except Exception as exc:  # noqa: BLE001
                    raise RemoteProviderError("write", f"Could not create remote folder {current}: {exc}") from exc

    def _require(self):
        if self._sftp is None:
            raise RemoteProviderError("connection", "SFTP provider is not connected.")
        return self._sftp


def create_remote_provider(profile: HostedProfile) -> RemoteProvider:
    normalized = profile.normalized()
    if normalized.protocol == PROTOCOL_FTP:
        return FtpRemoteProvider(normalized)
    if normalized.protocol == PROTOCOL_SFTP:
        return SftpRemoteProvider(normalized)
    raise RemoteProviderError("connection", f"Unsupported hosted protocol: {profile.protocol}")


def remote_error_summary(exc: RemoteProviderError) -> str:
    if exc.kind == "connection":
        return f"Connection failed: {exc.message}"
    if exc.kind == "write":
        return f"Remote write failed: {exc.message}"
    return f"Remote path check failed: {exc.message}"


def _ftp_path(path: str) -> str:
    normalized = str(path or ".").replace("\\", "/")
    return normalized or "."


def _sftp_path(path: str) -> str:
    normalized = str(path or ".").replace("\\", "/")
    return normalized or "."
