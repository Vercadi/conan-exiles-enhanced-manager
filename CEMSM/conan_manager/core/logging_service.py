"""Application-wide logging setup."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

_configured = False


def setup_logging(log_dir: Optional[Path] = None, level: int = logging.DEBUG) -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "manager.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


class LogCapture(logging.Handler):
    """Captures log records for support diagnostics or UI display."""

    def __init__(self, callback=None, max_records: int = 2000):
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.max_records = max_records
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records :]
        if self.callback:
            try:
                self.callback(record)
            except Exception:
                pass

    def get_text(self) -> str:
        fmt = logging.Formatter("%(asctime)s [%(levelname)-5s] %(message)s", datefmt="%H:%M:%S")
        return "\n".join(fmt.format(record) for record in self.records)
