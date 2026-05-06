from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProcessInfo:
    pid: int
    name: str


@dataclass
class ServerProcessStatus:
    running: bool = False
    processes: list[ProcessInfo] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.running:
            return "Stopped"
        names = ", ".join(f"{process.name} ({process.pid})" for process in self.processes)
        return f"Running: {names}"


@dataclass
class ServerConfigSnapshot:
    server_name: str = ""
    server_password_set: bool = False
    admin_password_set: bool = False
    max_players: str = ""
    pvp_enabled: str = ""
    battleye_enabled: str = ""
    server_mod_list: str = ""
    game_port: str = "7777"
    query_port: str = "27015"
    rcon_enabled: str = ""
    rcon_port: str = "25575"
    rcon_password_set: bool = False
    server_settings_path: Optional[Path] = None
    engine_ini_path: Optional[Path] = None

    @property
    def port_summary(self) -> str:
        rcon = f", RCON {self.rcon_port}"
        if self.rcon_enabled:
            rcon += f" ({self.rcon_enabled})"
        return f"Game {self.game_port}, Pinger {int_or_default(self.game_port, 7777) + 1}, Query {self.query_port}{rcon}"


@dataclass
class ServerLogSnapshot:
    log_path: Optional[Path] = None
    tail: str = ""
    filtered: str = ""


@dataclass
class ServerLaunchPlan:
    executable: Path
    args: list[str]
    cwd: Path

    @property
    def command(self) -> list[str]:
        return [str(self.executable), *self.args]


@dataclass
class ServerLaunchResult:
    started: bool
    message: str
    command: list[str] = field(default_factory=list)
    pid: Optional[int] = None


@dataclass
class ServerRuntimeState:
    restart_recommended: bool = False
    restart_reason: str = ""

    def mark_restart_recommended(self, reason: str) -> None:
        self.restart_recommended = True
        self.restart_reason = reason

    def clear_restart_recommended(self) -> None:
        self.restart_recommended = False
        self.restart_reason = ""


def int_or_default(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
