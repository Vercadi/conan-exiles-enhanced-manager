"""Read-only v0.1 dashboard."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk

import customtkinter as ctk

from ...core.needs_attention import build_needs_attention


class DashboardTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._value_labels: dict[str, ctk.CTkLabel] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="#101010")
        body.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            body,
            text="Conan Exiles Enhanced Manager",
            font=self.app.ui_font("page_title"),
            text_color="#f1e7d0",
        )
        title.grid(row=0, column=0, sticky="w", padx=8, pady=(0, 2))

        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.grid(row=0, column=1, sticky="e", padx=8, pady=(0, 2))
        ctk.CTkButton(
            controls,
            text="Refresh",
            width=100,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#5d3424",
            hover_color="#70402c",
            command=self.app.refresh_discovery,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Backup Configs/Saves",
            width=170,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._manual_backup,
        ).grid(row=0, column=1)

        subtitle = ctk.CTkLabel(
            body,
            text="Local Conan, Workshop, server, hosted, and recovery status.",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
            justify="left",
        )
        subtitle.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 10))

        self._home_card = self._make_card(body, row=2, column=0, title="Home", columnspan=2)
        self._client_card = self._make_card(body, row=3, column=0, title="Client")
        self._server_card = self._make_card(body, row=3, column=1, title="Dedicated Server")
        self._steam_card = self._make_card(body, row=4, column=0, title="Steam Workshop")
        self._backup_card = self._make_card(body, row=4, column=1, title="Backups")
        self._attention_card = self._make_card(body, row=5, column=0, title="Needs Attention", columnspan=2)

        self._summary_label = ctk.CTkLabel(
            self._home_card,
            text="",
            font=self.app.ui_font("body"),
            text_color="#f1e7d0",
            justify="left",
            anchor="w",
            wraplength=self.app.ui_tokens.panel_wrap * 2,
        )
        self._summary_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))
        shortcuts = ctk.CTkFrame(self._home_card, fg_color="transparent")
        shortcuts.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        for col in range(6):
            shortcuts.grid_columnconfigure(col, weight=1)
        shortcut_specs = [
            ("Workshop", lambda: self.app.select_tab("Workshop")),
            ("Active Mods", lambda: self.app.select_tab("Active Mods")),
            ("Profiles", lambda: self.app.select_tab("Profiles")),
            ("Server", lambda: self.app.select_tab("Server")),
            ("Hosted", lambda: self.app.select_tab("Hosted")),
            ("Backup", self._manual_backup),
        ]
        for col, (label, command) in enumerate(shortcut_specs):
            ctk.CTkButton(
                shortcuts,
                text=label,
                height=self.app.ui_tokens.compact_button_height,
                font=self.app.ui_font("body"),
                fg_color="#3a3028" if label != "Backup" else "#7d4429",
                hover_color="#4a3c31" if label != "Backup" else "#925333",
                command=command,
            ).grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))

        for card, rows in [
            (
                self._client_card,
                [
                    ("client_status", "Status"),
                    ("client_build", "Steam Build"),
                    ("client_root", "Root"),
                    ("client_config", "Config"),
                    ("client_saves", "Save DBs"),
                    ("client_mods", "Mods Folder"),
                ],
            ),
            (
                self._server_card,
                [
                    ("server_status", "Status"),
                    ("server_runtime", "Runtime"),
                    ("server_restart", "Restart"),
                    ("server_build", "Steam Build"),
                    ("server_root", "Root"),
                    ("server_config", "Config"),
                    ("server_saves", "Save DBs"),
                    ("server_mods", "Mods Folder"),
                ],
            ),
            (
                self._steam_card,
                [
                    ("steam_libraries", "Steam Libraries"),
                    ("workshop_status", "Workshop Content"),
                    ("workshop_path", "Workshop Path"),
                ],
            ),
            (
                self._backup_card,
                [
                    ("backup_root", "Backup Root"),
                    ("backup_count", "Known Backups"),
                    ("last_result", "Last Result"),
                ],
            ),
        ]:
            self._build_rows(card, rows)

        self._attention_label = ctk.CTkLabel(
            self._attention_card,
            text="",
            font=self.app.ui_font("body"),
            text_color="#f1e7d0",
            justify="left",
            anchor="w",
            wraplength=self.app.ui_tokens.panel_wrap * 2,
        )
        self._attention_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))

        footer = ctk.CTkFrame(body, fg_color="transparent")
        footer.grid(row=6, column=0, columnspan=2, sticky="ew", padx=8, pady=(4, 0))
        footer.grid_columnconfigure(0, weight=1)
        self._status_label = ctk.CTkLabel(
            footer,
            text="",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        )
        self._status_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            footer,
            text="Copy Support Info",
            width=150,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self.app.copy_support_info,
        ).grid(row=0, column=1, sticky="e")

    def _make_card(self, body, *, row: int, column: int, title: str, columnspan: int = 1) -> ctk.CTkFrame:
        card = ctk.CTkFrame(body, fg_color="#191715", border_width=1, border_color="#3a3028")
        padx = 8 if columnspan > 1 else (8 if column == 0 else (4, 8))
        card.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=padx, pady=(0, 8))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text=title, font=self.app.ui_font("card_title"), text_color="#d3a15f").grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=12,
            pady=(10, 8),
        )
        return card

    def _build_rows(self, card: ctk.CTkFrame, rows: list[tuple[str, str]]) -> None:
        for index, (key, label) in enumerate(rows, start=1):
            ctk.CTkLabel(
                card,
                text=label,
                font=self.app.ui_font("body"),
                text_color="#b9aa92",
            ).grid(row=index, column=0, sticky="w", padx=12, pady=3)
            value = ctk.CTkLabel(
                card,
                text="",
                font=self.app.ui_font("body"),
                text_color="#f1e7d0",
                justify="right",
                anchor="e",
                wraplength=self.app.ui_tokens.panel_wrap,
            )
            value.grid(row=index, column=1, sticky="e", padx=12, pady=3)
            self._value_labels[key] = value

    def refresh(self) -> None:
        paths = self.app.paths
        enhanced = self.app.enhanced_status()
        self._summary_label.configure(
            text=(
                f"{enhanced.summary}\n"
                f"{len(self.app.active_mods)} active mod(s), "
                f"{len(self.app.hosted_profiles)} hosted profile(s), "
                f"{len(self.app.snapshot_records())} backup snapshot(s)."
            )
        )
        self._set("client_status", "Detected" if paths.client_root else "Missing", ok=bool(paths.client_root))
        self._set("client_build", _build_label(paths.client_manifest))
        self._set("client_root", _path_label(paths.client_root))
        self._set("client_config", _path_label(paths.client_config_dir))
        self._set("client_saves", f"{len(paths.client_save_databases())} database file(s)")
        self._set("client_mods", _folder_state(paths.client_mods_dir))

        self._set("server_status", "Detected" if paths.dedicated_server_root else "Missing", ok=bool(paths.dedicated_server_root))
        server_status = self.app.dedicated_server_status()
        self._set("server_runtime", server_status.summary, ok=server_status.running)
        restart = self.app.server_runtime
        self._set(
            "server_restart",
            f"Recommended: {restart.restart_reason}" if restart.restart_recommended else "No pending restart note",
            ok=not restart.restart_recommended,
        )
        self._set("server_build", _build_label(paths.dedicated_server_manifest))
        self._set("server_root", _path_label(paths.dedicated_server_root))
        self._set("server_config", _path_label(paths.dedicated_server_config_dir))
        self._set("server_saves", f"{len(paths.dedicated_server_save_databases())} database file(s)")
        self._set("server_mods", _folder_state(paths.dedicated_server_mods_dir))

        self._set("steam_libraries", str(len(paths.steamapps_dirs)))
        workshop_exists = bool(paths.workshop_content_dir and paths.workshop_content_dir.is_dir())
        self._set("workshop_status", "Detected" if workshop_exists else "Not created/downloaded yet", ok=workshop_exists)
        self._set("workshop_path", _path_label(paths.workshop_content_dir))

        self._set("backup_root", _path_label(paths.backup_dir))
        self._set("backup_count", str(len(self.app.backup.list_backups())))
        self._set("last_result", self.app.last_action or "No backup run this session")

        attention = build_needs_attention(
            paths,
            server_runtime=self.app.server_runtime,
            active_mods=self.app.active_mods,
            workshop_items=self.app.workshop_items,
            enhanced_status=enhanced,
        )
        self._attention_label.configure(text="\n".join(f"- {item}" for item in attention) if attention else "No immediate issues found.")
        self._status_label.configure(text=self.app.status_text)

    def _set(self, key: str, value: str, *, ok: bool | None = None) -> None:
        label = self._value_labels.get(key)
        if not label:
            return
        color = "#f1e7d0"
        if ok is True:
            color = "#74ad7f"
        elif ok is False:
            color = "#c98a2e"
        label.configure(text=value, text_color=color)

    def _manual_backup(self) -> None:
        records = self.app.backup_configs_and_saves()
        if records:
            self.app.notify_info("Backup Complete", f"Backed up {len(records)} config/save file(s).")
        else:
            self.app.notify_warning("Backup Complete", "No config or save database files were found to back up.")
        self.refresh()


def _build_label(manifest) -> str:
    if not manifest:
        return "Unknown"
    return manifest.buildid or "Unknown"


def _path_label(path: Path | None) -> str:
    if not path:
        return "Not configured"
    return str(path)


def _folder_state(path: Path | None) -> str:
    if not path:
        return "Not configured"
    return "Exists" if path.is_dir() else "Not created yet"
