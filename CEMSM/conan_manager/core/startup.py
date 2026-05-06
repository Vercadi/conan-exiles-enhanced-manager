"""Small startup sequencing helpers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StartupStep:
    key: str
    message: str


STARTUP_STEPS = (
    StartupStep("shell", "Opening Conan Exiles Enhanced Manager..."),
    StartupStep("settings", "Loading local settings..."),
    StartupStep("dashboard", "Rendering dashboard..."),
    StartupStep("discovery", "Discovering Steam and Conan paths..."),
    StartupStep("ready", "Ready."),
)


def startup_message(key: str) -> str:
    for step in STARTUP_STEPS:
        if step.key == key:
            return step.message
    return str(key or "Starting...")
