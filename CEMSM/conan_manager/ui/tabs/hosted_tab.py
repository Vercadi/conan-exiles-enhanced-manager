"""Hosted server file-access workflow."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ...models.hosted import HOSTED_PROTOCOLS, PROTOCOL_SFTP, HostedProfile, default_port


class HostedTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._profile_var = ctk.StringVar(value="")
        self._protocol_var = ctk.StringVar(value=PROTOCOL_SFTP.upper())
        self._name_var = ctk.StringVar(value="Default Hosted")
        self._host_var = ctk.StringVar(value="")
        self._port_var = ctk.StringVar(value="22")
        self._username_var = ctk.StringVar(value="")
        self._password_var = ctk.StringVar(value="")
        self._key_var = ctk.StringVar(value="")
        self._server_folder_var = ctk.StringVar(value=".")
        self._mods_folder_var = ctk.StringVar(value="")
        self._config_folder_var = ctk.StringVar(value="")
        self._config_file_var = ctk.StringVar(value="")
        self._save_folder_var = ctk.StringVar(value="")
        self._log_folder_var = ctk.StringVar(value="")
        self._upload_paks_var = ctk.BooleanVar(value=True)
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
            text="Hosted Servers",
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

        connection = self._card(body, row=0, column=0, title="Connection")
        paths = self._card(body, row=0, column=1, title="Conan Paths")
        actions = self._card(body, row=1, column=0, title="Actions", columnspan=2)
        inventory = self._card(body, row=2, column=0, title="Hosted Inventory", columnspan=2)

        self._profile_menu = ctk.CTkOptionMenu(
            connection,
            variable=self._profile_var,
            values=["New Profile"],
            width=180,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
            command=lambda _value: self._load_selected_profile(),
        )
        self._profile_menu.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=4)
        self._entry(connection, "name", "Profile Name", self._name_var, row=2)
        self._option(connection, "Protocol", self._protocol_var, [item.upper() for item in HOSTED_PROTOCOLS], row=3)
        self._entry(connection, "host", "Host / IP", self._host_var, row=4)
        self._entry(connection, "port", "FTP/SFTP Port", self._port_var, row=5)
        self._entry(connection, "username", "Username", self._username_var, row=6)
        self._entry(connection, "password", "Password", self._password_var, row=7, show="*")
        self._entry(connection, "key", "Private Key Path", self._key_var, row=8)
        ctk.CTkButton(
            connection,
            text="Browse Key",
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._browse_key,
        ).grid(row=9, column=1, sticky="ew", padx=12, pady=(4, 10))

        self._entry(paths, "server", "Server Folder", self._server_folder_var, row=1)
        self._entry(paths, "mods", "Mods Folder Override", self._mods_folder_var, row=2)
        self._entry(paths, "config", "Server Config Folder", self._config_folder_var, row=3)
        self._entry(paths, "config_file", "ServerSettings.ini Override", self._config_file_var, row=4)
        self._entry(paths, "save", "Save Folder Override", self._save_folder_var, row=5)
        self._entry(paths, "logs", "Log Folder Override", self._log_folder_var, row=6)
        ctk.CTkLabel(
            paths,
            text="FTP/SFTP ports are for file access. They are not Conan game, query, or RCON ports.",
            font=self.app.ui_font("small"),
            text_color="#c98a2e",
            wraplength=self.app.ui_tokens.panel_wrap,
            justify="left",
        ).grid(row=7, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 10))

        actions.grid_columnconfigure(0, weight=1)
        buttons = ctk.CTkFrame(actions, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 10))
        for col in range(7):
            buttons.grid_columnconfigure(col, weight=1)
        self._action(buttons, "Save Profile", self._save_profile, 0)
        self._action(buttons, "Test Connection", self._test_connection, 1)
        self._action(buttons, "Auto-detect Paths", self._autodetect_paths, 2)
        self._action(buttons, "Scan Inventory", self._scan_inventory, 3)
        self._action(buttons, "Preview Upload", self._preview_upload, 4, primary=True)
        self._action(buttons, "Backup Configs", self._backup_configs, 5)
        self._action(buttons, "Copy Panel Fallback", self._copy_fallback, 6)
        ctk.CTkCheckBox(
            actions,
            text="Upload local .pak files with modlist",
            variable=self._upload_paks_var,
            font=self.app.ui_font("body"),
            text_color="#f1e7d0",
            fg_color="#7d4429",
            hover_color="#925333",
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))

        self._output = ctk.CTkTextbox(
            inventory,
            height=300,
            font=self.app.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        self._output.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=(4, 12))

    def _card(self, parent, *, row: int, column: int, title: str, columnspan: int = 1) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color="#191715", border_width=1, border_color="#3a3028")
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

    def _entry(self, parent, _key: str, label: str, variable: ctk.StringVar, *, row: int, show: str = "") -> None:
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
            show=show,
            font=self.app.ui_font("body"),
            fg_color="#101010",
            border_color="#3a3028",
            text_color="#f1e7d0",
        ).grid(row=row, column=1, sticky="ew", padx=12, pady=4)

    def _option(self, parent, label: str, variable: ctk.StringVar, values: list[str], *, row: int) -> None:
        ctk.CTkLabel(parent, text=label, font=self.app.ui_font("body"), text_color="#b9aa92").grid(
            row=row,
            column=0,
            sticky="w",
            padx=12,
            pady=4,
        )
        ctk.CTkOptionMenu(
            parent,
            variable=variable,
            values=values,
            width=120,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
            command=lambda value: self._protocol_changed(value),
        ).grid(row=row, column=1, sticky="ew", padx=12, pady=4)

    def _action(self, parent, text: str, command, column: int, *, primary: bool = False) -> None:
        ctk.CTkButton(
            parent,
            text=text,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429" if primary else "#3a3028",
            hover_color="#925333" if primary else "#4a3c31",
            command=command,
        ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))

    def refresh(self) -> None:
        names = [profile.name for profile in self.app.hosted_profiles]
        values = names or ["New Profile"]
        self._profile_menu.configure(values=values)
        if self._profile_var.get() not in values:
            self._profile_var.set(values[0])
            self._load_selected_profile()
        self._status_label.configure(
            text=f"{len(self.app.hosted_profiles)} hosted profile(s). Passwords are used for this session only."
        )
        if not self._output.get("1.0", "end").strip():
            self._write_output("Hosted file-access workflow is ready. Save a profile, test connection, then auto-detect paths.")

    def _profile(self) -> HostedProfile:
        protocol = self._protocol_var.get().casefold()
        try:
            port = int(self._port_var.get().strip() or default_port(protocol))
        except ValueError:
            port = default_port(protocol)
        key_text = self._key_var.get().strip()
        return HostedProfile(
            name=self._name_var.get(),
            protocol=protocol,
            host=self._host_var.get(),
            port=port,
            username=self._username_var.get(),
            password=self._password_var.get(),
            private_key_path=Path(key_text) if key_text else None,
            server_folder=self._server_folder_var.get(),
            mods_folder_override=self._mods_folder_var.get(),
            config_folder_override=self._config_folder_var.get(),
            config_file_override=self._config_file_var.get(),
            save_folder_override=self._save_folder_var.get(),
            log_folder_override=self._log_folder_var.get(),
        ).normalized()

    def _load_selected_profile(self) -> None:
        profile = self.app.hosted_profile_named(self._profile_var.get())
        if not profile:
            return
        self._name_var.set(profile.name)
        self._protocol_var.set(profile.protocol.upper())
        self._host_var.set(profile.host)
        self._port_var.set(str(profile.port))
        self._username_var.set(profile.username)
        self._password_var.set("")
        self._key_var.set(str(profile.private_key_path) if profile.private_key_path else "")
        self._server_folder_var.set(profile.server_folder)
        self._mods_folder_var.set(profile.mods_folder_override)
        self._config_folder_var.set(profile.config_folder_override)
        self._config_file_var.set(profile.config_file_override)
        self._save_folder_var.set(profile.save_folder_override)
        self._log_folder_var.set(profile.log_folder_override)

    def _protocol_changed(self, value: str) -> None:
        current_port = self._port_var.get().strip()
        if current_port in ("", "21", "22"):
            self._port_var.set(str(default_port(value.casefold())))

    def _browse_key(self) -> None:
        path = filedialog.askopenfilename(title="Select private key file", filetypes=[("All files", "*.*")])
        if path:
            self._key_var.set(path)

    def _save_profile(self) -> None:
        profile = self.app.save_hosted_profile(self._profile())
        self._profile_var.set(profile.name)
        self.refresh()
        self.app.notify_info("Hosted Profile Saved", f"Saved profile {profile.name}. Password was not stored.")

    def _test_connection(self) -> None:
        message = self.app.test_hosted_connection(self._profile())
        self._write_output(message)
        if "failed" in message.casefold():
            self.app.notify_warning("Hosted Connection", message)
        else:
            self.app.notify_info("Hosted Connection", message)

    def _autodetect_paths(self) -> None:
        detection = self.app.autodetect_hosted_paths(self._profile())
        if detection.mods_dir:
            self._mods_folder_var.set(detection.mods_dir)
        if detection.config_dir:
            self._config_folder_var.set(detection.config_dir)
        if detection.config_file:
            self._config_file_var.set(detection.config_file)
        if detection.save_dir:
            self._save_folder_var.set(detection.save_dir)
        if detection.log_dir:
            self._log_folder_var.set(detection.log_dir)
        self._write_output(_detection_text(detection))

    def _scan_inventory(self) -> None:
        inventory = self.app.scan_hosted_inventory(self._profile())
        self._write_output(_inventory_text(inventory))

    def _preview_upload(self) -> None:
        self.app.preview_hosted_upload(self._profile(), upload_paks=self._upload_paks_var.get())

    def _backup_configs(self) -> None:
        paths = self.app.backup_hosted_configs(self._profile())
        self._write_output("Downloaded hosted config backups:\n" + "\n".join(str(path) for path in paths or []))
        self.app.notify_info("Hosted Config Backup", f"Downloaded {len(paths)} hosted config file(s).")

    def _copy_fallback(self) -> None:
        self.app.copy_hosted_provider_fallback()
        self.app.notify_info("Fallback Copied", "Copied hosted provider-panel fallback instructions.")

    def _write_output(self, text: str) -> None:
        self._output.configure(state="normal")
        self._output.delete("1.0", tk.END)
        self._output.insert("1.0", text)
        self._output.configure(state="disabled")


def _detection_text(detection) -> str:
    rows = [
        detection.message,
        "",
        f"Server folder: {detection.server_folder or 'not detected'}",
        f"Mods folder: {detection.mods_dir or 'not detected'}",
        f"modlist.txt: {detection.modlist_path or 'not detected'}",
        f"Config folder: {detection.config_dir or 'not detected'}",
        f"ServerSettings.ini: {detection.config_file or 'not detected'}",
        f"Saves: {detection.save_dir or 'not detected'}",
        f"Logs: {detection.log_dir or 'not detected'}",
        "",
        "Checks:",
    ]
    rows.extend(f"- {label}: {'found' if exists else 'missing'}" for label, exists in detection.found_paths.items())
    return "\n".join(rows)


def _inventory_text(inventory) -> str:
    rows = [
        inventory.message or inventory.detection.message,
        "",
        "Remote paks:",
        *(inventory.pak_files or ["(none found)"]),
        "",
        "Config files:",
        *(inventory.config_files or ["(none found)"]),
        "",
        "Current remote modlist.txt:",
        inventory.modlist_text or "(missing or empty)",
    ]
    return "\n".join(rows)
