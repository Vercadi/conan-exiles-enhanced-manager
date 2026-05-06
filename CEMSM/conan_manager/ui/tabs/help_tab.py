"""Help, public links, and update checks."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
import webbrowser

import customtkinter as ctk

from ... import __app_name__, __version__
from ...core.project_links import GITHUB_URL, ISSUES_URL, KOFI_URL, PATREON_URL, RELEASES_URL


class HelpTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._release_url = RELEASES_URL
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="#101010")
        body.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)

        header = self._card(body, 0, "Help")
        ctk.CTkLabel(
            header,
            text=f"{__app_name__} v{__version__}",
            font=self.app.ui_font("page_title"),
            text_color="#f1e7d0",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            header,
            text=(
                "Conan-specific modlist, Workshop, local dedicated server, hosted server, profile, "
                "backup, and recovery manager."
            ),
            font=self.app.ui_font("body"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap * 2,
            justify="left",
            anchor="w",
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

        links = self._card(body, 1, "Links")
        link_buttons = ctk.CTkFrame(links, fg_color="transparent")
        link_buttons.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
        self._button(link_buttons, "GitHub", lambda: webbrowser.open(GITHUB_URL), column=0)
        self._button(link_buttons, "Issues", lambda: webbrowser.open(ISSUES_URL), column=1)
        self._button(link_buttons, "Releases", lambda: webbrowser.open(RELEASES_URL), column=2)
        self._button(link_buttons, "Ko-fi", lambda: webbrowser.open(KOFI_URL), column=3, color="#1f8bff")
        self._button(link_buttons, "Patreon", lambda: webbrowser.open(PATREON_URL), column=4, color="#f96854")
        ctk.CTkLabel(
            links,
            text="Use GitHub Issues for bugs and release downloads. Ko-fi and Patreon support continued work.",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap * 2,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

        updates = self._card(body, 2, "Updates")
        updates.grid_columnconfigure(1, weight=1)
        self._update_button = ctk.CTkButton(
            updates,
            text="Check for Updates",
            width=160,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._check_updates,
        )
        self._update_button.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
        self._open_release_button = ctk.CTkButton(
            updates,
            text="Open Release",
            width=140,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=lambda: webbrowser.open(self._release_url),
        )
        self._open_release_button.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=(0, 10))
        self._update_status = ctk.CTkLabel(
            updates,
            text="Manual update checks use GitHub Releases.",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap * 2,
            justify="left",
            anchor="w",
        )
        self._update_status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))

        support = self._card(body, 3, "Support Diagnostics")
        support_buttons = ctk.CTkFrame(support, fg_color="transparent")
        support_buttons.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
        self._button(support_buttons, "Copy Support Info", self.app.copy_support_info, column=0)
        self._button(support_buttons, "Save Support Info", self._save_support_info, column=1)
        self._button(support_buttons, "Open Data Folder", lambda: self.app.open_path(self.app.paths.data_dir), column=2)
        self._button(
            support_buttons,
            "Open Backup Folder",
            lambda: self.app.open_path(self.app.paths.backup_dir),
            column=3,
        )
        ctk.CTkLabel(
            support,
            text="Support info redacts hosted secrets before copying or saving.",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap * 2,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

    def _card(self, parent, row: int, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color="#191715", border_width=1, border_color="#3a3028")
        card.grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=self.app.ui_font("card_title"), text_color="#d3a15f").grid(
            row=0,
            column=0,
            sticky="w",
            padx=12,
            pady=(10, 8),
        )
        return card

    def _button(self, parent, text: str, command, *, column: int, color: str = "#3a3028") -> None:
        hover = "#4a3c31"
        if color == "#1f8bff":
            hover = "#166fcc"
        elif color == "#f96854":
            hover = "#d85745"
        ctk.CTkButton(
            parent,
            text=text,
            width=140,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color=color,
            hover_color=hover,
            command=command,
        ).grid(row=0, column=column, padx=(0 if column == 0 else 8, 0))

    def refresh(self) -> None:
        latest = self.app.latest_release
        if latest:
            self._release_url = latest.html_url or RELEASES_URL
            self._update_status.configure(text=f"Latest known release: v{latest.version}.", text_color="#c98a2e")
        else:
            self._release_url = RELEASES_URL
            self._update_status.configure(text="Manual update checks use GitHub Releases.", text_color="#b9aa92")

    def _check_updates(self) -> None:
        self._update_button.configure(state="disabled", text="Checking...")
        self._update_status.configure(text="Checking GitHub Releases...", text_color="#b9aa92")

        def _status(kind: str, message: str, release) -> None:
            self._update_button.configure(state="normal", text="Check for Updates")
            if release:
                self._release_url = release.html_url or RELEASES_URL
            color = "#74ad7f" if kind == "current" else "#c98a2e"
            if kind == "error":
                color = "#d06b61"
            self._update_status.configure(text=message, text_color=color)

        self.app.check_for_updates(show_no_update=True, status_callback=_status)

    def _save_support_info(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Support Info",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="conan-manager-support-info.txt",
        )
        if not path:
            return
        report = self.app.diagnostics.build_report(
            paths=self.app.paths,
            data_dir=self.app.paths.data_dir,
            backup_root=self.app.paths.backup_dir,
            hosted_profiles=self.app.hosted_profiles,
            activity_records=self.app.activity_records(limit=20),
        )
        Path(path).write_text(report, encoding="utf-8")
        self.app.notify_info("Support Info Saved", f"Saved support info to {path}.")

