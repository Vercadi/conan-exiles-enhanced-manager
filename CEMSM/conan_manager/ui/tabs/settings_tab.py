"""Application settings."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ...models.app_preferences import AppPreferences


UI_SIZE_LABELS = {
    "Compact": "compact",
    "Default": "default",
    "Large": "large",
}

CONFIRMATION_LABELS = {
    "Always Confirm": "always",
    "Destructive Actions Only": "destructive_only",
    "Reduced Confirmations": "reduced",
    "No Confirmation Popups": "none",
}


class SettingsTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._ui_size_var = ctk.StringVar(value=_label_for_value(UI_SIZE_LABELS, app.preferences.ui_size, "Default"))
        self._confirmation_var = ctk.StringVar(
            value=_label_for_value(CONFIRMATION_LABELS, app.preferences.confirmation_mode, "Destructive Actions Only")
        )
        self._result_popups_var = tk.BooleanVar(value=app.preferences.show_result_popups)
        self._auto_updates_var = tk.BooleanVar(value=app.preferences.auto_check_updates)
        self._steamcmd_path_var = ctk.StringVar(value=app.preferences.steamcmd_path)
        self._steamcmd_username_var = ctk.StringVar(value=app.preferences.steamcmd_username)
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="#101010")
        body.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body,
            text="Settings",
            font=self.app.ui_font("page_title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(0, 2))

        ctk.CTkLabel(
            body,
            text="App behavior, update checks, and local support storage.",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 10))

        behavior = self._card(body, 2, "Behavior")
        behavior.grid_columnconfigure(1, weight=1)
        self._option_row(
            behavior,
            1,
            "UI Size",
            self._ui_size_var,
            list(UI_SIZE_LABELS.keys()),
        )
        self._option_row(
            behavior,
            2,
            "Confirmations",
            self._confirmation_var,
            list(CONFIRMATION_LABELS.keys()),
        )
        self._switch_row(
            behavior,
            3,
            "Show result popups",
            self._result_popups_var,
            "When off, routine successes and warnings stay in the top banner instead of opening dialogs.",
        )
        self._switch_row(
            behavior,
            4,
            "Auto-check updates",
            self._auto_updates_var,
            "Checks GitHub Releases on startup. Manual checks are always available in Help.",
        )

        ctk.CTkLabel(
            behavior,
            text=(
                "Write, restore, and hosted upload workflows still use preview windows before they touch files. "
                "This setting only controls interruption level around routine prompts."
            ),
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 12))

        steamcmd = self._card(body, 3, "SteamCMD")
        steamcmd.grid_columnconfigure(1, weight=1)
        self._entry_row(
            steamcmd,
            1,
            "steamcmd.exe",
            self._steamcmd_path_var,
            browse_command=self._browse_steamcmd,
        )
        self._entry_row(steamcmd, 2, "Steam username", self._steamcmd_username_var)
        ctk.CTkLabel(
            steamcmd,
            text=(
                "Workshop downloads use anonymous login first. A username is optional for cases where SteamCMD "
                "requires an account; passwords are never saved by this app."
            ),
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(8, 12))

        storage = self._card(body, 4, "Storage")
        self._value_row(storage, 1, "Data", str(self.app.paths.data_dir or "Not configured"))
        self._value_row(storage, 2, "Backups", str(self.app.paths.backup_dir or "Not configured"))
        storage_actions = ctk.CTkFrame(storage, fg_color="transparent")
        storage_actions.grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 12))
        self._button(storage_actions, "Open Data Folder", lambda: self.app.open_path(self.app.paths.data_dir), column=0)
        self._button(
            storage_actions,
            "Open Backup Folder",
            lambda: self.app.open_path(self.app.paths.backup_dir),
            column=1,
        )

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", padx=8, pady=(4, 0))
        actions.grid_columnconfigure(0, weight=1)
        self._result_label = ctk.CTkLabel(
            actions,
            text="",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        )
        self._result_label.grid(row=0, column=0, sticky="ew")
        self._save_button = ctk.CTkButton(
            actions,
            text="Save Settings",
            width=140,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._save,
        )
        self._save_button.grid(row=0, column=1, sticky="e")

    def _card(self, parent, row: int, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color="#191715", border_width=1, border_color="#3a3028")
        card.grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 8))
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

    def _option_row(self, card, row: int, label: str, variable, values: list[str]) -> None:
        ctk.CTkLabel(card, text=label, font=self.app.ui_font("body"), text_color="#b9aa92").grid(
            row=row,
            column=0,
            sticky="w",
            padx=12,
            pady=4,
        )
        ctk.CTkOptionMenu(
            card,
            variable=variable,
            values=values,
            width=220,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
        ).grid(row=row, column=1, sticky="w", padx=12, pady=4)

    def _switch_row(self, card, row: int, label: str, variable, hint: str) -> None:
        ctk.CTkSwitch(
            card,
            text=label,
            variable=variable,
            onvalue=True,
            offvalue=False,
            font=self.app.ui_font("body"),
            text_color="#f1e7d0",
            progress_color="#7d4429",
        ).grid(row=row, column=0, sticky="w", padx=12, pady=6)
        ctk.CTkLabel(
            card,
            text=hint,
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap,
            justify="left",
            anchor="w",
        ).grid(row=row, column=1, sticky="ew", padx=12, pady=6)

    def _entry_row(self, card, row: int, label: str, variable, *, browse_command=None) -> None:
        ctk.CTkLabel(card, text=label, font=self.app.ui_font("body"), text_color="#b9aa92").grid(
            row=row,
            column=0,
            sticky="w",
            padx=12,
            pady=4,
        )
        ctk.CTkEntry(
            card,
            textvariable=variable,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#101010",
            border_color="#3a3028",
            text_color="#f1e7d0",
        ).grid(row=row, column=1, sticky="ew", padx=12, pady=4)
        if browse_command:
            ctk.CTkButton(
                card,
                text="Browse",
                width=90,
                height=self.app.ui_tokens.compact_button_height,
                font=self.app.ui_font("body"),
                fg_color="#3a3028",
                hover_color="#4a3c31",
                command=browse_command,
            ).grid(row=row, column=2, sticky="e", padx=(0, 12), pady=4)

    def _value_row(self, card, row: int, label: str, value: str) -> None:
        ctk.CTkLabel(card, text=label, font=self.app.ui_font("body"), text_color="#b9aa92").grid(
            row=row,
            column=0,
            sticky="w",
            padx=12,
            pady=4,
        )
        ctk.CTkLabel(
            card,
            text=value,
            font=self.app.ui_font("body"),
            text_color="#f1e7d0",
            wraplength=self.app.ui_tokens.panel_wrap,
            justify="right",
            anchor="e",
        ).grid(row=row, column=1, sticky="e", padx=12, pady=4)

    def _button(self, parent, text: str, command, *, column: int) -> None:
        ctk.CTkButton(
            parent,
            text=text,
            width=150,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=command,
        ).grid(row=0, column=column, padx=(0 if column == 0 else 8, 0))

    def refresh(self) -> None:
        preferences = self.app.preferences.normalized()
        self._ui_size_var.set(_label_for_value(UI_SIZE_LABELS, preferences.ui_size, "Default"))
        self._confirmation_var.set(
            _label_for_value(CONFIRMATION_LABELS, preferences.confirmation_mode, "Destructive Actions Only")
        )
        self._result_popups_var.set(preferences.show_result_popups)
        self._auto_updates_var.set(preferences.auto_check_updates)
        self._steamcmd_path_var.set(preferences.steamcmd_path)
        self._steamcmd_username_var.set(preferences.steamcmd_username)
        if hasattr(self, "_result_label"):
            self._result_label.configure(text="Current settings are loaded.")

    def _browse_steamcmd(self) -> None:
        path = filedialog.askopenfilename(
            title="Select steamcmd.exe",
            filetypes=[("SteamCMD", "steamcmd.exe"), ("Executables", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self._steamcmd_path_var.set(path)

    def _save(self) -> None:
        preferences = AppPreferences(
            ui_size=UI_SIZE_LABELS.get(self._ui_size_var.get(), "default"),
            dedicated_server_launch_args=self.app.preferences.dedicated_server_launch_args,
            confirmation_mode=CONFIRMATION_LABELS.get(self._confirmation_var.get(), "destructive_only"),
            show_result_popups=bool(self._result_popups_var.get()),
            auto_check_updates=bool(self._auto_updates_var.get()),
            steamcmd_path=self._steamcmd_path_var.get(),
            steamcmd_username=self._steamcmd_username_var.get(),
        ).normalized()
        self.app.update_preferences(preferences)
        self._result_label.configure(text="Saved. Restart to fully refresh any already-open tab sizing.")
        self.app.notify_info("Settings Saved", "Settings saved.")


def _label_for_value(mapping: dict[str, str], value: str, fallback: str) -> str:
    for label, mapped in mapping.items():
        if mapped == value:
            return label
    return fallback
