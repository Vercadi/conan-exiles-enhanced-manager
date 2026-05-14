"""Dedicated Server operations tab."""
from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ...core.server_config_editor import ServerConfigEdit

BOOLEAN_CHOICES = ("Unchanged", "True", "False")


class ServerTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._value_labels: dict[str, ctk.CTkLabel] = {}
        self._launch_args_var = ctk.StringVar(value=self.app.preferences.dedicated_server_launch_args)
        self._server_name_var = ctk.StringVar()
        self._max_players_var = ctk.StringVar()
        self._game_port_var = ctk.StringVar()
        self._query_port_var = ctk.StringVar()
        self._rcon_port_var = ctk.StringVar()
        self._pvp_var = ctk.StringVar(value="Unchanged")
        self._battleye_var = ctk.StringVar(value="Unchanged")
        self._rcon_enabled_var = ctk.StringVar(value="Unchanged")
        self._server_password_var = ctk.StringVar()
        self._admin_password_var = ctk.StringVar()
        self._rcon_password_var = ctk.StringVar()
        self._clear_server_password_var = ctk.BooleanVar(value=False)
        self._clear_admin_password_var = ctk.BooleanVar(value=False)
        self._clear_rcon_password_var = ctk.BooleanVar(value=False)
        self._motd_var = ctk.StringVar()
        self._mirror_modlist_var = ctk.BooleanVar(value=False)
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="#101010")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Dedicated Server",
            font=self.app.ui_font("page_title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w")
        self._status_label = ctk.CTkLabel(
            header,
            text="",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        )
        self._status_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="#101010")
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self._status_card = self._make_card(body, row=0, column=0, title="Status")
        self._paths_card = self._make_card(body, row=0, column=1, title="Paths")
        self._config_card = self._make_card(body, row=1, column=0, title="Server Config")
        self._launch_card = self._make_card(body, row=1, column=1, title="Launch")
        self._edit_card = self._make_card(body, row=2, column=0, title="Edit Config", columnspan=2)
        self._logs_card = self._make_card(body, row=3, column=0, title="Logs", columnspan=2)

        self._build_rows(
            self._status_card,
            [
                ("runtime", "Runtime"),
                ("restart", "Restart"),
                ("build", "Steam Build"),
            ],
        )
        self._build_rows(
            self._paths_card,
            [
                ("root", "Root"),
                ("config", "Config"),
                ("saves", "Saves"),
                ("logs", "Logs"),
            ],
        )
        self._build_rows(
            self._config_card,
            [
                ("server_name", "Server Name"),
                ("ports", "Ports"),
                ("password", "Server Password"),
                ("admin", "Admin Password"),
                ("max_players", "Max Players"),
                ("pvp", "PVP"),
                ("battleye", "BattlEye"),
                ("server_mod_list", "ServerModList"),
            ],
        )

        ctk.CTkLabel(
            self._launch_card,
            text="Launch Args",
            font=self.app.ui_font("body"),
            text_color="#b9aa92",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self._launch_args_entry = ctk.CTkEntry(
            self._launch_card,
            textvariable=self._launch_args_var,
            font=self.app.ui_font("body"),
            fg_color="#101010",
            border_color="#3a3028",
            text_color="#f1e7d0",
        )
        self._launch_args_entry.grid(row=1, column=1, sticky="ew", padx=12, pady=4)
        ctk.CTkButton(
            self._launch_card,
            text="Save Args",
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=lambda: self.app.update_dedicated_server_launch_args(self._launch_args_var.get()),
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 10))
        ctk.CTkButton(
            self._launch_card,
            text="Start Server",
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self.app.launch_dedicated_server_from_ui,
        ).grid(row=2, column=1, sticky="ew", padx=12, pady=(6, 10))

        self._build_config_editor()

        controls = ctk.CTkFrame(self._logs_card, fg_color="transparent")
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))
        controls.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            controls,
            text="Refresh Status",
            width=130,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self.refresh,
        ).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            controls,
            text="Open Server Folder",
            width=160,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=lambda: self.app.open_path(self.app.paths.dedicated_server_root),
        ).grid(row=0, column=2, padx=(8, 0))
        ctk.CTkButton(
            controls,
            text="Open Logs Folder",
            width=150,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=lambda: self.app.open_path(self.app.paths.dedicated_server_log_dir),
        ).grid(row=0, column=3, padx=(8, 0))

        self._log_text = ctk.CTkTextbox(
            self._logs_card,
            height=300,
            font=self.app.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        self._log_text.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0, 12))

    def _build_config_editor(self) -> None:
        self._edit_card.grid_columnconfigure(1, weight=1)
        self._edit_card.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(
            self._edit_card,
            text=(
                "Stage dedicated server config changes here. Password fields are unchanged when left blank; "
                "use the clear checkbox to intentionally blank one."
            ),
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap * 2,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 8))
        self._entry(self._edit_card, "Server Name", self._server_name_var, row=2, column=0)
        self._entry(self._edit_card, "Max Players", self._max_players_var, row=2, column=2, width=110)
        self._entry(self._edit_card, "Game Port", self._game_port_var, row=3, column=0, width=110)
        self._entry(self._edit_card, "Query Port", self._query_port_var, row=3, column=2, width=110)
        self._entry(self._edit_card, "RCON Port", self._rcon_port_var, row=4, column=0, width=110)
        self._option(self._edit_card, "PVP", self._pvp_var, row=4, column=2)
        self._option(self._edit_card, "BattlEye", self._battleye_var, row=5, column=0)
        self._option(self._edit_card, "RCON Enabled", self._rcon_enabled_var, row=5, column=2)
        self._secret(self._edit_card, "Server Password", self._server_password_var, self._clear_server_password_var, row=6)
        self._secret(self._edit_card, "Admin Password", self._admin_password_var, self._clear_admin_password_var, row=7)
        self._secret(self._edit_card, "RCON Password", self._rcon_password_var, self._clear_rcon_password_var, row=8)
        self._entry(self._edit_card, "MOTD", self._motd_var, row=9, column=0)
        ctk.CTkSwitch(
            self._edit_card,
            text="Mirror ServerModList from Active Mods",
            variable=self._mirror_modlist_var,
            onvalue=True,
            offvalue=False,
            font=self.app.ui_font("body"),
            text_color="#f1e7d0",
            progress_color="#7d4429",
        ).grid(row=9, column=2, columnspan=2, sticky="w", padx=12, pady=4)

        actions = ctk.CTkFrame(self._edit_card, fg_color="transparent")
        actions.grid(row=10, column=0, columnspan=4, sticky="ew", padx=12, pady=(8, 12))
        actions.grid_columnconfigure(0, weight=1)
        self._edit_status_label = ctk.CTkLabel(
            actions,
            text="",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        )
        self._edit_status_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            actions,
            text="Reset Fields",
            width=120,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._populate_editor_fields,
        ).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            actions,
            text="Preview Config Changes",
            width=180,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._preview_config_changes,
        ).grid(row=0, column=2, padx=(8, 0))

    def _entry(self, parent, label: str, variable, *, row: int, column: int, width: int | None = None) -> None:
        ctk.CTkLabel(parent, text=label, font=self.app.ui_font("body"), text_color="#b9aa92").grid(
            row=row,
            column=column,
            sticky="w",
            padx=12,
            pady=4,
        )
        ctk.CTkEntry(
            parent,
            textvariable=variable,
            width=width or 260,
            font=self.app.ui_font("body"),
            fg_color="#101010",
            border_color="#3a3028",
            text_color="#f1e7d0",
        ).grid(row=row, column=column + 1, sticky="ew", padx=12, pady=4)

    def _option(self, parent, label: str, variable, *, row: int, column: int) -> None:
        ctk.CTkLabel(parent, text=label, font=self.app.ui_font("body"), text_color="#b9aa92").grid(
            row=row,
            column=column,
            sticky="w",
            padx=12,
            pady=4,
        )
        ctk.CTkOptionMenu(
            parent,
            variable=variable,
            values=list(BOOLEAN_CHOICES),
            width=150,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
        ).grid(row=row, column=column + 1, sticky="w", padx=12, pady=4)

    def _secret(self, parent, label: str, variable, clear_var, *, row: int) -> None:
        ctk.CTkLabel(parent, text=label, font=self.app.ui_font("body"), text_color="#b9aa92").grid(
            row=row,
            column=0,
            sticky="w",
            padx=12,
            pady=4,
        )
        ctk.CTkEntry(
            parent,
            textvariable=variable,
            show="*",
            font=self.app.ui_font("body"),
            fg_color="#101010",
            border_color="#3a3028",
            text_color="#f1e7d0",
        ).grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        ctk.CTkCheckBox(
            parent,
            text="Clear",
            variable=clear_var,
            onvalue=True,
            offvalue=False,
            font=self.app.ui_font("body"),
            text_color="#f1e7d0",
            fg_color="#7d4429",
            hover_color="#925333",
        ).grid(row=row, column=2, sticky="w", padx=12, pady=4)

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
            ctk.CTkLabel(card, text=label, font=self.app.ui_font("body"), text_color="#b9aa92").grid(
                row=index,
                column=0,
                sticky="w",
                padx=12,
                pady=3,
            )
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
        if not self.app.dedicated_server_features_enabled():
            disabled = "Disabled in Settings"
            for key in self._value_labels:
                self._set(key, disabled, ok=True)
            self._status_label.configure(
                text="Dedicated-server features are disabled. Enable them in Settings and set a server path to use this tab."
            )
            self._launch_args_var.set(self.app.preferences.dedicated_server_launch_args)
            self._log_text.configure(state="normal")
            self._log_text.delete("1.0", "end")
            self._log_text.insert(
                "1.0",
                "Dedicated-server log/config checks are off. This is normal for client-only setups.",
            )
            self._log_text.configure(state="disabled")
            return
        status = self.app.dedicated_server_status()
        config = self.app.dedicated_server_config()
        logs = self.app.dedicated_server_log_snapshot()
        paths = self.app.paths

        self._set("runtime", status.summary, ok=status.running)
        restart_text = (
            f"Recommended: {self.app.server_runtime.restart_reason}"
            if self.app.server_runtime.restart_recommended
            else "No pending restart note"
        )
        self._set("restart", restart_text, ok=not self.app.server_runtime.restart_recommended)
        self._set("build", paths.dedicated_server_manifest.buildid if paths.dedicated_server_manifest else "Unknown")
        self._set("root", _path_label(paths.dedicated_server_root))
        self._set("config", _path_label(paths.dedicated_server_config_dir))
        self._set("saves", _path_label(paths.dedicated_server_save_root))
        self._set("logs", _path_label(paths.dedicated_server_log_dir))
        self._set("server_name", config.server_name or "Not set")
        self._set("ports", config.port_summary)
        self._set("password", "Set" if config.server_password_set else "Not set")
        self._set("admin", "Set" if config.admin_password_set else "Not set")
        self._set("max_players", config.max_players or "Not set")
        self._set("pvp", config.pvp_enabled or "Not set")
        self._set("battleye", config.battleye_enabled or "Not set")
        self._set("server_mod_list", "Set" if config.server_mod_list else "Empty")
        self._status_label.configure(text=f"{status.summary} | {restart_text}")
        self._launch_args_var.set(self.app.preferences.dedicated_server_launch_args)
        self._populate_editor_fields(config=config)

        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        if logs.log_path:
            filtered = logs.filtered or "(no mod/error/warning lines in current tail)"
            self._log_text.insert("1.0", f"Latest log: {logs.log_path}\n\nFiltered lines:\n{filtered}\n\nTail:\n{logs.tail}")
        else:
            self._log_text.insert("1.0", "No dedicated server log file found.")
        self._log_text.configure(state="disabled")

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

    def _populate_editor_fields(self, *, config=None) -> None:
        config = config or self.app.dedicated_server_config()
        self._server_name_var.set(config.server_name or "")
        self._max_players_var.set(config.max_players or "")
        self._game_port_var.set(config.game_port or "")
        self._query_port_var.set(config.query_port or "")
        self._rcon_port_var.set(config.rcon_port or "")
        self._pvp_var.set("Unchanged")
        self._battleye_var.set("Unchanged")
        self._rcon_enabled_var.set("Unchanged")
        self._server_password_var.set("")
        self._admin_password_var.set("")
        self._rcon_password_var.set("")
        self._clear_server_password_var.set(False)
        self._clear_admin_password_var.set(False)
        self._clear_rcon_password_var.set(False)
        self._motd_var.set("")
        self._mirror_modlist_var.set(False)
        self._edit_status_label.configure(
            text="Password boxes are blank because saved password values are not shown."
        )

    def _preview_config_changes(self) -> None:
        self.app.preview_server_config_edit(self._config_edit())

    def _config_edit(self) -> ServerConfigEdit:
        config = self.app.dedicated_server_config()
        return ServerConfigEdit(
            server_name=_changed_value(self._server_name_var.get(), config.server_name),
            server_password=_secret_value(self._server_password_var.get()),
            clear_server_password=bool(self._clear_server_password_var.get()),
            admin_password=_secret_value(self._admin_password_var.get()),
            clear_admin_password=bool(self._clear_admin_password_var.get()),
            max_players=_changed_value(self._max_players_var.get(), config.max_players),
            pvp_enabled=_boolean_choice(self._pvp_var.get()),
            battleye_enabled=_boolean_choice(self._battleye_var.get()),
            game_port=_changed_value(self._game_port_var.get(), config.game_port),
            query_port=_changed_value(self._query_port_var.get(), config.query_port),
            rcon_enabled=_boolean_choice(self._rcon_enabled_var.get()),
            rcon_password=_secret_value(self._rcon_password_var.get()),
            clear_rcon_password=bool(self._clear_rcon_password_var.get()),
            rcon_port=_changed_value(self._rcon_port_var.get(), config.rcon_port),
            motd=_optional_value(self._motd_var.get()),
            server_mod_list=self._server_mod_list_value(),
            mirror_server_mod_list=bool(self._mirror_modlist_var.get()),
        )

    def _server_mod_list_value(self) -> str:
        values = [
            entry.workshop_id or entry.normalized_value
            for entry in self.app.active_mods
            if entry.workshop_id or entry.normalized_value
        ]
        return ",".join(values)


def _path_label(path: Path | None) -> str:
    return str(path) if path else "Not configured"


def _optional_value(value: str) -> str | None:
    stripped = str(value or "").strip()
    return stripped if stripped else None


def _secret_value(value: str) -> str | None:
    return _optional_value(value)


def _changed_value(value: str, current: str) -> str | None:
    stripped = str(value or "").strip()
    return stripped if stripped != str(current or "").strip() else None


def _boolean_choice(value: str) -> str | None:
    return value if value in {"True", "False"} else None
