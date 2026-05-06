from __future__ import annotations

from dataclasses import dataclass

UI_SIZE_VALUES = ("compact", "default", "large")
CONFIRMATION_MODE_VALUES = ("always", "destructive_only", "reduced", "none")


@dataclass
class AppPreferences:
    """User-facing app preferences."""

    ui_size: str = "default"
    dedicated_server_launch_args: str = "-Messaging"
    confirmation_mode: str = "destructive_only"
    show_result_popups: bool = True
    auto_check_updates: bool = False
    steamcmd_path: str = ""
    steamcmd_username: str = ""

    def normalized(self) -> "AppPreferences":
        confirmation_mode = (
            self.confirmation_mode
            if self.confirmation_mode in CONFIRMATION_MODE_VALUES
            else "destructive_only"
        )
        return AppPreferences(
            ui_size=self.ui_size if self.ui_size in UI_SIZE_VALUES else "default",
            dedicated_server_launch_args=str(self.dedicated_server_launch_args or "-Messaging").strip() or "-Messaging",
            confirmation_mode=confirmation_mode,
            show_result_popups=bool(self.show_result_popups),
            auto_check_updates=bool(self.auto_check_updates),
            steamcmd_path=str(self.steamcmd_path or "").strip(),
            steamcmd_username=str(self.steamcmd_username or "").strip(),
        )

    def to_dict(self) -> dict:
        normalized = self.normalized()
        return {
            "ui_size": normalized.ui_size,
            "dedicated_server_launch_args": normalized.dedicated_server_launch_args,
            "confirmation_mode": normalized.confirmation_mode,
            "show_result_popups": normalized.show_result_popups,
            "auto_check_updates": normalized.auto_check_updates,
            "steamcmd_path": normalized.steamcmd_path,
            "steamcmd_username": normalized.steamcmd_username,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "AppPreferences":
        if not isinstance(data, dict):
            return cls()
        return cls(
            ui_size=str(data.get("ui_size") or "default"),
            dedicated_server_launch_args=str(data.get("dedicated_server_launch_args") or "-Messaging"),
            confirmation_mode=str(data.get("confirmation_mode") or "destructive_only"),
            show_result_popups=bool(data.get("show_result_popups", True)),
            auto_check_updates=bool(data.get("auto_check_updates", False)),
            steamcmd_path=str(data.get("steamcmd_path") or ""),
            steamcmd_username=str(data.get("steamcmd_username") or ""),
        ).normalized()
