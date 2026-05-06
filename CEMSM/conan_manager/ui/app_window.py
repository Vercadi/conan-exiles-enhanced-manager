"""Main application window."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
from tkinter import messagebox, simpledialog
import webbrowser

import customtkinter as ctk

from .. import __app_name__, __version__
from ..core.activity_log import ActivityLog
from ..core.backup_manager import BackupManager, BackupRecord
from ..core.compatibility import EnhancedStatus, detect_enhanced_status, old_mod_warnings
from ..core.discovery import discover_all
from ..core.hosted_profile_store import HostedProfileStore
from ..core.hosted_service import (
    apply_hosted_upload_plan,
    build_hosted_upload_plan,
    detect_hosted_paths,
    download_hosted_config_backups,
    provider_panel_fallback_text,
    scan_hosted_inventory,
    test_remote_connection,
)
from ..core.lazy_tabs import LazyTabController
from ..core.local_mod_library import LocalModLibraryStore, component_to_active_entry
from ..core.logging_service import setup_logging
from ..core.mod_profile_store import ModProfileStore
from ..core.modlist_service import (
    active_entries_from_modlist,
    active_entry_from_pak,
    active_entry_from_workshop_item,
    apply_modlist_plans,
    build_apply_plans,
    compare_client_server,
    restore_latest_modlist,
)
from ..core.profile_store import ProfileStore
from ..core.profile_warnings import profile_entry_warnings
from ..core.profile_diff import render_profile_modlist_diff
from ..core.release_guidance import (
    first_run_guidance,
    steamcmd_may_need_account,
    steamcmd_setup_guidance,
    workshop_download_failure_summary,
)
from ..core.server_config import read_server_config
from ..core.server_config_editor import (
    ServerConfigEdit,
    ServerConfigEditPlan,
    apply_server_config_edit_plan,
    build_server_config_edit_plan,
    config_preview_text,
)
from ..core.server_launcher import launch_dedicated_server
from ..core.server_logs import read_server_log_snapshot
from ..core.server_process import ServerProcessService
from ..core.support_diagnostics import SupportDiagnosticsService
from ..core.snapshot_service import list_snapshots, restore_snapshot_record, validate_snapshot_record
from ..core.startup import startup_message
from ..core.steamcmd_workshop import (
    SteamCmdProgress,
    detect_steamcmd_path,
    downloaded_workshop_ids,
    missing_workshop_ids,
    run_workshop_download,
    steamcmd_workshop_root,
    validate_steamcmd_path,
)
from ..core.update_checker import ReleaseInfo, check_for_update
from ..core.vanilla_restore import apply_vanilla_restore, build_vanilla_restore_plans, preview_vanilla_restore_text
from ..core.workshop_cache import WorkshopCache
from ..core.workshop_parser import parse_workshop_ids
from ..core.workshop_service import WorkshopService
from ..models.app_paths import ConanAppPaths
from ..models.app_preferences import AppPreferences
from ..models.hosted import HostedInventory, HostedPathDetection, HostedProfile, HostedUploadPlan
from ..models.modlist import (
    TARGET_BOTH,
    TARGET_CLIENT,
    TARGET_DEDICATED_SERVER,
    TARGET_LABELS,
    ActiveModEntry,
    ModlistTargetPlan,
)
from ..models.profiles import ModProfile, ServerProfile
from ..models.server import ServerConfigSnapshot, ServerLogSnapshot, ServerProcessStatus, ServerRuntimeState
from ..models.ui_state import BannerState, banner
from ..models.workshop import WORKSHOP_STATUS_DOWNLOADED, WorkshopItem
from ..core.remote_provider import RemoteProviderError, create_remote_provider, remote_error_summary
from ..utils.filesystem import ensure_dir
from ..utils.json_io import read_json, write_json
from .tabs.active_mods_tab import ActiveModsTab
from .tabs.dashboard_tab import DashboardTab
from .tabs.hosted_tab import HostedTab
from .tabs.profiles_tab import ProfilesTab
from .tabs.server_tab import ServerTab
from .tabs.settings_tab import SettingsTab
from .tabs.workshop_tab import WorkshopTab
from .tabs.help_tab import HelpTab
from .ui_tokens import UiTokens, ui_tokens_for_size

log = logging.getLogger(__name__)


def _resolve_app_dirs() -> tuple[Path, Path, Path]:
    import sys

    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ConanExilesEnhancedManager"
    else:
        base = Path(__file__).resolve().parent.parent.parent
    data_dir = base / "data"
    backup_dir = base / "backups"
    settings_file = data_dir / "settings.json"
    return data_dir, backup_dir, settings_file


DEFAULT_DATA_DIR, DEFAULT_BACKUP_DIR, SETTINGS_FILE = _resolve_app_dirs()


class AppWindow(ctk.CTk):
    """Root window for v0.1 read-only manager."""

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title(f"{__app_name__} v{__version__}")
        self.geometry("1220x780")
        self.minsize(1040, 680)

        self.preferences = AppPreferences()
        self.ui_tokens: UiTokens = ui_tokens_for_size("default")
        self.paths = ConanAppPaths()
        self.active_mods: list[ActiveModEntry] = []
        self.workshop_items: list[WorkshopItem] = []
        self.hosted_profiles: list[HostedProfile] = []
        self.named_mod_profiles: list[ModProfile] = []
        self.server_profiles: list[ServerProfile] = []
        self.banner_state = BannerState()
        self.workshop_scan_cancel_requested = False
        self.workshop_download_status = ""
        self._steamcmd_cancel_event: threading.Event | None = None
        self._steamcmd_thread: threading.Thread | None = None
        self.server_runtime = ServerRuntimeState()
        self.status_text = startup_message("shell")
        self.last_action = ""
        self.latest_release: ReleaseInfo | None = None

        self._init_services()
        self._build_ui()
        self.after(80, self._run_startup_discovery)

    def _init_services(self) -> None:
        ensure_dir(DEFAULT_DATA_DIR)
        ensure_dir(DEFAULT_BACKUP_DIR)
        setup_logging(DEFAULT_DATA_DIR)

        self.paths = self._load_settings()
        if self.paths.data_dir is None:
            self.paths.data_dir = DEFAULT_DATA_DIR
        if self.paths.backup_dir is None:
            self.paths.backup_dir = DEFAULT_BACKUP_DIR

        self.preferences = getattr(self, "preferences", AppPreferences()).normalized()
        self.ui_tokens = ui_tokens_for_size(self.preferences.ui_size)
        self.backup = BackupManager(self.paths.backup_dir or DEFAULT_BACKUP_DIR)
        self.diagnostics = SupportDiagnosticsService()
        self.mod_profiles = ModProfileStore(self.paths.data_dir or DEFAULT_DATA_DIR)
        self.active_mods = self.mod_profiles.list_entries()
        self.mod_library = LocalModLibraryStore(self.paths.data_dir or DEFAULT_DATA_DIR)
        self.profile_store = ProfileStore(self.paths.data_dir or DEFAULT_DATA_DIR)
        self.named_mod_profiles = self.profile_store.list_mod_profiles()
        self.server_profiles = self.profile_store.list_server_profiles()
        self.activity = ActivityLog(self.paths.data_dir or DEFAULT_DATA_DIR)
        self.workshop_cache: WorkshopCache | None = None
        self.workshop: WorkshopService | None = None
        self.workshop_items = []
        self.hosted_store = HostedProfileStore(self.paths.data_dir or DEFAULT_DATA_DIR)
        self.hosted_profiles = self.hosted_store.list_profiles()
        self.server_process = ServerProcessService()
        if not self.preferences.steamcmd_path:
            detected_steamcmd = detect_steamcmd_path(self.paths.data_dir or DEFAULT_DATA_DIR)
            if detected_steamcmd:
                self.preferences.steamcmd_path = str(detected_steamcmd)

    def _load_settings(self) -> ConanAppPaths:
        data = read_json(SETTINGS_FILE)
        self.preferences = AppPreferences.from_dict(data.get("preferences"))
        return ConanAppPaths.from_dict(data.get("paths"))

    def _run_startup_discovery(self) -> None:
        self.status_text = startup_message("discovery")
        self.show_banner("info", self.status_text)
        self.refresh_discovery()
        guidance = first_run_guidance(self.paths, steamcmd_path=self.resolved_steamcmd_path())
        self.show_banner("warning" if guidance else "success", guidance[0] if guidance else startup_message("ready"))
        if self.preferences.auto_check_updates:
            self.check_for_updates(show_no_update=False)

    def _ensure_workshop_services(self) -> None:
        if self.workshop_cache is None:
            self.status_text = "Loading Workshop cache..."
            self.workshop_cache = WorkshopCache(self.paths.data_dir or DEFAULT_DATA_DIR)
            self.workshop = WorkshopService(self.workshop_cache)
            self.workshop_items = self.workshop.list_items()

    def show_banner(self, kind: str, message: str) -> None:
        self.banner_state = banner(kind, message)
        bg, border = self.banner_state.colors
        self._banner_frame.configure(fg_color=bg, border_color=border)
        self._banner_label.configure(text=self.banner_state.message)
        self._banner_frame.grid()

    def clear_banner(self) -> None:
        self.banner_state = BannerState()
        self._banner_label.configure(text="")
        self._banner_frame.grid_remove()

    def save_settings(self) -> None:
        write_json(
            SETTINGS_FILE,
            {
                "preferences": self.preferences.to_dict(),
                "paths": self.paths.to_dict(),
            },
        )

    def resolved_steamcmd_path(self) -> Path | None:
        configured = self.preferences.steamcmd_path
        if configured and validate_steamcmd_path(configured).ok:
            return Path(configured)
        return detect_steamcmd_path(self.paths.data_dir or DEFAULT_DATA_DIR)

    def save_active_mods(self) -> None:
        self.mod_profiles.save(self.active_mods)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_banner()
        self.tabs = ctk.CTkTabview(
            self,
            fg_color="#101010",
            segmented_button_fg_color="#191715",
            segmented_button_selected_color="#7d4429",
            segmented_button_selected_hover_color="#925333",
            segmented_button_unselected_color="#24201c",
            segmented_button_unselected_hover_color="#3a3028",
            text_color="#f1e7d0",
            command=self._on_tab_selected,
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._tab_frames = {}
        for name in ("Dashboard", "Workshop", "Active Mods", "Profiles", "Server", "Hosted", "Settings", "Help"):
            frame = self.tabs.add(name)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)
            self._tab_frames[name] = frame
        self._lazy_tabs = LazyTabController(
            {
                "Dashboard": lambda: self._construct_tab("Dashboard", DashboardTab, "dashboard"),
                "Workshop": lambda: self._construct_tab("Workshop", WorkshopTab, "workshop_tab"),
                "Active Mods": lambda: self._construct_tab("Active Mods", ActiveModsTab, "active_mods_tab"),
                "Profiles": lambda: self._construct_tab("Profiles", ProfilesTab, "profiles_tab"),
                "Server": lambda: self._construct_tab("Server", ServerTab, "server_tab"),
                "Hosted": lambda: self._construct_tab("Hosted", HostedTab, "hosted_tab"),
                "Settings": lambda: self._construct_tab("Settings", SettingsTab, "settings_tab"),
                "Help": lambda: self._construct_tab("Help", HelpTab, "help_tab"),
            }
        )
        self._ensure_tab("Dashboard")

    def _build_banner(self) -> None:
        self._banner_frame = ctk.CTkFrame(self, fg_color="#172533", border_width=1, border_color="#7aa4c7")
        self._banner_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        self._banner_frame.grid_columnconfigure(0, weight=1)
        self._banner_label = ctk.CTkLabel(
            self._banner_frame,
            text=self.status_text,
            font=self.ui_font("small"),
            text_color="#f1e7d0",
            anchor="w",
        )
        self._banner_label.grid(row=0, column=0, sticky="ew", padx=10, pady=6)

    def _construct_tab(self, tab_name: str, cls, attr_name: str):
        if tab_name == "Workshop":
            self._ensure_workshop_services()
        frame = self._tab_frames[tab_name]
        tab = cls(frame, app=self)
        tab.grid(row=0, column=0, sticky="nsew")
        setattr(self, attr_name, tab)
        return tab

    def _ensure_tab(self, tab_name: str):
        return self._lazy_tabs.ensure(tab_name)

    def _on_tab_selected(self, *_args) -> None:
        self._ensure_tab(self.tabs.get())

    def select_tab(self, tab_name: str) -> None:
        self._ensure_tab(tab_name)
        self.tabs.set(tab_name)

    def ui_font(self, kind: str):
        mapping = {
            "page_title": ("Segoe UI", self.ui_tokens.page_title, "bold"),
            "title": ("Segoe UI", self.ui_tokens.title, "bold"),
            "card_title": ("Segoe UI", self.ui_tokens.card_title, "bold"),
            "row_title": ("Segoe UI", self.ui_tokens.row_title, "bold"),
            "body": ("Segoe UI", self.ui_tokens.body),
            "small": ("Segoe UI", self.ui_tokens.small),
            "mono": ("Cascadia Mono", self.ui_tokens.mono),
        }
        return ctk.CTkFont(*mapping.get(kind, mapping["body"]))

    def should_confirm(self, category: str) -> bool:
        mode = self.preferences.confirmation_mode
        if mode == "none":
            return False
        if category in {"destructive", "hosted", "write", "restore"}:
            return True
        if mode == "always":
            return True
        if mode == "destructive_only":
            return category in {"bulk"}
        return False

    def confirm_action(self, category: str, title: str, message: str) -> bool:
        if not self.should_confirm(category):
            return True
        return messagebox.askyesno(title, message)

    def notify_info(self, title: str, message: str) -> None:
        self.show_banner("success", message)
        if self.preferences.show_result_popups:
            messagebox.showinfo(title, message)

    def notify_warning(self, title: str, message: str, *, popup: bool = True) -> None:
        self.show_banner("warning", message)
        if popup and self.preferences.show_result_popups:
            messagebox.showwarning(title, message)

    def notify_error(self, title: str, message: str) -> None:
        self.show_banner("error", message)
        messagebox.showerror(title, message)

    def update_preferences(self, preferences: AppPreferences) -> None:
        self.preferences = preferences.normalized()
        self.ui_tokens = ui_tokens_for_size(self.preferences.ui_size)
        self.save_settings()
        self.status_text = "Settings saved."
        self.show_banner("success", "Settings saved. Restart the app to fully refresh existing tab sizing.")
        self._refresh_main_tabs()

    def check_for_updates(self, *, show_no_update: bool = True, status_callback=None) -> None:
        def _update_available(release: ReleaseInfo) -> None:
            def _show() -> None:
                self.latest_release = release
                message = f"Update available: v{release.version}."
                self.show_banner("warning", message)
                if status_callback:
                    status_callback("update", message, release)

            self.after(0, _show)

        def _no_update() -> None:
            def _show() -> None:
                message = f"You're up to date on v{__version__}."
                if show_no_update:
                    self.show_banner("success", message)
                if status_callback:
                    status_callback("current", message, None)

            self.after(0, _show)

        def _error(message: str) -> None:
            def _show() -> None:
                full_message = f"Update check unavailable: {message}"
                if show_no_update:
                    self.show_banner("warning", full_message)
                if status_callback:
                    status_callback("error", full_message, None)

            self.after(0, _show)

        check_for_update(__version__, _update_available, _no_update, _error)

    def refresh_discovery(self) -> None:
        self.status_text = "Refreshing local Conan and Steam state..."
        try:
            self.server_runtime.clear_restart_recommended()
            discovered = discover_all(
                known_client_root=self.paths.client_root,
                known_dedicated_server_root=self.paths.dedicated_server_root,
            )
            discovered.data_dir = self.paths.data_dir or DEFAULT_DATA_DIR
            discovered.backup_dir = self.paths.backup_dir or DEFAULT_BACKUP_DIR
            self.paths = discovered
            self.backup = BackupManager(self.paths.backup_dir or DEFAULT_BACKUP_DIR)
            self.save_settings()
            self.status_text = "Discovery refreshed."
            self.show_banner("success", self.status_text)
            log.info("Discovery refreshed from UI")
        except Exception as exc:
            self.status_text = f"Discovery failed: {exc}"
            self.show_banner("error", self.status_text)
            log.exception("Discovery failed")
            self.notify_error("Discovery Failed", str(exc))
        if hasattr(self, "dashboard"):
            self.dashboard.refresh()
        if hasattr(self, "active_mods_tab"):
            self.active_mods_tab.refresh()
        if hasattr(self, "workshop_tab"):
            self.workshop_tab.refresh()
        if hasattr(self, "profiles_tab"):
            self.profiles_tab.refresh()
        if hasattr(self, "server_tab"):
            self.server_tab.refresh()
        if hasattr(self, "hosted_tab"):
            self.hosted_tab.refresh()
        if hasattr(self, "settings_tab"):
            self.settings_tab.refresh()
        if hasattr(self, "help_tab"):
            self.help_tab.refresh()

    def backup_configs_and_saves(self) -> list[BackupRecord]:
        records = self.backup.backup_configs_and_saves(self.paths)
        self.last_action = f"Backed up {len(records)} file(s)." if records else "No config/save files found to back up."
        self.status_text = self.last_action
        self.show_banner("success" if records else "warning", self.last_action)
        self.record_activity("backup", "completed", target="configs/saves", details=f"{len(records)} file(s)")
        return records

    def copy_support_info(self) -> None:
        report = self.diagnostics.build_report(
            paths=self.paths,
            data_dir=self.paths.data_dir or DEFAULT_DATA_DIR,
            backup_root=self.paths.backup_dir or DEFAULT_BACKUP_DIR,
            hosted_profiles=self.hosted_profiles,
            activity_records=self.activity_records(limit=20),
            active_mods=self.active_mods,
            workshop_items=self.workshop_items,
            steamcmd_path=self.resolved_steamcmd_path(),
        )
        self.clipboard_clear()
        self.clipboard_append(report)
        self.status_text = "Support info copied to clipboard."
        self.show_banner("success", self.status_text)
        self.dashboard.refresh()

    def record_activity(self, action: str, result: str, *, target: str = "", details: str = "") -> None:
        self.activity.append(action=action, result=result, target=target, details=details)

    def activity_records(self, *, limit: int | None = None):
        return self.activity.list_records(limit=limit)

    def enhanced_status(self) -> EnhancedStatus:
        return detect_enhanced_status(self.paths)

    def old_mod_warnings(self) -> list[str]:
        return old_mod_warnings(self.active_mods, self.workshop_items)

    def snapshot_records(self, category: str | None = None) -> list[BackupRecord]:
        return list_snapshots(self.backup, category=category)

    def save_current_mod_profile(
        self,
        name: str,
        *,
        notes: str = "",
        target_coverage: list[str] | None = None,
    ) -> ModProfile:
        profile = self.profile_store.save_mod_profile(
            name=name,
            entries=self.active_mods,
            target_coverage=target_coverage or [TARGET_CLIENT, TARGET_DEDICATED_SERVER],
            notes=notes,
        )
        self.named_mod_profiles = self.profile_store.list_mod_profiles()
        self.last_action = f"Saved mod profile {profile.name}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("profile save", "saved", target=", ".join(profile.target_coverage), details=profile.name)
        self._refresh_main_tabs()
        return profile

    def duplicate_mod_profile(self, source_name: str, new_name: str) -> None:
        try:
            profile = self.profile_store.duplicate_mod_profile(source_name, new_name)
        except ValueError as exc:
            self.notify_warning("Duplicate Profile Failed", str(exc))
            return
        self.named_mod_profiles = self.profile_store.list_mod_profiles()
        self.last_action = f"Duplicated {source_name} to {profile.name}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("profile duplicate", "duplicated", details=f"{source_name} -> {profile.name}")
        self._refresh_main_tabs()

    def rename_mod_profile(self, old_name: str, new_name: str) -> None:
        try:
            profile = self.profile_store.rename_mod_profile(old_name, new_name)
        except ValueError as exc:
            self.notify_warning("Rename Profile Failed", str(exc))
            return
        self.named_mod_profiles = self.profile_store.list_mod_profiles()
        self.last_action = f"Renamed {old_name} to {profile.name}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("profile rename", "renamed", details=f"{old_name} -> {profile.name}")
        self._refresh_main_tabs()

    def delete_mod_profile(self, name: str) -> None:
        try:
            deleted = self.profile_store.delete_mod_profile(name)
        except ValueError as exc:
            self.notify_warning("Delete Profile Failed", str(exc))
            return
        if deleted:
            self.named_mod_profiles = self.profile_store.list_mod_profiles()
            self.last_action = f"Deleted mod profile {name}."
            self.status_text = self.last_action
            self.show_banner("success", self.last_action)
            self.record_activity("profile delete", "deleted", details=name)
            self._refresh_main_tabs()

    def preview_load_mod_profile(self, name: str) -> None:
        profile = self.profile_store.get_mod_profile(name)
        if profile is None:
            self.notify_warning("Profile Missing", f"Profile not found: {name}")
            return
        self._show_profile_load_preview(profile)

    def preview_restore_snapshot(self, backup_id: str) -> None:
        validation = validate_snapshot_record(self.backup, backup_id)
        if not validation.ok or validation.record is None:
            self.notify_warning("Restore Blocked", validation.message)
            return
        self._show_snapshot_restore_preview(validation.record)

    def preview_vanilla_restore(self, target: str) -> None:
        plans = build_vanilla_restore_plans(self.paths, target)
        self._show_vanilla_restore_preview(plans)

    def add_local_pak_paths(self, pak_paths: list[Path]) -> int:
        components = self.mod_library.import_pak_files(pak_paths)
        added = 0
        for component in components:
            if self._add_component_to_active(component.component_id, refresh=False, quiet=True):
                added += 1
        self.save_active_mods()
        self.last_action = f"Imported {len(components)} local mod(s); added {added} to Active Load Order."
        self.status_text = self.last_action
        self.show_banner("success" if added else "info", self.last_action)
        if components:
            self.record_activity("local mod import", "completed", target="library", details=f"{len(components)} mod(s)")
        self._refresh_main_tabs()
        return added

    def import_local_mod_files(self, paths: list[Path], *, link_external: bool = False) -> int:
        components = self.mod_library.import_pak_files(paths, link_external=link_external)
        mode = "linked" if link_external else "imported"
        self.last_action = f"{mode.title()} {len(components)} local mod(s) into the library."
        self.status_text = self.last_action
        self.show_banner("success" if components else "info", self.last_action)
        if components:
            self.record_activity("local mod import", "completed", target="library", details=f"{mode} {len(components)}")
        self._refresh_main_tabs()
        return len(components)

    def import_archive_paths(self, archive_paths: list[Path]) -> int:
        imported = 0
        warnings: list[str] = []
        for archive_path in archive_paths:
            try:
                components = self.mod_library.import_archive(archive_path)
            except ValueError as exc:
                warnings.append(f"{archive_path.name}: {exc}")
                continue
            imported += len(components)
        self.last_action = f"Imported {imported} archive mod component(s)."
        self.status_text = self.last_action
        self.show_banner("success" if imported else "warning", self.last_action)
        if imported:
            self.record_activity("archive import", "completed", target="library", details=f"{imported} component(s)")
        self._refresh_main_tabs()
        if warnings:
            self.notify_warning("Archive Needs Review", "\n".join(warnings))
        return imported

    def import_archive_path(self, archive_path: Path, *, selected_component_ids: list[str] | None = None) -> int:
        components = self.mod_library.import_archive(archive_path, selected_component_ids=selected_component_ids)
        self.last_action = f"Imported {len(components)} component(s) from {archive_path.name}."
        self.status_text = self.last_action
        self.show_banner("success" if components else "info", self.last_action)
        if components:
            self.record_activity("archive import", "completed", target="library", details=archive_path.name)
        self._refresh_main_tabs()
        return len(components)

    def add_library_component_to_active(self, component_id: str) -> bool:
        return self._add_component_to_active(component_id, refresh=True, quiet=False)

    def _add_component_to_active(self, component_id: str, *, refresh: bool, quiet: bool) -> bool:
        component = self.mod_library.component_by_id(component_id)
        if component is None:
            if not quiet:
                self.notify_warning("Library Mod Missing", "The selected library component no longer exists.")
            return False
        entry = component_to_active_entry(component)
        existing = {_entry_key(active.value) for active in self.active_mods}
        if _entry_key(entry.value) in existing:
            if not quiet:
                self.notify_info("Already Active", "That mod is already in Active Load Order.")
            return False
        self.active_mods.append(entry)
        self.save_active_mods()
        self.last_action = f"Added {entry.display_name or entry.value} to Active Load Order."
        self.status_text = self.last_action
        if not quiet:
            self.show_banner("success", self.last_action)
        if refresh:
            self._refresh_main_tabs(selected_mod_index=len(self.active_mods) - 1)
        return True

    def set_active_mod_enabled(self, index: int, enabled: bool) -> None:
        if 0 <= index < len(self.active_mods):
            entry = self.active_mods[index]
            entry.enabled = enabled
            self.save_active_mods()
            state = "enabled" if enabled else "disabled"
            self.last_action = f"{state.title()} {entry.display_name or entry.value} in Active Load Order."
            self.status_text = self.last_action
            self.show_banner("info", self.last_action)
            self._refresh_main_tabs(selected_mod_index=index)

    def library_components(self):
        return self.mod_library.list_components()

    def library_sources(self):
        return self.mod_library.list_sources()

    def add_workshop_ids_from_text(self, text: str) -> tuple[int, list[str]]:
        self._ensure_workshop_services()
        result = parse_workshop_ids(text)
        before = {item.workshop_id for item in self.workshop.list_items()}
        self.workshop_items = self.workshop.add_ids(result.ids, self.paths.workshop_content_dir)
        added = sum(1 for workshop_id in result.ids if workshop_id not in before)
        self.last_action = f"Added {added} Workshop item(s) to the local cache."
        self.status_text = self.last_action
        self.show_banner("success" if added else "info", self.last_action)
        self._refresh_main_tabs()
        return added, result.invalid_tokens

    def scan_workshop_content(self) -> int:
        self._ensure_workshop_services()
        self.workshop_scan_cancel_requested = False
        self.status_text = "Scanning Workshop content..."
        self.show_banner("info", self.status_text)
        if self.workshop_scan_cancel_requested:
            self.status_text = "Workshop scan canceled."
            self.show_banner("warning", self.status_text)
            return 0
        self.workshop_items = self.workshop.scan_roots(self._workshop_scan_roots())
        self.last_action = f"Scanned {len(self.workshop_items)} Workshop item(s)."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self._refresh_main_tabs()
        return len(self.workshop_items)

    def cancel_workshop_scan(self) -> None:
        self.workshop_scan_cancel_requested = True
        self.status_text = "Workshop scan cancel requested."
        self.show_banner("warning", self.status_text)

    def download_missing_workshop_items(self) -> None:
        self._ensure_workshop_services()
        self._start_workshop_steamcmd(missing_workshop_ids(self.workshop_items), action_label="Download Missing")

    def update_selected_workshop_item(self, workshop_id: str) -> None:
        self._start_workshop_steamcmd([workshop_id], action_label="Update Selected")

    def update_all_downloaded_workshop_items(self) -> None:
        self._ensure_workshop_services()
        self._start_workshop_steamcmd(downloaded_workshop_ids(self.workshop_items), action_label="Update All Downloaded")

    def cancel_workshop_steamcmd(self) -> None:
        if self._steamcmd_cancel_event is not None:
            self._steamcmd_cancel_event.set()
            self.workshop_download_status = "SteamCMD cancel requested..."
            self.show_banner("warning", self.workshop_download_status)
            self._refresh_main_tabs()

    def workshop_steamcmd_running(self) -> bool:
        return bool(self._steamcmd_thread and self._steamcmd_thread.is_alive())

    def _start_workshop_steamcmd(self, workshop_ids: list[str], *, action_label: str, use_account: bool = False) -> None:
        self._ensure_workshop_services()
        ids = [workshop_id for workshop_id in dict.fromkeys(str(value).strip() for value in workshop_ids) if workshop_id]
        if not ids:
            self.notify_info("No Workshop Items", "No Workshop items matched that action.")
            return
        if self.workshop_steamcmd_running():
            self.notify_warning("SteamCMD Busy", "A SteamCMD Workshop task is already running.")
            return
        steamcmd_path = self.resolved_steamcmd_path()
        status = validate_steamcmd_path(steamcmd_path)
        if not status.ok or status.path is None:
            self.notify_warning("SteamCMD Not Configured", steamcmd_setup_guidance(status.message))
            return
        account_label = " with Steam account" if use_account and self.preferences.steamcmd_username else ""
        self.workshop_download_status = f"{action_label}: starting SteamCMD{account_label} for {len(ids)} item(s)..."
        self.show_banner("info", self.workshop_download_status)
        self._steamcmd_cancel_event = threading.Event()

        def _progress(progress: SteamCmdProgress) -> None:
            message = progress.message or self.workshop_download_status
            self.after(0, lambda: self._set_workshop_download_status(message))

        def _worker() -> None:
            result = run_workshop_download(
                status.path,
                ids,
                username=self.preferences.steamcmd_username if use_account else "",
                progress_callback=_progress,
                cancel_event=self._steamcmd_cancel_event,
            )
            self.after(
                0,
                lambda: self._finish_workshop_steamcmd(
                    action_label,
                    ids,
                    result.ok,
                    result.canceled,
                    result.error or result.output_text,
                    used_account=use_account,
                ),
            )

        self._steamcmd_thread = threading.Thread(target=_worker, daemon=True)
        self._steamcmd_thread.start()
        self._refresh_main_tabs()

    def _set_workshop_download_status(self, message: str) -> None:
        self.workshop_download_status = message
        self.show_banner("info", message)
        if hasattr(self, "workshop_tab"):
            self.workshop_tab.refresh()

    def _finish_workshop_steamcmd(
        self,
        action_label: str,
        workshop_ids: list[str],
        ok: bool,
        canceled: bool,
        output_text: str,
        used_account: bool = False,
    ) -> None:
        self._ensure_workshop_services()
        if ok:
            self.workshop.add_ids(workshop_ids, self.paths.workshop_content_dir)
            self.workshop_items = self.workshop.scan_roots(self._workshop_scan_roots())
            self.last_action = f"{action_label} complete for {len(workshop_ids)} Workshop item(s)."
            self.status_text = self.last_action
            self.workshop_download_status = self.last_action
            self.show_banner("success", self.last_action)
            self.record_activity("workshop steamcmd", "completed", target=", ".join(workshop_ids), details=action_label)
        elif canceled:
            self.last_action = f"{action_label} canceled."
            self.status_text = self.last_action
            self.workshop_download_status = self.last_action
            self.show_banner("warning", self.last_action)
            self.record_activity("workshop steamcmd", "canceled", target=", ".join(workshop_ids), details=action_label)
        else:
            summary = workshop_download_failure_summary(output_text)
            self.last_action = f"{action_label} failed: {summary}"
            self.status_text = self.last_action
            self.workshop_download_status = self.last_action
            self.show_banner("error", self.last_action)
            self.record_activity("workshop steamcmd", "failed", target=", ".join(workshop_ids), details=summary)
            if steamcmd_may_need_account(output_text) and not used_account:
                username = self.preferences.steamcmd_username or simpledialog.askstring(
                    "Steam Account Optional",
                    "SteamCMD reported a login or ownership issue. Enter a Steam username for a retry, or leave blank to keep anonymous-only mode. Passwords are never saved.",
                    parent=self,
                )
                if username:
                    self.preferences.steamcmd_username = username.strip()
                    self.save_settings()
                    self._steamcmd_cancel_event = None
                    self._start_workshop_steamcmd(
                        workshop_ids,
                        action_label=f"{action_label} Account Retry",
                        use_account=True,
                    )
                    return
            self.notify_warning("SteamCMD Workshop Failed", self.last_action)
        self._steamcmd_cancel_event = None
        self._refresh_main_tabs()

    def add_workshop_item_to_active(self, workshop_id: str) -> bool:
        self._ensure_workshop_services()
        item = self.workshop_cache.get(workshop_id)
        if item is None:
            self.notify_warning("Workshop Item Missing", "The selected Workshop item is not in the local cache.")
            return False
        if item.status != WORKSHOP_STATUS_DOWNLOADED or len(item.pak_paths) != 1:
            self.notify_warning(
                "Workshop Pak Not Ready",
                "This Workshop item must have exactly one downloaded .pak before it can be added.",
            )
            return False
        entry = active_entry_from_workshop_item(item)
        existing = {_entry_key(active.value) for active in self.active_mods}
        if _entry_key(entry.value) in existing:
            self.notify_info("Already Active", "That Workshop pak is already in Active Mods.")
            return False
        self.active_mods.append(entry)
        self.save_active_mods()
        self.last_action = f"Added Workshop {workshop_id} to Active Mods."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self._refresh_main_tabs()
        return True

    def copy_ordered_workshop_ids(self) -> int:
        ids = [entry.workshop_id for entry in self.active_mods if entry.workshop_id]
        self.clipboard_clear()
        self.clipboard_append("\n".join(ids))
        self.last_action = f"Copied {len(ids)} ordered Workshop ID(s)."
        self.status_text = self.last_action
        self._refresh_main_tabs()
        return len(ids)

    def _workshop_scan_roots(self) -> list[Path | None]:
        roots = [self.paths.workshop_content_dir]
        extra = steamcmd_workshop_root(self.resolved_steamcmd_path())
        if extra and extra not in roots:
            roots.append(extra)
        return roots

    def replace_active_mods_from_modlist(self, modlist_path: Path) -> int:
        entries = active_entries_from_modlist(modlist_path)
        self.active_mods = entries
        self.save_active_mods()
        self.last_action = f"Imported {len(entries)} modlist entr{'y' if len(entries) == 1 else 'ies'}."
        self.status_text = self.last_action
        self._refresh_main_tabs()
        return len(entries)

    def remove_active_mod_at(self, index: int) -> None:
        if 0 <= index < len(self.active_mods):
            removed = self.active_mods.pop(index)
            self.save_active_mods()
            self.last_action = f"Removed {removed.display_name or removed.value}."
            self.status_text = self.last_action
            self.show_banner("info", self.last_action)
            self._refresh_main_tabs()

    def move_active_mod(self, index: int, delta: int) -> int:
        new_index = index + delta
        if not (0 <= index < len(self.active_mods) and 0 <= new_index < len(self.active_mods)):
            return index
        self.active_mods[index], self.active_mods[new_index] = self.active_mods[new_index], self.active_mods[index]
        self.save_active_mods()
        self.status_text = "Updated local mod order."
        self.show_banner("info", self.status_text)
        self._refresh_main_tabs(selected_mod_index=new_index)
        return new_index

    def preview_apply_modlist(self, target: str) -> None:
        if not self.active_mods:
            self.notify_warning("No Active Mods", "Add or import mods before applying a modlist.")
            return
        plans = build_apply_plans(self.paths, target, self.active_mods)
        if not plans:
            self.notify_error("No Target", "No target was selected.")
            return
        self._show_apply_preview(plans)

    def restore_selected_modlist(self, target: str) -> None:
        restored: list[str] = []
        targets = [TARGET_CLIENT, TARGET_DEDICATED_SERVER] if target == TARGET_BOTH else [target]
        for target_value in targets:
            modlist_path = self._modlist_path_for_target(target_value)
            if not modlist_path:
                continue
            record = restore_latest_modlist(self.backup, modlist_path)
            if record:
                restored.append(TARGET_LABELS.get(target_value, target_value))
        if restored:
            self.last_action = "Restored previous modlist for " + ", ".join(restored) + "."
            self.status_text = self.last_action
            self.record_activity("restore", "completed", target=", ".join(restored), details="latest modlist backup")
            self.notify_info("Restore Complete", self.last_action)
        else:
            self.notify_warning("No Backup Found", "No previous modlist backup exists for the selected target.")
        self._refresh_main_tabs()

    def parity_summary(self) -> str:
        return compare_client_server(self.paths).summary

    def dedicated_server_status(self) -> ServerProcessStatus:
        return self.server_process.status()

    def dedicated_server_config(self) -> ServerConfigSnapshot:
        return read_server_config(self.paths)

    def dedicated_server_log_snapshot(self) -> ServerLogSnapshot:
        return read_server_log_snapshot(self.paths)

    def preview_server_config_edit(self, edit: ServerConfigEdit) -> None:
        plan = build_server_config_edit_plan(
            self.paths,
            edit,
            process_status=self.dedicated_server_status(),
        )
        self._show_server_config_preview(plan)

    def launch_dedicated_server_from_ui(self) -> None:
        result = launch_dedicated_server(
            self.paths,
            launch_args=self.preferences.dedicated_server_launch_args,
            process_service=self.server_process,
        )
        self.last_action = result.message
        self.status_text = result.message
        self.record_activity("server launch", "requested" if result.started else "not started", target="dedicated", details=result.message)
        self.show_banner("success" if result.started else "warning", result.message)
        if result.started:
            self.server_runtime.clear_restart_recommended()
            self.notify_info("Server Launch Requested", f"{result.message}\nPID: {result.pid}")
        else:
            self.notify_warning("Server Not Started", result.message)
        self._refresh_main_tabs()

    def hosted_profile_named(self, name: str) -> HostedProfile | None:
        for profile in self.hosted_profiles:
            if profile.name == name:
                return profile
        return None

    def save_hosted_profile(self, profile: HostedProfile) -> HostedProfile:
        saved = self.hosted_store.upsert(profile)
        self.hosted_profiles = self.hosted_store.list_profiles()
        self.last_action = f"Saved hosted profile {saved.name}."
        self.status_text = self.last_action
        self._refresh_main_tabs()
        return saved

    def test_hosted_connection(self, profile: HostedProfile) -> str:
        try:
            message = test_remote_connection(create_remote_provider(profile))
        except RemoteProviderError as exc:
            message = remote_error_summary(exc)
        self.last_action = message
        self.status_text = message
        self.show_banner("warning" if "failed" in message.casefold() else "success", message)
        self._refresh_main_tabs()
        return message

    def autodetect_hosted_paths(self, profile: HostedProfile) -> HostedPathDetection:
        detection = detect_hosted_paths(create_remote_provider(profile), profile)
        self.last_action = detection.message
        self.status_text = detection.message
        self.show_banner("success" if detection.ok else "warning", detection.message)
        self._refresh_main_tabs()
        return detection

    def scan_hosted_inventory(self, profile: HostedProfile) -> HostedInventory:
        inventory = scan_hosted_inventory(create_remote_provider(profile), profile)
        self.last_action = inventory.message or inventory.detection.message
        self.status_text = self.last_action
        self.show_banner("success" if inventory.detection.ok else "warning", self.last_action)
        self._refresh_main_tabs()
        return inventory

    def preview_hosted_upload(self, profile: HostedProfile, *, upload_paks: bool) -> None:
        detection = detect_hosted_paths(create_remote_provider(profile), profile)
        plan = build_hosted_upload_plan(profile, detection, self.active_mods)
        self._show_hosted_upload_preview(plan, profile=profile, upload_paks=upload_paks)

    def backup_hosted_configs(self, profile: HostedProfile) -> list[Path]:
        try:
            paths = download_hosted_config_backups(
                create_remote_provider(profile),
                profile,
                self.paths.backup_dir or DEFAULT_BACKUP_DIR,
            )
        except RemoteProviderError as exc:
            self.notify_warning("Hosted Config Backup Failed", remote_error_summary(exc))
            return []
        self.last_action = f"Downloaded {len(paths)} hosted config backup(s)."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("backup", "completed", target="hosted configs", details=f"{len(paths)} file(s)")
        self._refresh_main_tabs()
        return paths

    def copy_hosted_provider_fallback(self) -> None:
        text = provider_panel_fallback_text(self.active_mods)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.last_action = "Copied hosted provider-panel fallback instructions."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self._refresh_main_tabs()

    def update_dedicated_server_launch_args(self, launch_args: str) -> None:
        self.preferences.dedicated_server_launch_args = str(launch_args or "").strip() or "-Messaging"
        self.preferences = self.preferences.normalized()
        self.save_settings()
        self.status_text = "Saved dedicated server launch args."
        self.show_banner("success", self.status_text)
        self._refresh_main_tabs()

    def open_path(self, path: Path | None) -> None:
        if not path or not path.exists():
            self.notify_warning("Path Not Found", str(path or "Path is not configured."))
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except AttributeError:
            webbrowser.open(path.as_uri())

    def _show_server_config_preview(self, plan: ServerConfigEditPlan) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Preview Server Config Changes")
        window.geometry("920x660")
        window.minsize(760, 500)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            window,
            text="Preview Server Config Changes",
            font=self.ui_font("title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))
        text = ctk.CTkTextbox(
            window,
            font=self.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        text.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)
        text.insert("1.0", config_preview_text(plan))
        text.configure(state="disabled")
        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="e", padx=14, pady=(4, 14))
        ctk.CTkButton(
            controls,
            text="Cancel",
            width=100,
            height=self.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=window.destroy,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Apply Config",
            width=130,
            height=self.ui_tokens.compact_button_height,
            fg_color="#7d4429",
            hover_color="#925333",
            state="normal" if plan.has_changes else "disabled",
            command=lambda: self._apply_server_config_edit(plan, window),
        ).grid(row=0, column=1)
        window.transient(self)
        window.grab_set()

    def _apply_server_config_edit(self, plan: ServerConfigEditPlan, window: ctk.CTkToplevel) -> None:
        if not plan.has_changes:
            self.notify_info("No Config Changes", "No server config changes were staged.")
            return
        result = apply_server_config_edit_plan(plan, self.backup)
        self.server_runtime.mark_restart_recommended("Dedicated Server config changed.")
        self.last_action = (
            f"Wrote {len(result.written_paths)} config file(s); "
            f"created {len(result.backup_records)} backup(s)."
        )
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity(
            "server config edit",
            "completed",
            target="dedicated",
            details=f"{len(result.written_paths)} file(s), {len(result.backup_records)} backup(s)",
        )
        window.destroy()
        self.notify_info("Server Config Applied", self.last_action)
        self._refresh_main_tabs()

    def _show_apply_preview(self, plans: list[ModlistTargetPlan]) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Preview Modlist Apply")
        window.geometry("860x620")
        window.minsize(720, 480)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            window,
            text="Preview Modlist Apply",
            font=self.ui_font("title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))
        text = ctk.CTkTextbox(
            window,
            font=self.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        text.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)
        text.insert("1.0", _preview_text(plans))
        text.configure(state="disabled")
        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="e", padx=14, pady=(4, 14))
        ctk.CTkButton(
            controls,
            text="Cancel",
            width=100,
            height=self.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=window.destroy,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Apply",
            width=120,
            height=self.ui_tokens.compact_button_height,
            fg_color="#7d4429",
            hover_color="#925333",
            command=lambda: self._apply_previewed_modlists(plans, window),
        ).grid(row=0, column=1)
        window.transient(self)
        window.grab_set()

    def _show_hosted_upload_preview(
        self,
        plan: HostedUploadPlan,
        *,
        profile: HostedProfile,
        upload_paks: bool,
    ) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Preview Hosted Upload")
        window.geometry("900x660")
        window.minsize(760, 500)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            window,
            text="Preview Hosted Upload",
            font=self.ui_font("title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))
        text = ctk.CTkTextbox(
            window,
            font=self.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        text.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)
        text.insert("1.0", _hosted_preview_text(plan, upload_paks=upload_paks))
        text.configure(state="disabled")
        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="e", padx=14, pady=(4, 14))
        ctk.CTkButton(
            controls,
            text="Cancel",
            width=100,
            height=self.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=window.destroy,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Apply / Upload",
            width=140,
            height=self.ui_tokens.compact_button_height,
            fg_color="#7d4429",
            hover_color="#925333",
            command=lambda: self._apply_hosted_upload(plan, profile=profile, upload_paks=upload_paks, window=window),
        ).grid(row=0, column=1)
        window.transient(self)
        window.grab_set()

    def _apply_hosted_upload(
        self,
        plan: HostedUploadPlan,
        *,
        profile: HostedProfile,
        upload_paks: bool,
        window: ctk.CTkToplevel,
    ) -> None:
        try:
            written = apply_hosted_upload_plan(create_remote_provider(profile), plan, upload_paks=upload_paks)
        except RemoteProviderError as exc:
            self.notify_warning("Hosted Upload Failed", remote_error_summary(exc))
            return
        self.last_action = f"Uploaded {len(written)} hosted file(s). Restart the hosted server from its panel."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("hosted upload", "completed", target=profile.name, details=f"{len(written)} file(s)")
        window.destroy()
        self.notify_info("Hosted Upload Complete", self.last_action)
        self._refresh_main_tabs()

    def _show_profile_load_preview(self, profile: ModProfile) -> None:
        self._ensure_workshop_services()
        warnings = profile_entry_warnings(profile.entries, self.workshop_items)
        window = ctk.CTkToplevel(self)
        window.title("Preview Profile Load")
        window.geometry("860x620")
        window.minsize(720, 480)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            window,
            text=f"Preview Profile: {profile.name}",
            font=self.ui_font("title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))
        text = ctk.CTkTextbox(
            window,
            font=self.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        text.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)
        text.insert("1.0", _profile_preview_text(profile, self.active_mods, warnings))
        text.configure(state="disabled")
        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="e", padx=14, pady=(4, 14))
        ctk.CTkButton(
            controls,
            text="Cancel",
            width=100,
            height=self.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=window.destroy,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Load Profile",
            width=130,
            height=self.ui_tokens.compact_button_height,
            fg_color="#7d4429",
            hover_color="#925333",
            command=lambda: self._apply_profile_load(profile, window),
        ).grid(row=0, column=1)
        window.transient(self)
        window.grab_set()

    def _apply_profile_load(self, profile: ModProfile, window: ctk.CTkToplevel) -> None:
        self.active_mods = list(profile.entries)
        self.save_active_mods()
        self.last_action = f"Loaded mod profile {profile.name}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("profile load", "loaded", target=", ".join(profile.target_coverage), details=profile.name)
        window.destroy()
        self._refresh_main_tabs()

    def _show_snapshot_restore_preview(self, record: BackupRecord) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Preview Snapshot Restore")
        window.geometry("780x520")
        window.minsize(680, 420)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            window,
            text="Preview Snapshot Restore",
            font=self.ui_font("title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))
        text = ctk.CTkTextbox(
            window,
            font=self.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        text.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)
        text.insert("1.0", _snapshot_preview_text(record))
        text.configure(state="disabled")
        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="e", padx=14, pady=(4, 14))
        ctk.CTkButton(
            controls,
            text="Cancel",
            width=100,
            height=self.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=window.destroy,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Restore",
            width=120,
            height=self.ui_tokens.compact_button_height,
            fg_color="#7d4429",
            hover_color="#925333",
            command=lambda: self._apply_snapshot_restore(record.backup_id, window),
        ).grid(row=0, column=1)
        window.transient(self)
        window.grab_set()

    def _apply_snapshot_restore(self, backup_id: str, window: ctk.CTkToplevel) -> None:
        try:
            record = restore_snapshot_record(self.backup, backup_id)
        except ValueError as exc:
            self.notify_warning("Restore Failed", str(exc))
            return
        self.last_action = f"Restored backup {record.backup_id}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("restore", "completed", target=record.category, details=record.source_path)
        window.destroy()
        self.notify_info("Snapshot Restored", self.last_action)
        self._refresh_main_tabs()

    def _show_vanilla_restore_preview(self, plans: list[ModlistTargetPlan]) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Preview Vanilla Restore")
        window.geometry("860x620")
        window.minsize(720, 480)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            window,
            text="Preview Vanilla Restore",
            font=self.ui_font("title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))
        text = ctk.CTkTextbox(
            window,
            font=self.ui_font("mono"),
            fg_color="#101010",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            wrap="none",
        )
        text.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)
        text.insert("1.0", preview_vanilla_restore_text(plans))
        text.configure(state="disabled")
        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="e", padx=14, pady=(4, 14))
        ctk.CTkButton(
            controls,
            text="Cancel",
            width=100,
            height=self.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=window.destroy,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Apply Vanilla",
            width=130,
            height=self.ui_tokens.compact_button_height,
            fg_color="#7d4429",
            hover_color="#925333",
            command=lambda: self._apply_vanilla_restore(plans, window),
        ).grid(row=0, column=1)
        window.transient(self)
        window.grab_set()

    def _apply_vanilla_restore(self, plans: list[ModlistTargetPlan], window: ctk.CTkToplevel) -> None:
        result = apply_vanilla_restore(plans, self.backup)
        labels = [plan.label for plan in plans if plan.modlist_path != Path()]
        if any(plan.target == TARGET_DEDICATED_SERVER for plan in plans) and result.written_paths:
            self.server_runtime.mark_restart_recommended("Dedicated Server modlist cleared.")
        self.last_action = (
            f"Restored vanilla modlist for {', '.join(labels)}; "
            f"created {len(result.backup_ids)} backup(s)."
        )
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("vanilla restore", "completed", target=", ".join(labels), details=self.last_action)
        window.destroy()
        self.notify_info("Vanilla Restore Applied", self.last_action)
        self._refresh_main_tabs()

    def _apply_previewed_modlists(self, plans: list[ModlistTargetPlan], window: ctk.CTkToplevel) -> None:
        result = apply_modlist_plans(plans, self.backup)
        if any(plan.target == TARGET_DEDICATED_SERVER for plan in plans) and result.written_paths:
            self.server_runtime.mark_restart_recommended("Dedicated Server modlist changed.")
        self.last_action = (
            f"Wrote {len(result.written_paths)} modlist file(s); "
            f"copied {len(result.copied_paths)} mod file(s); "
            f"created {len(result.backup_ids)} backup(s)."
        )
        self.status_text = self.last_action
        window.destroy()
        self.show_banner("success", self.last_action)
        labels = [plan.label for plan in plans if plan.modlist_path != Path()]
        self.record_activity("modlist apply", "completed", target=", ".join(labels), details=self.last_action)
        if result.warnings:
            self.notify_warning("Modlist Applied With Warnings", self.last_action + "\n\n" + "\n".join(result.warnings))
        else:
            self.notify_info("Modlist Applied", self.last_action)
        self._refresh_main_tabs()

    def _modlist_path_for_target(self, target: str) -> Path | None:
        if target == TARGET_CLIENT:
            return self.paths.client_modlist_path
        if target == TARGET_DEDICATED_SERVER:
            return self.paths.dedicated_server_modlist_path
        return None

    def _refresh_main_tabs(self, *, selected_mod_index: int | None = None) -> None:
        if hasattr(self, "dashboard"):
            self.dashboard.refresh()
        if hasattr(self, "workshop_tab"):
            self.workshop_tab.refresh()
        if hasattr(self, "active_mods_tab"):
            self.active_mods_tab.refresh(selected_index=selected_mod_index)
        if hasattr(self, "profiles_tab"):
            self.profiles_tab.refresh()
        if hasattr(self, "server_tab"):
            self.server_tab.refresh()
        if hasattr(self, "hosted_tab"):
            self.hosted_tab.refresh()
        if hasattr(self, "settings_tab"):
            self.settings_tab.refresh()
        if hasattr(self, "help_tab"):
            self.help_tab.refresh()


def _entry_key(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").casefold()


def _preview_text(plans: list[ModlistTargetPlan]) -> str:
    sections: list[str] = []
    for plan in plans:
        current = [entry.value for entry in plan.current_entries]
        proposed = plan.proposed_values
        lines = [
            f"Target: {plan.label}",
            f"modlist.txt: {plan.modlist_path if str(plan.modlist_path) != '.' else 'not configured'}",
            f"Mods folder: {plan.mods_dir if str(plan.mods_dir) != '.' else 'not configured'}",
            f"Create Mods folder: {'yes' if plan.creates_mods_dir else 'no'}",
            f"Backup existing modlist: {'yes' if plan.backup_needed else 'no'}",
            "",
            "Current:",
            *(current or ["  (empty or missing)"]),
            "",
            "Proposed:",
            *(proposed or ["  (empty)"]),
        ]
        if plan.warnings:
            lines.extend(["", "Warnings:", *plan.warnings])
        if plan.file_copies:
            lines.extend(
                [
                    "",
                    "Target file copies:",
                    *[
                        (
                            f"{copy_plan.source_path} -> {copy_plan.target_path}"
                            f" {'(backup existing first)' if copy_plan.backup_needed else ''}"
                        )
                        for copy_plan in plan.file_copies
                    ],
                ]
            )
        sections.append("\n".join(lines))
    return "\n\n" + ("-" * 72 + "\n\n").join(sections)


def _hosted_preview_text(plan: HostedUploadPlan, *, upload_paks: bool) -> str:
    lines = [
        f"Profile: {plan.profile_name}",
        f"Remote Mods folder: {plan.remote_mods_dir or 'not detected'}",
        f"Remote modlist.txt: {plan.remote_modlist_path or 'not detected'}",
        f"Upload local pak files: {'yes' if upload_paks else 'no'}",
        "Restart required: yes, use the provider panel after upload",
        "",
        "Proposed remote modlist.txt:",
        plan.modlist_text or "(empty)",
        "",
        "Pak uploads:",
    ]
    if plan.pak_uploads:
        lines.extend(f"{upload.local_path} -> {upload.remote_path}" for upload in plan.pak_uploads)
    else:
        lines.append("(none)")
    if plan.missing_local_paks:
        lines.extend(["", "Missing local paks:", *plan.missing_local_paks])
    if plan.warnings:
        lines.extend(["", "Warnings:", *plan.warnings])
    if not plan.can_apply:
        lines.extend(["", "Blocked: plan is incomplete. Fix the warnings before applying."])
    return "\n".join(lines)


def _profile_preview_text(profile: ModProfile, current_entries: list[ActiveModEntry], warnings: list[str]) -> str:
    lines = [
        f"Profile: {profile.name}",
        f"Coverage: {', '.join(profile.target_coverage)}",
        f"Current Active Mods: {len(current_entries)}",
        f"Profile Mods: {len(profile.entries)}",
        "",
        "Current:",
        *([entry.value for entry in current_entries] or ["  (empty)"]),
        "",
        "Proposed Active Mods:",
        *([entry.value for entry in profile.entries] or ["  (empty / vanilla)"]),
        "",
        "Exact modlist diff:",
        render_profile_modlist_diff(current_entries, profile.entries),
    ]
    if profile.notes:
        lines.extend(["", "Notes:", profile.notes])
    if warnings:
        lines.extend(["", "Warnings:", *warnings])
    return "\n".join(lines)


def _snapshot_preview_text(record: BackupRecord) -> str:
    return "\n".join(
        [
            f"Backup ID: {record.backup_id}",
            f"Timestamp: {record.timestamp}",
            f"Category: {record.category}",
            f"Description: {record.description}",
            "",
            f"Restore to: {record.source_path}",
            f"Backup file: {record.backup_path}",
            "",
            "This restore copies the backup file back to its original source path.",
        ]
    )
