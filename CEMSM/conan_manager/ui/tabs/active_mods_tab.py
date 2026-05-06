"""Active Mods tab with local library and load-order management."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ...core.list_formatting import format_active_mod_row
from ...core.local_mod_library import ArchiveInspection, target_sync_labels
from ...core.modlist_service import missing_entries
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

FILTER_CHOICES = ["All", "Local", "Workshop", "Archive", "Missing", "Active"]


class ActiveModsTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._target_var = ctk.StringVar(value="Both")
        self._filter_var = ctk.StringVar(value="All")
        self._selected_index: int | None = None
        self._selected_library_row: tuple[str, str] | None = None
        self._library_rows: list[tuple[str, str]] = []
        self._component_by_id: dict[str, ModComponent] = {}
        self._source_by_id: dict[str, ModSource] = {}
        self._workshop_by_id: dict[str, WorkshopItem] = {}
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
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self._build_import_toolbar(body)
        self._build_library_panel(body)
        self._build_active_panel(body)
        self._build_details(body)
        self._build_footer()

    def _build_import_toolbar(self, parent) -> None:
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        for col in range(8):
            toolbar.grid_columnconfigure(col, weight=0)
        toolbar.grid_columnconfigure(7, weight=1)

        self._button(toolbar, "Import .pak", self._import_managed_paks, column=0, width=110)
        self._button(toolbar, "Link .pak", self._link_external_paks, column=1, width=100)
        self._button(toolbar, "Import .zip", self._import_archives, column=2, width=110)
        self._button(toolbar, "Import modlist", self._import_modlist_file, column=3, width=120)
        self._button(toolbar, "Load Client", self._load_client_modlist, column=4, width=105)
        self._button(toolbar, "Load Server", self._load_server_modlist, column=5, width=105)

        self._target_menu = ctk.CTkOptionMenu(
            toolbar,
            variable=self._target_var,
            values=list(TARGET_CHOICES.keys()),
            width=155,
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
        library_scroll = tk.Scrollbar(list_frame, orient="vertical", command=self._library_listbox.yview)
        library_scroll.grid(row=0, column=1, sticky="ns")
        self._library_listbox.configure(yscrollcommand=library_scroll.set)
        self._library_listbox.bind("<<ListboxSelect>>", self._on_library_select)

        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        controls.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            controls,
            text="Add to Active",
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._add_selected_library_to_active,
        ).grid(row=0, column=0, sticky="ew")

    def _build_active_panel(self, parent) -> None:
        panel = ctk.CTkFrame(parent, fg_color="#101010", border_width=1, border_color="#3a3028")
        panel.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            panel,
            text="Active Load Order",
            font=self.app.ui_font("card_title"),
            text_color="#f0b35f",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))

        list_frame = ctk.CTkFrame(panel, fg_color="#101010")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        self._active_listbox = tk.Listbox(
            list_frame,
            bg="#101010",
            fg="#f1e7d0",
            selectbackground="#7d4429",
            selectforeground="#ffffff",
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Cascadia Mono", self.app.ui_tokens.mono),
        )
        self._active_listbox.grid(row=0, column=0, sticky="nsew")
        active_scroll = tk.Scrollbar(list_frame, orient="vertical", command=self._active_listbox.yview)
        active_scroll.grid(row=0, column=1, sticky="ns")
        self._active_listbox.configure(yscrollcommand=active_scroll.set)
        self._active_listbox.bind("<<ListboxSelect>>", self._on_active_select)

        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        for column in range(5):
            controls.grid_columnconfigure(column, weight=1)
        self._button(controls, "Up", self._move_up, column=0, width=70)
        self._button(controls, "Down", self._move_down, column=1, width=75)
        self._button(controls, "Enable", lambda: self._set_selected_enabled(True), column=2, width=80)
        self._button(controls, "Disable", lambda: self._set_selected_enabled(False), column=3, width=85)
        self._button(controls, "Remove", self._remove_selected, column=4, width=85)

    def _build_details(self, parent) -> None:
        details = ctk.CTkFrame(parent, fg_color="#141210", border_width=1, border_color="#3a3028")
        details.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        details.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            details,
            text="Selection Details",
            font=self.app.ui_font("card_title"),
            text_color="#f0b35f",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        self._detail_label = ctk.CTkLabel(
            details,
            text="Select a library item or active entry.",
            font=self.app.ui_font("small"),
            text_color="#f1e7d0",
            anchor="w",
            justify="left",
            wraplength=1080,
        )
        self._detail_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

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
            text="Restore Previous",
            width=150,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=self._restore_selected_target,
        ).grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(
            footer,
            text="Preview Apply",
            width=140,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#7d4429",
            hover_color="#925333",
            command=self._preview_apply,
        ).grid(row=0, column=2)

    def _button(self, parent, text: str, command, *, column: int, width: int = 100) -> None:
        ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=command,
        ).grid(row=0, column=column, sticky="ew", padx=(0, 8))

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
            if source.source_type == SOURCE_ARCHIVE and (filter_value in {"All", "Archive"} or visible_components):
                self._insert_library_row(f"+ Archive: {source.display_name} ({len(source_components)} component(s))", "source", source.source_id)
                row_count += 1
            for component in visible_components:
                indent = "  " if source.source_type == SOURCE_ARCHIVE else ""
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

    def _refresh_active(self) -> None:
        entries = self.app.active_mods
        self._active_listbox.delete(0, tk.END)
        missing = set(missing_entries(entries))
        for index, entry in enumerate(entries, start=1):
            self._active_listbox.insert(tk.END, format_active_mod_row(index, entry, missing=entry.normalized_value in missing))
        if self._selected_index is not None and 0 <= self._selected_index < len(entries):
            self._active_listbox.selection_set(self._selected_index)
            self._active_listbox.see(self._selected_index)
        else:
            self._selected_index = None

    def _insert_library_row(self, text: str, kind: str, value: str) -> None:
        self._library_rows.append((kind, value))
        self._library_listbox.insert(tk.END, text)

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
        return f"{component.display_name} [{source}; {', '.join(badges)}]{companion_text}"

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
        return f"Workshop {item.workshop_id}: {item.display_title} [{', '.join(badges)}]"

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
        return False

    def _active_status_text(self) -> str:
        entries = self.app.active_mods
        if not entries:
            return "No active mods yet. Import library mods, add Workshop items, or import an existing modlist.txt."
        enabled = sum(1 for entry in entries if entry.enabled)
        disabled = len(entries) - enabled
        return f"{enabled} enabled, {disabled} disabled. Disabled entries stay in the list but are not written to modlist.txt."

    def _on_library_select(self, _event=None) -> None:
        selection = self._library_listbox.curselection()
        if not selection or int(selection[0]) >= len(self._library_rows):
            self._selected_library_row = None
            return
        self._selected_library_row = self._library_rows[int(selection[0])]
        self._detail_label.configure(text=self._library_detail_text(self._selected_library_row))

    def _on_active_select(self, _event=None) -> None:
        selection = self._active_listbox.curselection()
        self._selected_index = int(selection[0]) if selection else None
        if self._selected_index is not None and 0 <= self._selected_index < len(self.app.active_mods):
            self._detail_label.configure(text=self._active_detail_text(self.app.active_mods[self._selected_index]))

    def _library_detail_text(self, row: tuple[str, str]) -> str:
        kind, value = row
        if kind == "component":
            component = self._component_by_id.get(value)
            if component is None:
                return "Library component missing."
            lines = [
                f"{component.display_name} ({_source_label(component.source_type)})",
                f"Status: {self._component_status_badge(component, self._component_is_active(component))}",
                f"Primary pak: {component.primary_file.path}",
            ]
            if component.companion_files:
                lines.append("Companions: " + ", ".join(file.path.name for file in component.companion_files))
            if component.primary_file.original_path:
                lines.append(f"Source: {component.primary_file.original_path}")
            if component.primary_file.sha256:
                lines.append(f"Hash: {component.primary_file.sha256[:12]}...")
            return "\n".join(lines)
        if kind == "source":
            source = self._source_by_id.get(value)
            if source is None:
                return "Library source missing."
            return "\n".join(
                [
                    f"Archive source: {source.display_name}",
                    f"Original: {source.original_path or 'unknown'}",
                    f"Managed archive: {source.managed_path or 'unknown'}",
                    f"Components: {len(source.component_ids)}",
                ]
            )
        if kind == "workshop":
            item = self._workshop_by_id.get(value)
            if item is None:
                return "Workshop item missing."
            pak_text = ", ".join(str(path) for path in item.pak_paths) if item.pak_paths else "none"
            return "\n".join(
                [
                    f"{item.display_title} (Workshop {item.workshop_id})",
                    f"Status: {_workshop_status_label(item)}",
                    f"Folder: {item.folder_path or 'unknown'}",
                    f"Pak files: {pak_text}",
                    item.compatibility_note,
                ]
            )
        return "Select a library item or active entry."

    def _active_detail_text(self, entry: ActiveModEntry) -> str:
        lines = [
            f"{entry.display_name or Path(entry.value).stem or 'Unnamed mod'}",
            f"Status: {'Enabled' if entry.enabled else 'Disabled'}",
            f"Source: {entry.source_type.replace('_', ' ')}",
            f"modlist value/source pak: {entry.value}",
        ]
        if entry.workshop_id:
            lines.append(f"Workshop ID: {entry.workshop_id}")
        if entry.component_id:
            lines.append(f"Library component: {entry.component_id}")
        if entry.companion_paths:
            lines.append("Companions copied with apply: " + ", ".join(Path(path).name for path in entry.companion_paths))
        return "\n".join(lines)

    def _component_is_active(self, component: ModComponent) -> bool:
        return any(
            entry.component_id == component.component_id or _entry_key(entry.value) == _entry_key(str(component.primary_pak_path))
            for entry in self.app.active_mods
        )

    def _target_value(self) -> str:
        return TARGET_CHOICES.get(self._target_var.get(), TARGET_BOTH)

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
        window.geometry("700x420")
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
        if self._selected_library_row is None:
            return
        kind, value = self._selected_library_row
        if kind == "component":
            self.app.add_library_component_to_active(value)
        elif kind == "workshop":
            self.app.add_workshop_item_to_active(value)

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
        if self.app.active_mods:
            ok = self.app.confirm_action(
                "bulk",
                "Replace Active Mods",
                "Importing a modlist replaces the current active list in the manager. Continue?",
            )
            if not ok:
                return
        count = self.app.replace_active_mods_from_modlist(path)
        self.app.notify_info("Modlist Imported", f"Imported {count} modlist entr{'y' if count == 1 else 'ies'}.")

    def _move_up(self) -> None:
        if self._selected_index is None:
            return
        self._selected_index = self.app.move_active_mod(self._selected_index, -1)

    def _move_down(self) -> None:
        if self._selected_index is None:
            return
        self._selected_index = self.app.move_active_mod(self._selected_index, 1)

    def _set_selected_enabled(self, enabled: bool) -> None:
        if self._selected_index is None:
            return
        self.app.set_active_mod_enabled(self._selected_index, enabled)

    def _remove_selected(self) -> None:
        if self._selected_index is None:
            return
        self.app.remove_active_mod_at(self._selected_index)

    def _preview_apply(self) -> None:
        self.app.preview_apply_modlist(self._target_value())

    def _restore_selected_target(self) -> None:
        self.app.restore_selected_modlist(self._target_value())


def _entry_key(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").casefold()


def _source_label(source_type: str) -> str:
    if source_type == SOURCE_ARCHIVE:
        return "Archive"
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
