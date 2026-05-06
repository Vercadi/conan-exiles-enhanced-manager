"""Dedicated server process detection."""
from __future__ import annotations

import csv
import subprocess
from dataclasses import dataclass
from io import StringIO
from typing import Callable, Iterable

from ..models.server import ProcessInfo, ServerProcessStatus

SERVER_PROCESS_NAMES = {
    "conansandboxserver.exe",
    "conansandboxserver-win64-shipping.exe",
}


class ServerProcessService:
    def __init__(self, process_provider: Callable[[], Iterable[ProcessInfo]] | None = None):
        self.process_provider = process_provider or tasklist_process_provider

    def status(self) -> ServerProcessStatus:
        matches = [
            process for process in self.process_provider()
            if process.name.casefold() in SERVER_PROCESS_NAMES
        ]
        return ServerProcessStatus(running=bool(matches), processes=matches)


def tasklist_process_provider() -> list[ProcessInfo]:
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    processes: list[ProcessInfo] = []
    for row in csv.reader(StringIO(result.stdout)):
        if len(row) < 2:
            continue
        try:
            pid = int(row[1])
        except ValueError:
            continue
        processes.append(ProcessInfo(pid=pid, name=row[0]))
    return processes
