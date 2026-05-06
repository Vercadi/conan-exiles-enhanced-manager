"""Dedicated server launch planning and explicit launch support."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ..models.app_paths import ConanAppPaths
from ..models.server import ServerLaunchPlan, ServerLaunchResult
from .server_process import ServerProcessService

DEFAULT_SERVER_ARGS = "-Messaging"


def dedicated_server_executable(paths: ConanAppPaths) -> Path | None:
    if not paths.dedicated_server_root:
        return None
    return paths.dedicated_server_root / "ConanSandboxServer.exe"


def build_launch_plan(paths: ConanAppPaths, launch_args: str = DEFAULT_SERVER_ARGS) -> ServerLaunchPlan | None:
    executable = dedicated_server_executable(paths)
    if executable is None:
        return None
    args = split_launch_args(launch_args)
    return ServerLaunchPlan(executable=executable, args=args, cwd=executable.parent)


def split_launch_args(launch_args: str) -> list[str]:
    if not str(launch_args or "").strip():
        return []
    return shlex.split(str(launch_args), posix=False)


def launch_dedicated_server(
    paths: ConanAppPaths,
    *,
    launch_args: str = DEFAULT_SERVER_ARGS,
    process_service: ServerProcessService | None = None,
) -> ServerLaunchResult:
    service = process_service or ServerProcessService()
    if service.status().running:
        return ServerLaunchResult(started=False, message="Dedicated server is already running.")
    plan = build_launch_plan(paths, launch_args)
    if plan is None:
        return ServerLaunchResult(started=False, message="Dedicated server path is not configured.")
    if not plan.executable.is_file():
        return ServerLaunchResult(started=False, message=f"Dedicated server executable was not found: {plan.executable}")

    process = subprocess.Popen(plan.command, cwd=str(plan.cwd))
    return ServerLaunchResult(
        started=True,
        message="Dedicated server launch requested.",
        command=plan.command,
        pid=process.pid,
    )
