"""Active Mods tab with local library and load-order management."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, simpledialog

import customtkinter as ctk

from ...core.size_formatting import format_bytes
from ...core.list_formatting import format_active_mod_row
from ...core.local_mod_library import ArchiveInspection, normalize_mod_display_name, target_sync_labels
from ...core.modlist_service import missing_entries
from ...core.target_actions import classify_dropped_mod_files, invert_indices, next_first_letter_index
from ...core.workshop_service import workshop_display_name
from ...models.local_mod_library import (
    COMPONENT_DISABLED,
    COMPONENT_MISSING_MANAGED,
    COMPONENT_MISSING_SOURCE,
    SOURCE_ARCHIVE,
    SOURCE_EXTERNAL_LINK,
    SOURCE_LOCAL_FILES,
    ModComponent,
    ModSource,
)
from ...models.modlist import TARGET_BOTH, TARGET_CLIENT, TARGET_DEDICATED_SERVER, ActiveModEntry
from ...models.workshop import (
    WORKSHOP_STATUS_DOWNLOADED,
    WORKSHOP_STATUS_DUPLICATE_PAK,
    WORKSHOP_STATUS_MISSING,
    WORKSHOP_STATUS_NO_PAK,
    WorkshopItem,
)


TARGET_CHOICES = {
    "Client": TARGET_CLIENT,
    "Dedicated Server": TARGET_DEDICATED_SERVER,
    "Both": TARGET_BOTH,
}

FILTER_CHOICES = ["All", "Local", "Workshop", "Archive", "Missing", "Active", "Inactive / Not Active"]
ACTIVE_FILTER_CHOICES = [
    "All",
    "Client Target",
    "Server Target",
    "Both Targets",
    "Client Only",
    "Server Only",
    "Unsynced",
    "Missing/Outdated",
    "Inactive / Disabled",
]


class ActiveModsTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._target_var = ctk.StringVar(value="Both")
        self._filter_var = ctk.StringVar(value="All")
        self._active_filter_var = ctk.StringVar(value="All")
        self._selected_index: int | None = None
        self._selected_library_row: tuple[str, str] | None = None
        self._library_rows: list[tuple[str, str]] = []
        self._active_rows: list[int] = []
        self._component_by_id: dict[str, ModComponent] = {}
        self._source_by_id: dict[str, ModSource] = {}
        self._workshop_by_id: dict[str, WorkshopItem] = {}
        self._drag_source: str | None = None
        self._drag_start_xy: tuple[int, int] = (0, 0)
        self._drag_start_row: int | None = None
        self._drag_started = False
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
            text="Active Mods",
            font=self.app.ui_font("page_title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w")
        self._parity_label = ctk.CTkLabel(
            header,
            text="",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        )
        self._parity_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        body = ctk.CTkFrame(self, fg_color="#191715", border_width=1, border_color="#3a3028")
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(1, weight=8)
        body.grid_rowconfigure(2, weight=0)

        self._build_import_toolbar(body)
        self._build_library_panel(body)
        self._build_active_panel(body)
        self._build_details(body)
        self._build_footer()
        self._register_drag_and_drop()

    def _build_import_toolbar(self, parent) -> None:
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        for col in range(9):
            toolbar.grid_columnconfigure(col, weight=0)
        toolbar.grid_columnconfigure(8, weight=1)

        self._button(toolbar, "Import Pak", self._import_managed_paks, column=0, width=96)
        self._button(toolbar, "Link Pak", self._link_external_paks, column=1, width=88)
        self._button(toolbar, "Import Zip", self._import_archives, column=2, width=96)
        self._button(toolbar, "Import Order", self._import_modlist_file, column=3, width=112)
        self._button(toolbar, "Client Order", self._load_client_modlist, column=4, width=110)
        self._button(toolbar, "Server Order", self._load_server_modlist, column=5, width=110)

        self._target_menu = ctk.CTkOptionMenu(
            toolbar,
            variable=self._target_var,
            values=list(TARGET_CHOICES.keys()),
            width=132,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
        )
        self._target_menu.grid(row=0, column=6, padx=(8, 0))

    def _build_library_panel(self, parent) -> None:
        panel = ctk.CTkFrame(parent, fg_color="#101010", border_width=1, border_color="#3a3028")
        panel.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top,
            text="Library",
            font=self.app.ui_font("card_title"),
            text_color="#f0b35f",
        ).grid(row=0, column=0, sticky="w")
        self._filter_menu = ctk.CTkOptionMenu(
            top,
            variable=self._filter_var,
            values=FILTER_CHOICES,
            width=130,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
            command=lambda _value: self.refresh(),
        )
        self._filter_menu.grid(row=0, column=1, padx=(8, 0))

        self._library_status = ctk.CTkLabel(
            panel,
            text="",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        )
        self._library_status.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))

        list_frame = ctk.CTkFrame(panel, fg_color="#101010")
        list_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        self._library_listbox = tk.Listbox(
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
        self._library_listbox.grid(row=0, column=0, sticky="nsew")
        library_scroll = ctk.CTkScrollbar(
            list_frame,
            orientation="vertical",
            command=self._library_listbox.yview,
            fg_color="#101010",
            button_color="#3a3028",
            button_hover_color="#5d3424",
        )
        library_scroll.grid(row=0, column=1, sticky="ns")
        self._library_listbox.configure(yscrollcommand=library_scroll.set)
        self._library_listbox.bind("<<ListboxSelect>>", self._on_library_select)
        self._library_listbox.bind("<Button-3>", self._show_library_context_menu)
        self._library_listbox.bind("<ButtonPress-1>", self._begin_library_drag, add="+")
        self._library_listbox.bind("<B1-Motion>", self._track_drag_motion, add="+")
        self._library_listbox.bind("<ButtonRelease-1>", self._release_drag, add="+")
        self._library_listbox.bind("<KeyPress>", self._jump_library_by_letter)

        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        for column in range(3):
            controls.grid_columnconfigure(column, weight=1)
        ctk.CTkButton(
            controls,
            text="Activate",
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._add_selected_library_to_active,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        self._button(controls, "Sync", self._sync_selected_library_to_target, column=1, width=84)
        self._button(controls, "Forget", self._forget_selected_library_records, column=2, width=84)
        self._button(controls, "All", self._select_all_library, column=0, row=1, width=76)
        self._button(controls, "Invert", self._invert_library_selection, column=1, row=1, width=82)
        self._button(controls, "Clear", self._clear_library_selection, column=2, row=1, width=76)

    def _build_active_panel(self, parent) -> None:
        panel = ctk.CTkFrame(parent, fg_color="#101010", border_width=1, border_color="#3a3028")
        panel.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top,
            text="Active Load Order",
            font=self.app.ui_font("card_title"),
            text_color="#f0b35f",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self._active_filter_menu = ctk.CTkOptionMenu(
            top,
            variable=self._active_filter_var,
            values=ACTIVE_FILTER_CHOICES,
            width=158,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
            command=lambda _value: self.refresh(),
        )
        self._active_filter_menu.grid(row=0, column=1, padx=(8, 0))

        list_frame = ctk.CTkFrame(panel, fg_color="#101010")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        list_frame.grid_columnconfigure(0, weight=0)
        list_frame.grid_columnconfigure(1, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        order_controls = ctk.CTkFrame(list_frame, fg_color="transparent")
        order_controls.grid(row=0, column=0, sticky="ns", padx=(0, 6))
        for row, (label, command) in enumerate(
            (
                ("^^", self._move_to_top),
                ("^", self._move_up),
                ("v", self._move_down),
                ("vv", self._move_to_bottom),
            )
        ):
            ctk.CTkButton(
                order_controls,
                text=label,
                width=34,
                height=self.app.ui_tokens.compact_button_height,
                font=self.app.ui_font("body"),
                fg_color="#3a3028",
                hover_color="#4a3c31",
                command=command,
            ).grid(row=row, column=0, sticky="ew", pady=(0, 6))

        self._active_listbox = tk.Listbox(
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
        self._active_listbox.grid(row=0, column=1, sticky="nsew")
        active_scroll = ctk.CTkScrollbar(
            list_frame,
            orientation="vertical",
            command=self._active_listbox.yview,
            fg_color="#101010",
            button_color="#3a3028",
            button_hover_color="#5d3424",
        )
        active_scroll.grid(row=0, column=2, sticky="ns")
        self._active_listbox.configure(yscrollcommand=active_scroll.set)
        self._active_listbox.bind("<<ListboxSelect>>", self._on_active_select)
        self._active_listbox.bind("<Button-3>", self._show_active_context_menu)
        self._active_listbox.bind("<ButtonPress-1>", self._begin_active_drag, add="+")
        self._active_listbox.bind("<B1-Motion>", self._track_drag_motion, add="+")
        self._active_listbox.bind("<ButtonRelease-1>", self._release_drag, add="+")
        self._active_listbox.bind("<KeyPress>", self._jump_active_by_letter)

        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        for column in range(6):
            controls.grid_columnconfigure(column, weight=1)
        self._button(controls, "Enable", lambda: self._set_selected_enabled(True), column=0, width=80)
        self._button(controls, "Disable", lambda: self._set_selected_enabled(False), column=1, width=85)
        self._button(controls, "Remove", self._remove_selected, column=2, width=85)
        self._button(controls, "All", self._select_all_active, column=3, width=76)
        self._button(controls, "Invert", self._invert_active_selection, column=4, width=82)
        self._button(controls, "Clear", self._clear_active_selection, column=5, width=76)
        self._button(controls, "Sync", self._sync_selected_active_to_target, column=0, row=1, width=82)
        self._button(controls, "Uninstall", self._uninstall_selected_active_from_target, column=1, row=1, width=92)
        self._button(controls, "Dedupe", self.app.remove_duplicate_active_mods, column=2, row=1, width=82)

    def _build_details(self, parent) -> None:
        details = ctk.CTkFrame(parent, fg_color="#141210", border_width=1, border_color="#3a3028")
        details.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        details.configure(height=126)
        details.grid_propagate(False)
        details.grid_columnconfigure(0, weight=1)
        details.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            details,
            text="Selection Details",
            font=self.app.ui_font("card_title"),
            text_color="#f0b35f",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 2))
        self._detail_text = ctk.CTkTextbox(
            details,
            height=72,
            fg_color="#141210",
            text_color="#f1e7d0",
            border_width=0,
            font=("Cascadia Mono", self.app.ui_tokens.small),
            wrap="none",
            activate_scrollbars=True,
        )
        self._detail_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self._set_detail_text("Select a library item or active entry.")

    def _set_detail_text(self, text: str) -> None:
        self._detail_text.configure(state="normal")
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert("1.0", text)
        self._detail_text.configure(state="disabled")

    def _compact_target_suffix(self, entry: ActiveModEntry) -> str:
        states = self.app.active_entry_target_states(entry)
        labels = [_compact_state_label("C", states.get(TARGET_CLIENT, "not_configured"))]
        if self.app.dedicated_server_features_enabled():
            labels.append(_compact_state_label("S", states.get(TARGET_DEDICATED_SERVER, "not_configured")))
        return f" [{' | '.join(labels)}]"

    def _button(self, parent, text: str, command, *, column: int, row: int = 0, width: int = 100) -> None:
        ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=command,
        ).grid(row=row, column=column, sticky="ew", padx=(0, 8), pady=(0, 6))

    def _register_drag_and_drop(self) -> None:
        drop_enabled = False
        if hasattr(self.app, "register_file_drop_target"):
            drop_enabled = bool(self.app.register_file_drop_target(self, self._drop_files_to_library)) or drop_enabled
            drop_enabled = bool(self.app.register_file_drop_target(self._library_listbox, self._drop_files_to_library)) or drop_enabled
            drop_enabled = bool(self.app.register_file_drop_target(self._active_listbox, self._drop_files_to_active)) or drop_enabled
        hint = (
            "Drop .pak/.zip/modlist.txt from Windows Explorer here."
            if drop_enabled
            else "Drag library rows into Active Load Order."
        )
        self._set_detail_text(hint)

    def _begin_library_drag(self, event) -> None:
        index = self._library_listbox.nearest(event.y)
        if not (0 <= index < len(self._library_rows)):
            self._reset_drag()
            return
        if index not in {int(value) for value in self._library_listbox.curselection()}:
            self._library_listbox.selection_clear(0, tk.END)
            self._library_listbox.selection_set(index)
            self._on_library_select()
        self._drag_source = "library"
        self._drag_start_xy = (event.x_root, event.y_root)
        self._drag_start_row = index
        self._drag_started = False

    def _begin_active_drag(self, event) -> None:
        index = self._active_listbox.nearest(event.y)
        if not (0 <= index < len(self._active_rows)):
            self._reset_drag()
            return
        if index not in {int(value) for value in self._active_listbox.curselection()}:
            self._active_listbox.selection_clear(0, tk.END)
            self._active_listbox.selection_set(index)
            self._on_active_select()
        self._drag_source = "active"
        self._drag_start_xy = (event.x_root, event.y_root)
        self._drag_start_row = index
        self._drag_started = False

    def _track_drag_motion(self, event) -> None:
        if self._drag_source is None:
            return
        dx = abs(event.x_root - self._drag_start_xy[0])
        dy = abs(event.y_root - self._drag_start_xy[1])
        if dx + dy < 8:
            return
        if not self._drag_started:
            self._drag_started = True
            self.configure(cursor="hand2")
            if self._drag_source == "library":
                self._set_detail_text("Drop on Active Load Order to activate selected library mods.")
            else:
                self._set_detail_text("Drop inside Active Load Order to reorder selected mods.")

    def _release_drag(self, event) -> None:
        if self._drag_source is None:
            return
        source = self._drag_source
        started = self._drag_started
        target_widget = self.winfo_containing(event.x_root, event.y_root)
        self._reset_drag()
        if not started:
            return
        if target_widget == self._active_listbox and source == "library":
            rows = self._selected_library_rows()
            insert_index = self._active_drop_actual_index_from_root(event.y_root)
            self.app.add_library_rows_to_active(rows, insert_index=insert_index)
            return
        if target_widget == self._active_listbox and source == "active":
            indices = self._selected_active_indices()
            target_index = self._active_drop_actual_index_from_root(event.y_root)
            moved = self.app.move_active_mods_to_index(indices, target_index)
            self._select_active_actual_indices(moved)

    def _reset_drag(self) -> None:
        self._drag_source = None
        self._drag_start_row = None
        self._drag_started = False
        self.configure(cursor="")

    def _active_drop_actual_index(self, y: int) -> int:
        if not self._active_rows:
            return len(self.app.active_mods)
        row_index = self._active_listbox.nearest(y)
        if not (0 <= row_index < len(self._active_rows)):
            return len(self.app.active_mods)
        target_index = self._active_rows[row_index]
        bbox = self._active_listbox.bbox(row_index)
        if bbox and y > bbox[1] + (bbox[3] // 2):
            target_index += 1
        return max(0, min(target_index, len(self.app.active_mods)))

    def _active_drop_actual_index_from_root(self, root_y: int) -> int:
        return self._active_drop_actual_index(root_y - self._active_listbox.winfo_rooty())

    def refresh(self, *, selected_index: int | None = None) -> None:
        if selected_index is not None:
            self._selected_index = selected_index
        self._component_by_id = {component.component_id: component for component in self.app.library_components()}
        self._source_by_id = {source.source_id: source for source in self.app.library_sources()}
        self._workshop_by_id = {item.workshop_id: item for item in self.app.workshop_items}
        self._refresh_library()
        self._refresh_active()
        self._parity_label.configure(text=self.app.parity_summary())
        self._status_label.configure(text=self._active_status_text())

    def _refresh_library(self) -> None:
        selected_rows = set(self._selected_library_rows())
        self._pending_library_selection = selected_rows
        self._library_listbox.delete(0, tk.END)
        self._library_rows = []
        active_component_ids = {entry.component_id for entry in self.app.active_mods if entry.component_id}
        active_workshop_ids = {entry.workshop_id for entry in self.app.active_mods if entry.workshop_id}
        active_values = {_entry_key(entry.value) for entry in self.app.active_mods}
        filter_value = self._filter_var.get()
        row_count = 0

        for source in self._source_by_id.values():
            source_components = [
                self._component_by_id[component_id]
                for component_id in source.component_ids
                if component_id in self._component_by_id
            ]
            visible_components = [
                component
                for component in source_components
                if self._component_matches_filter(component, filter_value, active_component_ids, active_values)
            ]
            if not visible_components and source.source_type != SOURCE_ARCHIVE:
                continue
            show_archive_source = source.source_type == SOURCE_ARCHIVE and len(source_components) > 1
            if show_archive_source and (filter_value in {"All", "Archive"} or visible_components):
                self._insert_library_row(
                    f"Archive: {normalize_mod_display_name(source.display_name)} [{len(source_components)} mods]",
                    "source",
                    source.source_id,
                )
                row_count += 1
            for component in visible_components:
                indent = "  - " if show_archive_source else ""
                self._insert_library_row(
                    indent + self._component_row(component, component.component_id in active_component_ids),
                    "component",
                    component.component_id,
                )
                row_count += 1

        for item in self._workshop_by_id.values():
            if not self._workshop_matches_filter(item, filter_value, active_workshop_ids):
                continue
            self._insert_library_row(self._workshop_row(item, item.workshop_id in active_workshop_ids), "workshop", item.workshop_id)
            row_count += 1

        if row_count == 0:
            self._library_listbox.insert(tk.END, "No library items for this filter.")
        self._library_status.configure(text=f"{row_count} visible library item(s). Imports stay in app data until explicitly applied.")
        self._pending_library_selection = set()

    def _refresh_active(self) -> None:
        entries = self.app.active_mods
        previous_keys = set() if self._selected_index is not None else set(self._selected_active_keys())
        self._active_listbox.delete(0, tk.END)
        self._active_rows = []
        missing = set(missing_entries(entries))
        filter_value = self._active_filter_var.get()
        for actual_index, entry in enumerate(entries):
            if not self._active_entry_matches_filter(entry, filter_value):
                continue
            self._active_rows.append(actual_index)
            self._active_listbox.insert(
                tk.END,
                format_active_mod_row(actual_index + 1, entry, missing=entry.normalized_value in missing, show_value=False)
                + self._compact_target_suffix(entry),
            )
            if not entry.enabled:
                self._active_listbox.itemconfig(tk.END, foreground="#a89278")
            if _active_selection_key(entry, actual_index) in previous_keys:
                self._active_listbox.selection_set(tk.END)
        if self._selected_index is not None and 0 <= self._selected_index < len(entries):
            try:
                row_index = self._active_rows.index(self._selected_index)
            except ValueError:
                row_index = -1
            if row_index >= 0:
                self._active_listbox.selection_set(row_index)
                self._active_listbox.see(row_index)
            else:
                self._selected_index = None
        else:
            self._selected_index = None

    def _insert_library_row(self, text: str, kind: str, value: str) -> None:
        self._library_rows.append((kind, value))
        self._library_listbox.insert(tk.END, text)
        if (kind, value) in getattr(self, "_pending_library_selection", set()):
            self._library_listbox.selection_set(tk.END)

    def _component_row(self, component: ModComponent, is_active: bool) -> str:
        source = _source_label(component.source_type)
        badges = [self._component_status_badge(component, is_active)]
        badges.extend(target_sync_labels(
            component,
            client_mods_dir=self.app.paths.client_mods_dir,
            server_mods_dir=self.app.paths.dedicated_server_mods_dir,
        ))
        companion_count = len(component.companion_files)
        companion_text = f" +{companion_count} companion" if companion_count == 1 else (
            f" +{companion_count} companions" if companion_count else ""
        )
        return f"{self._component_display_name(component)} [{source}; {', '.join(badges)}]{companion_text}"

    def _component_display_name(self, component: ModComponent) -> str:
        source = self._source_by_id.get(component.source_id)
        if source and source.source_type == SOURCE_ARCHIVE and len(source.component_ids) == 1:
            return normalize_mod_display_name(source.display_name)
        return normalize_mod_display_name(component.display_name)

    def _component_status_badge(self, component: ModComponent, is_active: bool) -> str:
        if component.status == COMPONENT_MISSING_MANAGED:
            return "Missing managed file"
        if component.status == COMPONENT_MISSING_SOURCE:
            return "Missing external link"
        if component.status == COMPONENT_DISABLED:
            return "Disabled"
        if is_active:
            return "In active order"
        if component.source_type == SOURCE_EXTERNAL_LINK:
            return "Unmanaged external"
        return "Available"

    def _workshop_row(self, item: WorkshopItem, is_active: bool) -> str:
        badges = [_workshop_status_label(item)]
        if is_active:
            badges.append("In active order")
        return f"{workshop_display_name(item)} [Workshop {item.workshop_id}; {', '.join(badges)}]"

    def _component_matches_filter(
        self,
        component: ModComponent,
        filter_value: str,
        active_component_ids: set[str],
        active_values: set[str],
    ) -> bool:
        is_active = component.component_id in active_component_ids or _entry_key(str(component.primary_pak_path)) in active_values
        is_missing = component.status in {COMPONENT_MISSING_MANAGED, COMPONENT_MISSING_SOURCE}
        if filter_value == "All":
            return True
        if filter_value == "Local":
            return component.source_type in {SOURCE_LOCAL_FILES, SOURCE_EXTERNAL_LINK}
        if filter_value == "Archive":
            return component.source_type == SOURCE_ARCHIVE
        if filter_value == "Missing":
            return is_missing
        if filter_value == "Active":
            return is_active
        if filter_value == "Inactive / Not Active":
            return not is_active
        return False

    def _workshop_matches_filter(self, item: WorkshopItem, filter_value: str, active_workshop_ids: set[str]) -> bool:
        is_missing = item.status in {WORKSHOP_STATUS_MISSING, WORKSHOP_STATUS_NO_PAK, WORKSHOP_STATUS_DUPLICATE_PAK}
        if filter_value == "All":
            return True
        if filter_value == "Workshop":
            return True
        if filter_value == "Missing":
            return is_missing
        if filter_value == "Active":
            return item.workshop_id in active_workshop_ids
        if filter_value == "Inactive / Not Active":
            return item.workshop_id not in active_workshop_ids
        return False

    def _active_entry_matches_filter(self, entry: ActiveModEntry, filter_value: str) -> bool:
        if filter_value == "All":
            return True
        states = self.app.active_entry_target_states(entry)
        client_state = states.get(TARGET_CLIENT, "not_configured")
        server_state = states.get(TARGET_DEDICATED_SERVER, "not_configured")
        client_has_target = _state_is_in_target(client_state)
        server_has_target = _state_is_in_target(server_state)
        if filter_value == "Client Target":
            return client_has_target
        if filter_value == "Server Target":
            return server_has_target
        if filter_value == "Both Targets":
            return client_has_target and server_has_target
        if filter_value == "Client Only":
            return client_has_target and not server_has_target
        if filter_value == "Server Only":
            return server_has_target and not client_has_target
        if filter_value == "Unsynced":
            return entry.enabled and (client_state != "synced" or server_state != "synced")
        if filter_value == "Missing/Outdated":
            return any(_state_needs_attention(state) for state in (client_state, server_state))
        if filter_value == "Inactive / Disabled":
            return not entry.enabled
        return True

    def _jump_library_by_letter(self, event) -> str | None:
        return self._jump_listbox_by_letter(self._library_listbox, event)

    def _jump_active_by_letter(self, event) -> str | None:
        labels = [
            self._active_search_label(self.app.active_mods[actual_index])
            for actual_index in self._active_rows
            if 0 <= actual_index < len(self.app.active_mods)
        ]
        return self._jump_listbox_by_letter(self._active_listbox, event, labels=labels)

    def _jump_listbox_by_letter(self, listbox: tk.Listbox, event, *, labels: list[str] | None = None) -> str | None:
        char = getattr(event, "char", "")
        if len(char) != 1 or not char.isalnum():
            return None
        labels = labels or [listbox.get(index) for index in range(listbox.size())]
        current = int(listbox.curselection()[0]) if listbox.curselection() else -1
        index = next_first_letter_index(labels, char, start=current)
        if index is None:
            return None
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(index)
        listbox.activate(index)
        listbox.see(index)
        if listbox == self._library_listbox:
            self._on_library_select()
        else:
            self._on_active_select()
        return "break"

    @staticmethod
    def _active_search_label(entry: ActiveModEntry) -> str:
        return normalize_mod_display_name(entry.display_name or Path(entry.value).stem)

    def _selected_library_rows(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for raw_index in self._library_listbox.curselection():
            index = int(raw_index)
            if 0 <= index < len(self._library_rows):
                rows.append(self._library_rows[index])
        return rows

    def _selected_active_indices(self) -> list[int]:
        indices: list[int] = []
        for row in self._active_listbox.curselection():
            row_index = int(row)
            if 0 <= row_index < len(self._active_rows):
                indices.append(self._active_rows[row_index])
        return indices

    def _selected_active_keys(self) -> list[str]:
        return [
            _active_selection_key(self.app.active_mods[index], index)
            for index in self._selected_active_indices()
        ]

    def _select_all_library(self) -> None:
        if self._library_rows:
            self._library_listbox.selection_set(0, len(self._library_rows) - 1)
            self._on_library_select()

    def _invert_library_selection(self) -> None:
        selected = {int(index) for index in self._library_listbox.curselection()}
        self._library_listbox.selection_clear(0, tk.END)
        for index in invert_indices(len(self._library_rows), selected):
            self._library_listbox.selection_set(index)
        self._on_library_select()

    def _clear_library_selection(self) -> None:
        self._library_listbox.selection_clear(0, tk.END)
        self._selected_library_row = None
        self._set_detail_text("Select a library item or active entry.")

    def _select_all_active(self) -> None:
        if self._active_rows:
            self._active_listbox.selection_set(0, len(self._active_rows) - 1)
            self._on_active_select()

    def _invert_active_selection(self) -> None:
        selected = {int(index) for index in self._active_listbox.curselection()}
        self._active_listbox.selection_clear(0, tk.END)
        for index in invert_indices(len(self._active_rows), selected):
            self._active_listbox.selection_set(index)
        self._on_active_select()

    def _clear_active_selection(self) -> None:
        self._active_listbox.selection_clear(0, tk.END)
        self._selected_index = None
        self._set_detail_text("Select a library item or active entry.")

    def _select_active_actual_indices(self, indices: list[int]) -> None:
        selected = set(indices)
        self._active_listbox.selection_clear(0, tk.END)
        for row_index, actual_index in enumerate(self._active_rows):
            if actual_index in selected:
                self._active_listbox.selection_set(row_index)
        self._on_active_select()

    def _active_status_text(self) -> str:
        entries = self.app.active_mods
        if not entries:
            return "No active mods yet. Import library mods, add Workshop items, or import an existing modlist.txt."
        enabled = sum(1 for entry in entries if entry.enabled)
        disabled = len(entries) - enabled
        return (
            f"{enabled} enabled, {disabled} disabled. Disabled entries stay in the list but are not written to "
            "modlist.txt. Use the Active Load Order filter for target status; Ctrl/Shift-click rows or use All/Invert/Clear for multi-select."
        )

    def _on_library_select(self, _event=None) -> None:
        selection = self._library_listbox.curselection()
        if not selection or int(selection[0]) >= len(self._library_rows):
            self._selected_library_row = None
            return
        self._selected_library_row = self._library_rows[int(selection[0])]
        rows = self._selected_library_rows()
        if len(rows) > 1:
            self._set_detail_text(f"{len(rows)} library item(s) selected.")
        else:
            self._set_detail_text(self._library_detail_text(self._selected_library_row))

    def _on_active_select(self, _event=None) -> None:
        selection = self._active_listbox.curselection()
        indices = self._selected_active_indices()
        self._selected_index = indices[0] if indices else None
        if len(indices) > 1:
            self._set_detail_text(f"{len(indices)} active mod(s) selected.")
        elif self._selected_index is not None and 0 <= self._selected_index < len(self.app.active_mods):
            self._set_detail_text(self._active_detail_text(self.app.active_mods[self._selected_index]))

    def _library_detail_text(self, row: tuple[str, str]) -> str:
        kind, value = row
        if kind == "component":
            component = self._component_by_id.get(value)
            if component is None:
                return "Component missing."
            lines = [
                self._component_display_name(component),
                f"Status: {self._component_status_badge(component, self._component_is_active(component))}",
                f"Source: {_source_label(component.source_type)}",
                f"Pak size: {format_bytes(component.primary_file.size)}",
                f"Pak: {component.primary_file.path}",
            ]
            if component.primary_file.original_path:
                lines.append(f"Original: {component.primary_file.original_path}")
            if component.companion_files:
                companion_size = sum(file.size for file in component.companion_files)
                lines.append(
                    f"Companions: {len(component.companion_files)} file(s), {format_bytes(companion_size)} total - "
                    + ", ".join(file.path.name for file in component.companion_files)
                )
            return "\n".join(lines)
        if kind == "source":
            source = self._source_by_id.get(value)
            if source is None:
                return "Archive source missing."
            return "\n".join(
                [
                    f"{normalize_mod_display_name(source.display_name)}",
                    f"Archive size: {format_bytes(source.size)}",
                    f"Source archive: {source.original_path or 'unknown'}",
                    f"Managed archive: {source.managed_path or 'unknown'}",
                    f"Components: {len(source.component_ids)}",
                ]
            )
        if kind == "workshop":
            item = self._workshop_by_id.get(value)
            if item is None:
                return "Workshop item missing."
            pak_text = ", ".join(str(path) for path in item.pak_paths) if item.pak_paths else "none"
            remote_updated = f"Steam updated: {_timestamp_label(item.remote_time_updated)}"
            return "\n".join(
                [
                    f"{workshop_display_name(item)} (Workshop {item.workshop_id})",
                    f"Status: {_workshop_status_label(item)}",
                    f"Local size: {format_bytes(item.local_size)}",
                    f"Steam remote size: {format_bytes(item.remote_file_size)}",
                    remote_updated,
                    f"Folder: {item.folder_path or 'unknown'}",
                    f"Pak files: {pak_text}",
                    f"Tags: {', '.join(item.tags) if item.tags else 'none'}",
                    item.metadata_warning,
                    item.compatibility_note,
                ]
            )
        return "Select a library item or active entry."

    def _active_detail_text(self, entry: ActiveModEntry) -> str:
        labels = self.app.active_entry_target_labels(entry)
        lines = [
            f"{normalize_mod_display_name(entry.display_name or Path(entry.value).stem or 'Unnamed mod')}",
            f"Status: {'Enabled' if entry.enabled else 'Disabled'}",
            f"Source: {entry.source_type.replace('_', ' ')}",
            f"Targets: {' | '.join(labels) if labels else 'not configured'}",
            f"Source pak size: {format_bytes(_safe_size(Path(entry.value)))}",
            f"modlist value/source pak: {entry.value}",
        ]
        note_text = self.app.note_text_for_active_entry(entry)
        if note_text.strip():
            lines.append("Notes: saved")
        if entry.workshop_id:
            lines.append(f"Workshop ID: {entry.workshop_id}")
        if entry.component_id:
            lines.append(f"Library component: {entry.component_id}")
        if entry.companion_paths:
            lines.append("Companions copied with apply: " + ", ".join(Path(path).name for path in entry.companion_paths))
        lines.append(f"Client Mods folder: {self.app.paths.client_mods_dir or 'not configured'}")
        lines.append(f"Dedicated Mods folder: {self.app.paths.dedicated_server_mods_dir or 'not configured'}")
        lines.append("Hosted target: use the Hosted tab upload preview for remote status.")
        return "\n".join(lines)

    def _component_is_active(self, component: ModComponent) -> bool:
        return any(
            entry.component_id == component.component_id or _entry_key(entry.value) == _entry_key(str(component.primary_pak_path))
            for entry in self.app.active_mods
        )

    def _target_value(self) -> str:
        return TARGET_CHOICES.get(self._target_var.get(), TARGET_BOTH)


    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="#101010")
        footer.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 10))
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
            text="Save Order",
            width=120,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=lambda: self.app.save_active_load_order_profile_from_ui(self._target_value()),
        ).grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(
            footer,
            text="Restore Prev",
            width=125,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._restore_selected_target,
        ).grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(
            footer,
            text="Vanilla",
            width=105,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._preview_vanilla_restore,
        ).grid(row=0, column=3, padx=(0, 8))
        ctk.CTkButton(
            footer,
            text="Preview Apply",
            width=130,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._preview_apply,
        ).grid(row=0, column=4)

    def _import_managed_paks(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Import Conan pak components into library",
            filetypes=[("Conan mod files", "*.pak *.ucas *.utoc"), ("Pak files", "*.pak"), ("All files", "*.*")],
        )
        if paths:
            imported = self.app.import_local_mod_files([Path(path) for path in paths], link_external=False)
            if imported == 0:
                self.app.notify_info("No Mods Imported", "No new .pak groups were imported.")

    def _link_external_paks(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Link external Conan pak components",
            filetypes=[("Conan mod files", "*.pak *.ucas *.utoc"), ("Pak files", "*.pak"), ("All files", "*.*")],
        )
        if paths:
            linked = self.app.import_local_mod_files([Path(path) for path in paths], link_external=True)
            if linked == 0:
                self.app.notify_info("No Mods Linked", "No new external .pak groups were linked.")

    def _import_archives(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Import Conan mod archives",
            filetypes=[("Zip archives", "*.zip"), ("All files", "*.*")],
        )
        for raw_path in paths:
            archive_path = Path(raw_path)
            inspection = self.app.mod_library.inspect_archive(archive_path)
            if not inspection.components:
                self.app.notify_warning("Archive Has No Paks", f"{archive_path.name} does not contain any .pak files.")
                continue
            selected = self._archive_selected_component_ids(inspection)
            if selected is None:
                continue
            try:
                self.app.import_archive_path(archive_path, selected_component_ids=selected)
            except ValueError as exc:
                self.app.notify_warning("Archive Import Blocked", str(exc))

    def _drop_files_to_library(self, paths: list[Path]) -> None:
        self._import_dropped_files(paths, activate=False)

    def _drop_files_to_active(self, paths: list[Path]) -> None:
        self._import_dropped_files(paths, activate=True)

    def _import_dropped_files(self, paths: list[Path], *, activate: bool) -> None:
        grouped = classify_dropped_mod_files(paths)
        activated = 0
        if grouped.pak_files:
            new_rows = self._import_pak_drop(grouped.pak_files)
            if activate:
                activated += self.app.add_library_rows_to_active(new_rows)
        for archive_path in grouped.archive_files:
            new_rows = self._import_archive_drop(archive_path)
            if activate and new_rows:
                activated += self.app.add_library_rows_to_active(new_rows)
        if grouped.modlist_files:
            if len(grouped.modlist_files) > 1:
                self.app.notify_warning("Multiple Modlists Dropped", "Only the first dropped modlist.txt was imported.", popup=False)
            self._replace_from_modlist(grouped.modlist_files[0])
        if grouped.ignored_files:
            names = ", ".join(path.name for path in grouped.ignored_files[:4])
            if len(grouped.ignored_files) > 4:
                names += ", ..."
            self.app.notify_warning("Unsupported Drop Files", f"Ignored unsupported file(s): {names}", popup=False)
        if activate and activated:
            self._active_listbox.see(tk.END)

    def _import_pak_drop(self, paths: list[Path]) -> list[tuple[str, str]]:
        before = {component.component_id for component in self.app.library_components()}
        self.app.import_local_mod_files(paths, link_external=False)
        return [
            ("component", component.component_id)
            for component in self.app.library_components()
            if component.component_id not in before
        ]

    def _import_archive_drop(self, archive_path: Path) -> list[tuple[str, str]]:
        try:
            inspection = self.app.mod_library.inspect_archive(archive_path)
        except Exception as exc:
            self.app.notify_warning("Archive Import Blocked", f"{archive_path.name}: {exc}", popup=False)
            return []
        if not inspection.components:
            self.app.notify_warning("Archive Has No Paks", f"{archive_path.name} does not contain any .pak files.", popup=False)
            return []
        selected = self._archive_selected_component_ids(inspection)
        if selected is None:
            return []
        before = {component.component_id for component in self.app.library_components()}
        try:
            self.app.import_archive_path(archive_path, selected_component_ids=selected)
        except ValueError as exc:
            self.app.notify_warning("Archive Import Blocked", str(exc), popup=False)
            return []
        return [
            ("component", component.component_id)
            for component in self.app.library_components()
            if component.component_id not in before
        ]

    def _archive_selected_component_ids(self, inspection: ArchiveInspection) -> list[str] | None:
        selected = [component.component_id for component in inspection.components if not component.variant_group_id]
        if inspection.requires_variant_choice:
            for group_id in inspection.variant_group_ids:
                choices = [component for component in inspection.components if component.variant_group_id == group_id]
                choice = self._choose_archive_component(inspection.archive_path.name, group_id, choices)
                if choice is None:
                    return None
                selected.append(choice)
            return selected
        if inspection.ambiguous:
            names = "\n".join(f"- {component.display_name} ({component.pak_member})" for component in inspection.components)
            ok = self.app.confirm_action(
                "bulk",
                "Review Multi-Mod Archive",
                f"{inspection.archive_path.name} contains multiple pak groups. Import all of them?\n\n{names}",
            )
            if not ok:
                return None
        return selected or [component.component_id for component in inspection.components]

    def _choose_archive_component(self, archive_name: str, group_id: str, choices) -> str | None:
        window = ctk.CTkToplevel(self)
        window.title("Choose Archive Option")
        self.app.center_window(window, 700, 420)
        window.minsize(560, 360)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            window,
            text=f"{archive_name} option: {group_id}",
            font=self.app.ui_font("title"),
            text_color="#f1e7d0",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        listbox = tk.Listbox(
            window,
            bg="#101010",
            fg="#f1e7d0",
            selectbackground="#7d4429",
            selectforeground="#ffffff",
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Cascadia Mono", self.app.ui_tokens.mono),
        )
        listbox.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)
        for component in choices:
            listbox.insert(tk.END, f"{component.display_name} :: {component.pak_member}")
        if choices:
            listbox.selection_set(0)
        selected: dict[str, str | None] = {"value": None}

        def apply_choice() -> None:
            selection = listbox.curselection()
            if selection:
                selected["value"] = choices[int(selection[0])].component_id
            window.destroy()

        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="e", padx=14, pady=(4, 14))
        ctk.CTkButton(
            controls,
            text="Cancel",
            width=100,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=window.destroy,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Use Selected",
            width=130,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#7d4429",
            hover_color="#925333",
            command=apply_choice,
        ).grid(row=0, column=1)
        window.transient(self.app)
        window.grab_set()
        self.wait_window(window)
        return selected["value"]

    def _add_selected_library_to_active(self) -> None:
        rows = self._selected_library_rows()
        if not rows and self._selected_library_row is not None:
            rows = [self._selected_library_row]
        self.app.add_library_rows_to_active(rows)

    def _add_selected_library_to_position(self) -> None:
        rows = self._selected_library_rows()
        if not rows and self._selected_library_row is not None:
            rows = [self._selected_library_row]
        if not rows:
            self.app.notify_warning("No Library Item Selected", "Select one or more Library rows to add.", popup=False)
            return
        position = self._ask_position(
            "Add to Position",
            f"Position in Active Load Order (1-{len(self.app.active_mods) + 1}):",
            minimum=1,
            maximum=len(self.app.active_mods) + 1,
        )
        if position is None:
            return
        self.app.add_library_rows_to_active(rows, insert_index=position - 1)

    def _sync_selected_library_to_target(self) -> None:
        rows = self._selected_library_rows()
        if not rows and self._selected_library_row is not None:
            rows = [self._selected_library_row]
        self.app.preview_sync_library_rows(self._target_value(), rows)

    def _sync_selected_active_to_target(self) -> None:
        self.app.preview_sync_active_indices(self._target_value(), self._selected_active_indices())

    def _uninstall_selected_active_from_target(self) -> None:
        self.app.preview_uninstall_active_indices(self._target_value(), self._selected_active_indices())

    def _forget_selected_library_records(self) -> None:
        rows = self._selected_library_rows()
        if not rows and self._selected_library_row is not None:
            rows = [self._selected_library_row]
        if not rows:
            self.app.notify_warning("No Library Item Selected", "Select one or more Library rows to forget.", popup=False)
            return
        self.app.forget_library_rows(rows)

    def _show_library_context_menu(self, event) -> None:
        index = self._library_listbox.nearest(event.y)
        if not (0 <= index < len(self._library_rows)):
            return
        if index not in {int(value) for value in self._library_listbox.curselection()}:
            self._library_listbox.selection_clear(0, tk.END)
            self._library_listbox.selection_set(index)
            self._on_library_select()
        row = self._library_rows[index]
        menu = tk.Menu(self, tearoff=0, bg="#191715", fg="#f1e7d0", activebackground="#7d4429")
        kind, value = row
        if kind == "component":
            menu.add_command(label="Add to Active Load Order", command=self._add_selected_library_to_active)
            menu.add_command(label="Add to Position...", command=self._add_selected_library_to_position)
            self._add_sync_menu_items(menu, lambda target: self.app.preview_sync_library_rows(target, self._selected_library_rows()))
            menu.add_separator()
            menu.add_command(label="Open Source Folder", command=lambda: self._open_component_source(value))
            menu.add_command(label="Open Managed Folder", command=lambda: self._open_component_managed(value))
            menu.add_separator()
            menu.add_command(label="Forget Library Record", command=self._forget_selected_library_records)
        elif kind == "workshop":
            menu.add_command(label="Download / Update with SteamCMD", command=lambda: self.app.update_selected_workshop_item(value))
            menu.add_command(label="Add to Active Load Order", command=self._add_selected_library_to_active)
            menu.add_command(label="Add to Position...", command=self._add_selected_library_to_position)
            menu.add_command(label="Rename Display Name...", command=lambda: self.app.rename_workshop_display_name(value))
            menu.add_command(label="Refresh Metadata", command=lambda: self.app.refresh_selected_workshop_metadata([value]))
            self._add_sync_menu_items(menu, lambda target: self.app.preview_sync_library_rows(target, self._selected_library_rows()))
            menu.add_separator()
            menu.add_command(label="Copy Workshop ID", command=lambda: self.app.copy_workshop_id(value))
            menu.add_command(label="Open Workshop Folder", command=lambda: self._open_workshop_folder(value))
            menu.add_separator()
            menu.add_command(label="Forget Workshop Cache Entry", command=self._forget_selected_library_records)
        elif kind == "source":
            menu.add_command(label="Open Source Folder", command=lambda: self._open_source_row(value))
            menu.add_command(label="Open Managed Folder", command=lambda: self._open_source_managed(value))
            menu.add_separator()
            menu.add_command(label="Forget Archive Record", command=self._forget_selected_library_records)
        self._post_menu(menu, event)

    def _show_active_context_menu(self, event) -> None:
        index = self._active_listbox.nearest(event.y)
        if not (0 <= index < len(self._active_rows)):
            return
        if index not in {int(value) for value in self._active_listbox.curselection()}:
            self._active_listbox.selection_clear(0, tk.END)
            self._active_listbox.selection_set(index)
            self._on_active_select()
        entry = self.app.active_mods[self._active_rows[index]]
        menu = tk.Menu(self, tearoff=0, bg="#191715", fg="#f1e7d0", activebackground="#7d4429")
        menu.add_command(
            label="Disable" if entry.enabled else "Enable",
            command=lambda: self._set_selected_enabled(not entry.enabled),
        )
        menu.add_command(label="Move to Position...", command=self._move_selected_to_position)
        menu.add_command(label="Remove from Active", command=self._remove_selected)
        menu.add_command(label="Rename Display Name...", command=self._rename_selected_active)
        menu.add_command(label="Link Workshop ID", command=self._link_selected_active_to_workshop)
        self._add_sync_menu_items(menu, lambda target: self.app.preview_sync_active_indices(target, self._selected_active_indices()))
        menu.add_separator()
        menu.add_command(
            label="Uninstall from Client",
            command=lambda: self.app.preview_uninstall_active_indices(TARGET_CLIENT, self._selected_active_indices()),
        )
        menu.add_command(
            label="Uninstall from Dedicated Server",
            command=lambda: self.app.preview_uninstall_active_indices(TARGET_DEDICATED_SERVER, self._selected_active_indices()),
        )
        menu.add_separator()
        menu.add_command(label="Open Source Folder", command=lambda: self.app.open_path_in_shell(Path(entry.value)))
        menu.add_command(label="Open Client Mods Folder", command=lambda: self.app.open_path_in_shell(self.app.paths.client_mods_dir))
        menu.add_command(
            label="Open Server Mods Folder",
            command=lambda: self.app.open_path_in_shell(self.app.paths.dedicated_server_mods_dir),
        )
        self._post_menu(menu, event)

    def _link_selected_active_to_workshop(self) -> None:
        self.app.link_active_indices_to_workshop_id(self._selected_active_indices())

    def _rename_selected_active(self) -> None:
        self.app.rename_active_indices_display_name(self._selected_active_indices())

    def _move_selected_to_position(self) -> None:
        indices = self._selected_active_indices()
        if not indices:
            self.app.notify_warning("No Active Mods Selected", "Select one or more active mods first.", popup=False)
            return
        position = self._ask_position(
            "Move to Position",
            f"Position in Active Load Order (1-{len(self.app.active_mods)}):",
            minimum=1,
            maximum=len(self.app.active_mods),
        )
        if position is None:
            return
        moved = self.app.move_active_mods_to_index(indices, position - 1)
        self._select_active_actual_indices(moved)

    def _ask_position(self, title: str, prompt: str, *, minimum: int, maximum: int) -> int | None:
        return simpledialog.askinteger(
            title,
            prompt,
            parent=self,
            minvalue=minimum,
            maxvalue=maximum,
        )

    def _add_sync_menu_items(self, menu: tk.Menu, callback) -> None:
        menu.add_separator()
        menu.add_command(label="Install / Sync to Client", command=lambda: callback(TARGET_CLIENT))
        menu.add_command(label="Install / Sync to Dedicated Server", command=lambda: callback(TARGET_DEDICATED_SERVER))
        menu.add_command(label="Install / Sync to Both", command=lambda: callback(TARGET_BOTH))

    def _post_menu(self, menu: tk.Menu, event) -> None:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_component_source(self, component_id: str) -> None:
        component = self._component_by_id.get(component_id)
        if component:
            self.app.open_path_in_shell(component.primary_file.original_path or component.primary_file.path)

    def _open_component_managed(self, component_id: str) -> None:
        component = self._component_by_id.get(component_id)
        if component:
            self.app.open_path_in_shell(component.primary_file.path)

    def _open_source_row(self, source_id: str) -> None:
        source = self._source_by_id.get(source_id)
        if source:
            self.app.open_path_in_shell(source.original_path)

    def _open_source_managed(self, source_id: str) -> None:
        source = self._source_by_id.get(source_id)
        if source:
            self.app.open_path_in_shell(source.managed_path)

    def _open_workshop_folder(self, workshop_id: str) -> None:
        item = self._workshop_by_id.get(workshop_id)
        if item:
            self.app.open_path_in_shell(item.folder_path)

    def _import_modlist_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Import modlist.txt",
            filetypes=[("Conan modlist", "modlist.txt"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._replace_from_modlist(Path(path))

    def _load_client_modlist(self) -> None:
        path = self.app.paths.client_modlist_path
        if not path or not path.is_file():
            self.app.notify_warning("Client Modlist Missing", "Client modlist.txt does not exist yet.")
            return
        self._replace_from_modlist(path)

    def _load_server_modlist(self) -> None:
        path = self.app.paths.dedicated_server_modlist_path
        if not path or not path.is_file():
            self.app.notify_warning("Server Modlist Missing", "Dedicated server modlist.txt does not exist yet.")
            return
        self._replace_from_modlist(path)

    def _replace_from_modlist(self, path: Path) -> None:
        from ...core.modlist_service import active_entries_from_modlist

        incoming = active_entries_from_modlist(path)
        if not incoming and self.app.active_mods:
            self.app.notify_warning(
                "Modlist Is Empty",
                "That modlist has no entries, so Active Load Order was not changed. Use Restore Vanilla if you want an empty target modlist.",
            )
            return
        if self.app.active_mods:
            ok = self.app.confirm_action(
                "bulk",
                "Replace Active Mods",
                "Importing a modlist replaces the current Active Load Order in the manager. Save a profile first if you want to keep it. Continue?",
            )
            if not ok:
                return
        count = self.app.replace_active_mods_from_modlist(path)
        self.app.notify_info("Modlist Imported", f"Imported {count} modlist entr{'y' if count == 1 else 'ies'}.")

    def _move_up(self) -> None:
        indices = self._selected_active_indices()
        if not indices:
            return
        if len(indices) == 1:
            self._selected_index = self.app.move_active_mod(indices[0], -1)
        else:
            moved = self.app.move_active_mods(indices, -1)
            self._select_active_actual_indices(moved)

    def _move_down(self) -> None:
        indices = self._selected_active_indices()
        if not indices:
            return
        if len(indices) == 1:
            self._selected_index = self.app.move_active_mod(indices[0], 1)
        else:
            moved = self.app.move_active_mods(indices, 1)
            self._select_active_actual_indices(moved)

    def _move_to_top(self) -> None:
        moved = self.app.move_active_mods_to_edge(self._selected_active_indices(), to_top=True)
        self._select_active_actual_indices(moved)
        if moved:
            self._active_listbox.see(0)

    def _move_to_bottom(self) -> None:
        moved = self.app.move_active_mods_to_edge(self._selected_active_indices(), to_top=False)
        self._select_active_actual_indices(moved)
        if moved:
            self._active_listbox.see(tk.END)

    def _set_selected_enabled(self, enabled: bool) -> None:
        indices = self._selected_active_indices()
        if len(indices) == 1:
            self.app.set_active_mod_enabled(indices[0], enabled)
        else:
            self.app.set_active_mods_enabled(indices, enabled)

    def _remove_selected(self) -> None:
        indices = self._selected_active_indices()
        if len(indices) == 1:
            self.app.remove_active_mod_at(indices[0])
        else:
            self.app.remove_active_mods_at(indices)

    def _preview_apply(self) -> None:
        self.app.preview_apply_modlist(self._target_value())

    def _restore_selected_target(self) -> None:
        self.app.restore_selected_modlist(self._target_value())

    def _preview_vanilla_restore(self) -> None:
        self.app.preview_vanilla_restore(self._target_value())


def _entry_key(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").casefold()


def _active_selection_key(entry: ActiveModEntry, index: int) -> str:
    return f"{index}:{entry.component_id}:{entry.workshop_id}:{_entry_key(entry.value)}"


def _state_is_in_target(state: str) -> bool:
    return state in {"synced", "in_order", "missing_file", "outdated"}


def _state_needs_attention(state: str) -> bool:
    return state in {"missing_source", "missing_file", "outdated", "file_only"}


def _compact_state_label(prefix: str, state: str) -> str:
    labels = {
        "synced": "ok",
        "in_order": "list",
        "not_in_order": "off",
        "missing_source": "source?",
        "missing_file": "pak?",
        "outdated": "old",
        "file_only": "file",
        "not_configured": "n/a",
    }
    return f"{prefix}:{labels.get(state, state.replace('_', ' '))}"


def _source_label(source_type: str) -> str:
    if source_type == SOURCE_ARCHIVE:
        return "Archive ZIP"
    if source_type == SOURCE_EXTERNAL_LINK:
        return "Linked local"
    if source_type == SOURCE_LOCAL_FILES:
        return "Local"
    return source_type.replace("_", " ").title()


def _workshop_status_label(item: WorkshopItem) -> str:
    if item.status == WORKSHOP_STATUS_DOWNLOADED:
        if len(item.pak_paths) > 1:
            return "Multiple pak"
        return "Downloaded"
    if item.status == WORKSHOP_STATUS_MISSING:
        return "Missing download"
    if item.status == WORKSHOP_STATUS_NO_PAK:
        return "No pak"
    if item.status == WORKSHOP_STATUS_DUPLICATE_PAK:
        return "Multiple pak"
    return "Unknown"


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _timestamp_label(timestamp: int | float) -> str:
    if not timestamp:
        return "unknown"
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return "unknown"
