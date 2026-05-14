"""Workshop tab for local Steam Workshop metadata."""
from __future__ import annotations

from datetime import datetime
import tkinter as tk

import customtkinter as ctk

from ...models.workshop import (
    WORKSHOP_STATUS_DOWNLOADED,
    WORKSHOP_STATUS_DUPLICATE_PAK,
    WORKSHOP_STATUS_MISSING,
    WORKSHOP_STATUS_NO_PAK,
    WorkshopItem,
)


STATUS_LABELS = {
    WORKSHOP_STATUS_DOWNLOADED: "Downloaded",
    WORKSHOP_STATUS_MISSING: "Missing download",
    WORKSHOP_STATUS_NO_PAK: "No pak",
    WORKSHOP_STATUS_DUPLICATE_PAK: "Multiple pak",
}


class WorkshopTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._selected_index: int | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="#101010")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Steam Workshop",
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

        input_frame = ctk.CTkFrame(self, fg_color="#191715", border_width=1, border_color="#3a3028")
        input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        input_frame.grid_columnconfigure(0, weight=1)
        self._input = ctk.CTkTextbox(
            input_frame,
            height=72,
            font=self.app.ui_font("body"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
        )
        self._input.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        buttons = ctk.CTkFrame(input_frame, fg_color="transparent")
        buttons.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self._button(buttons, "Add IDs", self._add_ids, row=0)
        self._button(buttons, "Refresh Cache", self._refresh_cache, row=1)
        self._scan_button = self._button(buttons, "Scan Workshop", self._scan, row=2)
        self._button(buttons, "Cancel Scan", self.app.cancel_workshop_scan, row=3)
        self._download_missing_button = self._button(buttons, "Download Missing", self._download_missing, row=4)
        self._update_all_button = self._button(buttons, "Update Downloaded", self._update_all_downloaded, row=5)
        self._cancel_steamcmd_button = self._button(buttons, "Cancel SteamCMD", self.app.cancel_workshop_steamcmd, row=6)
        self._button(buttons, "SteamCMD Settings", lambda: self.app.select_tab("Settings"), row=7)

        list_frame = ctk.CTkFrame(self, fg_color="#191715", border_width=1, border_color="#3a3028")
        list_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        self._listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            bg="#101010",
            fg="#f1e7d0",
            selectbackground="#7d4429",
            selectforeground="#ffffff",
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Cascadia Mono", self.app.ui_tokens.mono),
        )
        self._listbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scrollbar = ctk.CTkScrollbar(
            list_frame,
            orientation="vertical",
            command=self._listbox.yview,
            fg_color="#101010",
            button_color="#3a3028",
            button_hover_color="#5d3424",
        )
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)
        self._listbox.configure(yscrollcommand=scrollbar.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)
        self._listbox.bind("<Button-3>", self._show_context_menu)

        footer = ctk.CTkFrame(self, fg_color="#101010")
        footer.grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 10))
        footer.grid_columnconfigure(0, weight=1)
        self._detail_label = ctk.CTkLabel(
            footer,
            text="",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
            justify="left",
        )
        self._detail_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            footer,
            text="Activate",
            width=120,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._add_selected_to_active,
        ).grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(
            footer,
            text="Update Selected",
            width=140,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._update_selected,
        ).grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(
            footer,
            text="Forget Selected",
            width=145,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._forget_selected,
        ).grid(row=0, column=3, padx=(0, 8))
        ctk.CTkButton(
            footer,
            text="Forget Missing",
            width=135,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._forget_missing,
        ).grid(row=0, column=4, padx=(0, 8))
        ctk.CTkButton(
            footer,
            text="Forget All",
            width=110,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._forget_all,
        ).grid(row=0, column=5, padx=(0, 8))
        ctk.CTkButton(
            footer,
            text="Copy Active IDs",
            width=140,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._copy_active_ids,
        ).grid(row=0, column=6)

    def _button(self, parent, text: str, command, *, row: int) -> ctk.CTkButton:
        button = ctk.CTkButton(
            parent,
            text=text,
            width=130,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=command,
        )
        button.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        return button

    def refresh(self) -> None:
        items = self.app.workshop_items
        self._listbox.delete(0, tk.END)
        for item in items:
            self._listbox.insert(tk.END, _row_text(item))
        if self._selected_index is not None and 0 <= self._selected_index < len(items):
            self._listbox.selection_set(self._selected_index)
            self._listbox.see(self._selected_index)
        else:
            self._selected_index = None
        old_warnings = self.app.old_mod_warnings()[:3]
        suffix = (" | " + "; ".join(old_warnings)) if old_warnings else ""
        steamcmd_status = f" | {self.app.workshop_download_status}" if self.app.workshop_download_status else ""
        if not self.app.resolved_steamcmd_path():
            steamcmd_status = " | SteamCMD not configured: open SteamCMD Settings before downloading"
        self._status_label.configure(
            text=f"{len(items)} Workshop item(s) cached. Local downloads are scanned and explicit.{steamcmd_status}{suffix}"
        )
        busy = self.app.workshop_steamcmd_running()
        self._download_missing_button.configure(state="disabled" if busy else "normal")
        self._update_all_button.configure(state="disabled" if busy else "normal")
        self._cancel_steamcmd_button.configure(state="normal" if busy else "disabled")
        self._refresh_detail()

    def _on_select(self, _event=None) -> None:
        selection = self._listbox.curselection()
        self._selected_index = int(selection[0]) if selection else None
        self._refresh_detail()

    def _show_context_menu(self, event) -> None:
        index = self._listbox.nearest(event.y)
        if not (0 <= index < len(self.app.workshop_items)):
            return
        if index not in {int(value) for value in self._listbox.curselection()}:
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(index)
        self._selected_index = index
        self._refresh_detail()
        item = self.app.workshop_items[index]
        menu = tk.Menu(self, tearoff=0, bg="#191715", fg="#f1e7d0", activebackground="#7d4429")
        menu.add_command(label="Add to Active Load Order", command=self._add_selected_to_active)
        menu.add_command(label="Download / Update with SteamCMD", command=self._update_selected)
        menu.add_command(label="Copy Workshop ID", command=lambda: self.app.copy_workshop_id(item.workshop_id))
        menu.add_command(label="Open Workshop Folder", command=lambda: self.app.open_path_in_shell(item.folder_path))
        menu.add_separator()
        menu.add_command(label="Forget Cache Entry", command=self._forget_selected)
        menu.add_command(label="Forget Missing Downloads", command=self._forget_missing)
        menu.add_command(label="Forget All Cached", command=self._forget_all)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _selected_item(self) -> WorkshopItem | None:
        if self._selected_index is None:
            return None
        items = self.app.workshop_items
        if 0 <= self._selected_index < len(items):
            return items[self._selected_index]
        return None

    def _selected_items(self) -> list[WorkshopItem]:
        items = self.app.workshop_items
        selected: list[WorkshopItem] = []
        for raw_index in self._listbox.curselection():
            index = int(raw_index)
            if 0 <= index < len(items):
                selected.append(items[index])
        return selected

    def _refresh_detail(self) -> None:
        item = self._selected_item()
        if item is None:
            self._detail_label.configure(text="Select a Workshop item to see local pak status.")
            return
        modified = datetime.fromtimestamp(item.modified_time).strftime("%Y-%m-%d %H:%M") if item.modified_time else "unknown"
        pak_summary = ", ".join(path.name for path in item.pak_paths) if item.pak_paths else "none"
        self._detail_label.configure(
            text=(
                f"ID {item.workshop_id} | {STATUS_LABELS.get(item.status, item.status)} | "
                f"{len(item.pak_paths)} pak(s): {pak_summary} | modified {modified}"
            )
        )

    def _add_ids(self) -> None:
        text = self._input.get("1.0", "end").strip()
        if not text:
            return
        added, invalid = self.app.add_workshop_ids_from_text(text)
        if invalid:
            self.app.notify_warning(
                "Some IDs Were Invalid",
                f"Added {added} Workshop item(s).\n\nInvalid input:\n" + "\n".join(invalid),
            )
        else:
            self.app.notify_info("Workshop IDs Added", f"Added {added} Workshop item(s).")

    def _scan(self) -> None:
        self._scan_button.configure(state="disabled", text="Scanning...")
        try:
            count = self.app.scan_workshop_content()
        finally:
            self._scan_button.configure(state="normal", text="Scan Workshop")
        self.app.notify_info("Workshop Scan Complete", f"Scanned {count} Workshop item(s).")

    def _refresh_cache(self) -> None:
        count = self.app.refresh_workshop_cache()
        self.app.notify_info("Workshop Cache Refreshed", f"Refreshed {count} cached Workshop item(s).")

    def _add_selected_to_active(self) -> None:
        items = self._selected_items()
        if not items:
            item = self._selected_item()
            items = [item] if item else []
        for item in items:
            self.app.add_workshop_item_to_active(item.workshop_id)

    def _download_missing(self) -> None:
        self.app.download_missing_workshop_items()

    def _update_selected(self) -> None:
        items = self._selected_items()
        if not items:
            item = self._selected_item()
            items = [item] if item else []
        self.app.update_selected_workshop_items([item.workshop_id for item in items])

    def _forget_selected(self) -> None:
        ids = [item.workshop_id for item in self._selected_items()]
        self.app.remove_workshop_cache_entries(ids)

    def _forget_missing(self) -> None:
        self.app.remove_missing_workshop_cache_entries()

    def _forget_all(self) -> None:
        self.app.remove_all_workshop_cache_entries()

    def _update_all_downloaded(self) -> None:
        self.app.update_all_downloaded_workshop_items()

    def _copy_active_ids(self) -> None:
        count = self.app.copy_ordered_workshop_ids()
        self.app.notify_info("Workshop IDs Copied", f"Copied {count} active Workshop ID(s).")


def _row_text(item: WorkshopItem) -> str:
    status = STATUS_LABELS.get(item.status, item.status)
    pak_count = len(item.pak_paths)
    return f"{item.workshop_id} | {status:<13} | {pak_count:>2} pak(s) | {item.display_title}"
