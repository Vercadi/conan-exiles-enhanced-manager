"""Profiles, snapshots, recovery, and activity tab."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ...models.modlist import TARGET_BOTH, TARGET_CLIENT, TARGET_DEDICATED_SERVER
from ...models.profiles import TARGET_HOSTED


RESTORE_TARGETS = {
    "Client": TARGET_CLIENT,
    "Dedicated Server": TARGET_DEDICATED_SERVER,
    "Both": TARGET_BOTH,
}


class ProfilesTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._selected_profile_index: int | None = None
        self._selected_snapshot_index: int | None = None
        self._profile_name_var = ctk.StringVar(value="Solo")
        self._profile_rename_var = ctk.StringVar(value="")
        self._target_var = ctk.StringVar(value="Both")
        self._client_var = ctk.BooleanVar(value=True)
        self._server_var = ctk.BooleanVar(value=True)
        self._hosted_var = ctk.BooleanVar(value=False)
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
            text="Profiles & Recovery",
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

        profiles = self._card(body, row=0, column=0, title="Mod Profiles")
        snapshots = self._card(body, row=0, column=1, title="Backup Snapshots")
        recovery = self._card(body, row=1, column=0, title="Vanilla Restore")
        activity = self._card(body, row=1, column=1, title="Recent Activity")

        profiles.grid_rowconfigure(1, weight=1)
        self._profile_list = self._listbox(profiles, row=1)
        self._profile_list.bind("<<ListboxSelect>>", self._on_profile_select)
        self._entry(profiles, "Profile Name", self._profile_name_var, row=2)
        self._entry(profiles, "Rename To", self._profile_rename_var, row=3)
        ctk.CTkLabel(
            profiles,
            text="Coverage",
            font=self.app.ui_font("body"),
            text_color="#b9aa92",
        ).grid(row=4, column=0, sticky="w", padx=12, pady=4)
        coverage = ctk.CTkFrame(profiles, fg_color="transparent")
        coverage.grid(row=4, column=1, sticky="ew", padx=12, pady=4)
        for col, (text, var) in enumerate(
            [("Client", self._client_var), ("Server", self._server_var), ("Hosted", self._hosted_var)]
        ):
            ctk.CTkCheckBox(
                coverage,
                text=text,
                variable=var,
                font=self.app.ui_font("small"),
                text_color="#f1e7d0",
                fg_color="#7d4429",
                hover_color="#925333",
            ).grid(row=0, column=col, sticky="w", padx=(0, 8))
        self._profile_notes = ctk.CTkTextbox(
            profiles,
            height=60,
            font=self.app.ui_font("body"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
        )
        self._profile_notes.grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
        profile_buttons = ctk.CTkFrame(profiles, fg_color="transparent")
        profile_buttons.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 10))
        for col in range(5):
            profile_buttons.grid_columnconfigure(col, weight=1)
        self._button(profile_buttons, "Save Current", self._save_current_profile, column=0, primary=True)
        self._button(profile_buttons, "Preview Load", self._preview_load_profile, column=1)
        self._button(profile_buttons, "Duplicate", self._duplicate_profile, column=2)
        self._button(profile_buttons, "Rename", self._rename_profile, column=3)
        self._button(profile_buttons, "Delete", self._delete_profile, column=4)

        snapshots.grid_rowconfigure(1, weight=1)
        self._snapshot_list = self._listbox(snapshots, row=1)
        self._snapshot_list.bind("<<ListboxSelect>>", self._on_snapshot_select)
        self._snapshot_detail = ctk.CTkLabel(
            snapshots,
            text="Select a backup snapshot.",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            wraplength=self.app.ui_tokens.panel_wrap,
            justify="left",
            anchor="w",
        )
        self._snapshot_detail.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
        snapshot_buttons = ctk.CTkFrame(snapshots, fg_color="transparent")
        snapshot_buttons.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 10))
        snapshot_buttons.grid_columnconfigure(0, weight=1)
        snapshot_buttons.grid_columnconfigure(1, weight=1)
        self._button(snapshot_buttons, "Refresh", self.refresh, column=0)
        self._button(snapshot_buttons, "Preview Restore", self._preview_restore_snapshot, column=1, primary=True)

        self._option(recovery, "Target", self._target_var, list(RESTORE_TARGETS.keys()), row=1)
        ctk.CTkLabel(
            recovery,
            text="Restores an empty modlist only. Existing .pak files are not deleted.",
            font=self.app.ui_font("small"),
            text_color="#c98a2e",
            wraplength=self.app.ui_tokens.panel_wrap,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=8)
        ctk.CTkButton(
            recovery,
            text="Preview Vanilla Restore",
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._preview_vanilla_restore,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 12))

        activity.grid_rowconfigure(1, weight=1)
        self._activity_text = ctk.CTkTextbox(
            activity,
            height=280,
            font=self.app.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        self._activity_text.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=(4, 12))

    def _card(self, parent, *, row: int, column: int, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color="#191715", border_width=1, border_color="#3a3028")
        card.grid(row=row, column=column, sticky="nsew", padx=(8 if column == 0 else 4, 8), pady=(0, 8))
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

    def _listbox(self, parent, *, row: int) -> tk.Listbox:
        frame = ctk.CTkFrame(parent, fg_color="#101010", border_width=1, border_color="#3a3028")
        frame.grid(row=row, column=0, columnspan=2, sticky="nsew", padx=12, pady=4)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        listbox = tk.Listbox(
            frame,
            bg="#101010",
            fg="#f1e7d0",
            selectbackground="#7d4429",
            selectforeground="#ffffff",
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            height=8,
            font=("Cascadia Mono", self.app.ui_tokens.mono),
        )
        listbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)
        listbox.configure(yscrollcommand=scrollbar.set)
        return listbox

    def _entry(self, parent, label: str, variable: ctk.StringVar, *, row: int) -> None:
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
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
        ).grid(row=row, column=1, sticky="ew", padx=12, pady=4)

    def _button(self, parent, text: str, command, *, column: int, primary: bool = False) -> None:
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
        profiles = self.app.named_mod_profiles
        snapshots = self.app.snapshot_records()
        self._profile_list.delete(0, tk.END)
        for profile in profiles:
            targets = ",".join(profile.target_coverage)
            self._profile_list.insert(tk.END, f"{profile.name} | {len(profile.entries)} mod(s) | {targets}")
        if self._selected_profile_index is not None and 0 <= self._selected_profile_index < len(profiles):
            self._profile_list.selection_set(self._selected_profile_index)
        self._snapshot_list.delete(0, tk.END)
        for record in snapshots:
            self._snapshot_list.insert(tk.END, f"{record.timestamp} | {record.category:<8} | {record.description}")
        if self._selected_snapshot_index is not None and 0 <= self._selected_snapshot_index < len(snapshots):
            self._snapshot_list.selection_set(self._selected_snapshot_index)
        self._status_label.configure(
            text=f"{len(profiles)} mod profile(s), {len(snapshots)} backup snapshot(s)."
        )
        self._refresh_activity()
        self._refresh_snapshot_detail()

    def _on_profile_select(self, _event=None) -> None:
        selection = self._profile_list.curselection()
        self._selected_profile_index = int(selection[0]) if selection else None
        profile = self._selected_profile()
        if not profile:
            return
        self._profile_name_var.set(profile.name)
        self._profile_rename_var.set("")
        self._client_var.set(TARGET_CLIENT in profile.target_coverage)
        self._server_var.set(TARGET_DEDICATED_SERVER in profile.target_coverage)
        self._hosted_var.set(TARGET_HOSTED in profile.target_coverage)
        self._profile_notes.delete("1.0", tk.END)
        self._profile_notes.insert("1.0", profile.notes)

    def _on_snapshot_select(self, _event=None) -> None:
        selection = self._snapshot_list.curselection()
        self._selected_snapshot_index = int(selection[0]) if selection else None
        self._refresh_snapshot_detail()

    def _selected_profile(self):
        if self._selected_profile_index is None:
            return None
        profiles = self.app.named_mod_profiles
        if 0 <= self._selected_profile_index < len(profiles):
            return profiles[self._selected_profile_index]
        return None

    def _selected_snapshot(self):
        if self._selected_snapshot_index is None:
            return None
        snapshots = self.app.snapshot_records()
        if 0 <= self._selected_snapshot_index < len(snapshots):
            return snapshots[self._selected_snapshot_index]
        return None

    def _coverage(self) -> list[str]:
        values: list[str] = []
        if self._client_var.get():
            values.append(TARGET_CLIENT)
        if self._server_var.get():
            values.append(TARGET_DEDICATED_SERVER)
        if self._hosted_var.get():
            values.append(TARGET_HOSTED)
        return values

    def _notes(self) -> str:
        return self._profile_notes.get("1.0", tk.END).strip()

    def _save_current_profile(self) -> None:
        profile = self.app.save_current_mod_profile(
            self._profile_name_var.get(),
            notes=self._notes(),
            target_coverage=self._coverage(),
        )
        self._profile_name_var.set(profile.name)
        self.app.notify_info("Profile Saved", f"Saved {profile.name}.")

    def _preview_load_profile(self) -> None:
        profile = self._selected_profile()
        if profile:
            self.app.preview_load_mod_profile(profile.name)

    def _duplicate_profile(self) -> None:
        profile = self._selected_profile()
        new_name = self._profile_rename_var.get().strip()
        if profile and new_name:
            self.app.duplicate_mod_profile(profile.name, new_name)
        elif profile:
            self.app.notify_warning("Duplicate Profile", "Enter a new name in Rename To.")

    def _rename_profile(self) -> None:
        profile = self._selected_profile()
        new_name = self._profile_rename_var.get().strip()
        if profile and new_name:
            self.app.rename_mod_profile(profile.name, new_name)
        elif profile:
            self.app.notify_warning("Rename Profile", "Enter a new name in Rename To.")

    def _delete_profile(self) -> None:
        profile = self._selected_profile()
        if not profile:
            return
        if self.app.confirm_action("destructive", "Delete Profile", f"Delete profile {profile.name}?"):
            self.app.delete_mod_profile(profile.name)

    def _preview_restore_snapshot(self) -> None:
        record = self._selected_snapshot()
        if record:
            self.app.preview_restore_snapshot(record.backup_id)

    def _preview_vanilla_restore(self) -> None:
        target = RESTORE_TARGETS.get(self._target_var.get(), TARGET_BOTH)
        self.app.preview_vanilla_restore(target)

    def _refresh_snapshot_detail(self) -> None:
        record = self._selected_snapshot()
        if not record:
            self._snapshot_detail.configure(text="Select a backup snapshot.")
            return
        self._snapshot_detail.configure(
            text=(
                f"ID: {record.backup_id}\n"
                f"Source: {record.source_path}\n"
                f"Backup: {record.backup_path}"
            )
        )

    def _refresh_activity(self) -> None:
        self._activity_text.configure(state="normal")
        self._activity_text.delete("1.0", tk.END)
        records = self.app.activity_records(limit=80)
        self._activity_text.insert("1.0", "\n".join(record.summary for record in records) or "No activity yet.")
        self._activity_text.configure(state="disabled")
