"""Main application window."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import webbrowser

import customtkinter as ctk

try:
    from tkinterdnd2 import COPY as DND_COPY
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - optional native drag/drop dependency
    DND_COPY = None
    DND_FILES = None
    TkinterDnD = None

from .. import __app_name__, __version__
from ..core.activity_log import ActivityLog
from ..core.backup_manager import BackupManager, BackupRecord
from ..core.compatibility import EnhancedStatus, detect_enhanced_status, old_mod_warnings
from ..core.discovery import discover_all, validate_client_root, validate_dedicated_server_root
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
from ..core.local_mod_library import LocalModLibraryStore, component_to_active_entry, normalize_mod_display_name
from ..core.logging_service import setup_logging
from ..core.mod_notes_store import ModNotesStore, filter_note_subjects, note_key_for_active_entry, subjects_for_mods
from ..core.mod_profile_store import ModProfileStore
from ..core.modlist_service import (
    active_entries_from_modlist,
    active_entry_from_pak,
    active_entry_from_workshop_item,
    apply_modlist_plans,
    apply_selected_uninstall_plans,
    build_apply_plans,
    build_selected_sync_plans,
    build_selected_uninstall_plans,
    compare_client_server,
    preview_selected_uninstall_text,
    restore_latest_modlist,
    target_install_state_for_entry,
    target_status_labels_for_entry,
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
from ..core.server_launcher import launch_client_game, launch_dedicated_server
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
from ..core.target_actions import move_items_to_edge, move_items_to_index, selected_active_entries
from ..core.update_checker import ReleaseInfo, check_for_update
from ..core.vanilla_restore import apply_vanilla_restore, build_vanilla_restore_plans, preview_vanilla_restore_text
from ..core.workshop_cache import WorkshopCache
from ..core.workshop_metadata import WorkshopMetadataError, fetch_workshop_metadata
from ..core.workshop_parser import parse_workshop_ids
from ..core.workshop_service import WorkshopService, workshop_display_name
from ..models.app_paths import ConanAppPaths
from ..models.app_paths import path_from_setting
from ..models.app_preferences import AppPreferences
from ..models.hosted import HostedInventory, HostedPathDetection, HostedProfile, HostedUploadPlan
from ..models.modlist import (
    TARGET_BOTH,
    TARGET_CLIENT,
    TARGET_DEDICATED_SERVER,
    TARGET_LABELS,
    APPLY_MODE_COPY,
    APPLY_MODE_SOURCE,
    ActiveModEntry,
    ModlistTargetPlan,
)
from ..models.profiles import ModProfile, ServerProfile
from ..models.server import ServerConfigSnapshot, ServerLogSnapshot, ServerProcessStatus, ServerRuntimeState
from ..models.ui_state import BannerState, banner
from ..models.workshop import WORKSHOP_STATUS_DOWNLOADED, WORKSHOP_STATUS_MISSING, WorkshopItem
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
from .tabs.notes_tab import NotesTab
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


def _asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "assets" / name
    return Path(__file__).resolve().parent.parent.parent / "assets" / name


class AppWindow(ctk.CTk):
    """Root window for v0.1 read-only manager."""

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title(f"{__app_name__} v{__version__}")
        self._window_icon_image = None
        self._set_window_icon()
        self.geometry("1360x900")
        self.minsize(1180, 760)

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
        self.native_file_drop_available = False
        self.server_runtime = ServerRuntimeState()
        self.status_text = startup_message("shell")
        self.last_action = ""
        self.latest_release: ReleaseInfo | None = None

        self._init_native_file_drop()
        self._init_services()
        self._build_ui()
        self.after(80, self._run_startup_discovery)

    def _init_native_file_drop(self) -> None:
        if TkinterDnD is None:
            return
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            self.native_file_drop_available = True
        except Exception as exc:  # pragma: no cover - depends on TkDND runtime DLL availability
            log.debug("Native file drag/drop unavailable: %s", exc)

    def _set_window_icon(self) -> None:
        png_path = _asset_path("app_icon.png")
        ico_path = _asset_path("app_icon.ico")
        try:
            if ico_path.is_file():
                self.iconbitmap(str(ico_path))
        except Exception as exc:
            log.debug("Failed to set .ico window icon: %s", exc)
        try:
            if png_path.is_file():
                self._window_icon_image = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._window_icon_image)
        except Exception as exc:
            log.debug("Failed to set .png window icon: %s", exc)

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
        self.mod_notes = ModNotesStore(self.paths.data_dir or DEFAULT_DATA_DIR)
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
        self.mod_notes.migrate_existing_notes(
            active_mods=self.active_mods,
            components=self.mod_library.list_components(),
            workshop_items=[],
        )
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
        guidance = first_run_guidance(
            self.paths,
            steamcmd_path=self.resolved_steamcmd_path(),
            dedicated_server_enabled=self.dedicated_server_features_enabled(),
        )
        self.show_banner("warning" if guidance else "success", guidance[0] if guidance else startup_message("ready"))
        if not self.preferences.first_run_setup_completed and not validate_client_root(self.paths.client_root):
            self.after(120, self.show_first_run_setup)
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
        self.grid_rowconfigure(2, weight=1)
        self._build_banner()
        self._build_global_quick_actions()
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
        self.tabs.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._tab_frames = {}
        for name in ("Dashboard", "Workshop", "Active Mods", "Profiles", "Notes", "Server", "Hosted", "Settings", "Help"):
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
                "Notes": lambda: self._construct_tab("Notes", NotesTab, "notes_tab"),
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

    def _build_global_quick_actions(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="#141210", border_width=1, border_color="#3a3028")
        bar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        bar.grid_columnconfigure(0, weight=0)
        ctk.CTkLabel(
            bar,
            text="Quick Actions",
            font=self.ui_font("small"),
            text_color="#f0b35f",
        ).grid(row=0, column=0, sticky="w", padx=(10, 8), pady=6)
        actions = [
            ("Start Game", self.launch_client_game_from_ui, "#7d4429"),
            ("Start Server", self.launch_dedicated_server_from_ui, "#7d4429"),
            ("Open Game Folder", self.open_client_root_folder, "#3a3028"),
            ("Open Dedicated Folder", self.open_dedicated_root_folder, "#3a3028"),
            ("Open Logs", self.open_dedicated_logs_folder, "#3a3028"),
            ("Backup Now", self.backup_configs_and_saves_from_ui, "#5d3424"),
        ]
        for index, (label, command, color) in enumerate(actions, start=1):
            bar.grid_columnconfigure(index, weight=1)
            ctk.CTkButton(
                bar,
                text=label,
                height=self.ui_tokens.compact_button_height,
                font=self.ui_font("body"),
                fg_color=color,
                hover_color="#925333" if color == "#7d4429" else "#4a3c31",
                command=command,
            ).grid(row=0, column=index, sticky="ew", padx=(0, 8), pady=6)

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

    def center_window(self, window: ctk.CTkToplevel, width: int, height: int) -> None:
        self.update_idletasks()
        screen_width = max(1, self.winfo_screenwidth())
        screen_height = max(1, self.winfo_screenheight())
        parent_x = self.winfo_rootx()
        parent_y = self.winfo_rooty()
        parent_width = max(1, self.winfo_width())
        parent_height = max(1, self.winfo_height())
        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
        window.geometry(f"{width}x{height}+{x}+{y}")

    def register_file_drop_target(self, widget, callback) -> bool:
        if not self.native_file_drop_available or DND_FILES is None:
            return False
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", lambda event: self._handle_native_file_drop(event, callback))
        except Exception as exc:  # pragma: no cover - depends on TkDND runtime registration
            log.debug("Failed to register file drop target: %s", exc)
            return False
        return True

    def _handle_native_file_drop(self, event, callback):
        paths = [Path(value) for value in self.tk.splitlist(event.data) if value]
        callback(paths)
        return DND_COPY or getattr(event, "action", None)

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

    def dedicated_server_features_enabled(self) -> bool:
        return bool(self.preferences.dedicated_server_enabled)

    def target_apply_modes(self) -> dict[str, str]:
        return {
            TARGET_CLIENT: self.preferences.client_mod_apply_mode,
            TARGET_DEDICATED_SERVER: self.preferences.dedicated_server_mod_apply_mode,
        }

    def update_workshop_content_dir(self, path_text: str) -> None:
        self.paths.workshop_content_dir = path_from_setting(path_text)
        self.save_settings()

    def update_local_paths(
        self,
        *,
        client_root: str = "",
        dedicated_server_root: str = "",
        workshop_content_dir: str = "",
    ) -> None:
        self.paths.client_root = path_from_setting(client_root)
        self.paths.dedicated_server_root = path_from_setting(dedicated_server_root)
        self.paths.workshop_content_dir = path_from_setting(workshop_content_dir)
        if self.paths.dedicated_server_root:
            self.preferences.dedicated_server_enabled = True
        self.save_settings()

    def set_first_run_setup_completed(self, completed: bool = True) -> None:
        self.preferences.first_run_setup_completed = bool(completed)
        self.save_settings()

    def path_validation_summary(self) -> dict[str, str]:
        return {
            "client": _validation_label(self.paths.client_root, validate_client_root, "Conan client"),
            "dedicated": _validation_label(
                self.paths.dedicated_server_root,
                validate_dedicated_server_root,
                "Dedicated server",
            ),
            "workshop": _folder_validation_label(self.paths.workshop_content_dir, "Workshop content"),
        }

    def show_first_run_setup(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("First-Run Setup")
        self.center_window(window, 820, 460)
        window.minsize(720, 420)
        window.grid_columnconfigure(1, weight=1)

        client_var = ctk.StringVar(value=str(self.paths.client_root or ""))
        server_var = ctk.StringVar(value=str(self.paths.dedicated_server_root or ""))
        workshop_var = ctk.StringVar(value=str(self.paths.workshop_content_dir or ""))
        steamcmd_var = ctk.StringVar(value=self.preferences.steamcmd_path)
        use_server_var = tk.BooleanVar(value=self.dedicated_server_features_enabled())

        ctk.CTkLabel(
            window,
            text="Conan Exiles Enhanced Manager Setup",
            font=self.ui_font("title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(14, 4))
        ctk.CTkLabel(
            window,
            text="Set paths here once. You can change them later in Settings.",
            font=self.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 12))

        def browse_dir(variable, title: str) -> None:
            path = filedialog.askdirectory(title=title, parent=window)
            if path:
                variable.set(path)

        def browse_steamcmd() -> None:
            path = filedialog.askopenfilename(
                title="Select steamcmd.exe",
                filetypes=[("SteamCMD", "steamcmd.exe"), ("Executables", "*.exe"), ("All files", "*.*")],
                parent=window,
            )
            if path:
                steamcmd_var.set(path)

        rows = [
            ("Conan client root", client_var, lambda: browse_dir(client_var, "Select Conan Exiles folder")),
            ("Dedicated server root", server_var, lambda: browse_dir(server_var, "Select Conan Exiles Dedicated Server folder")),
            ("Workshop content 440900", workshop_var, lambda: browse_dir(workshop_var, "Select Workshop content\\440900 folder")),
            ("steamcmd.exe", steamcmd_var, browse_steamcmd),
        ]
        for offset, (label, variable, command) in enumerate(rows, start=2):
            ctk.CTkLabel(window, text=label, font=self.ui_font("body"), text_color="#b9aa92").grid(
                row=offset,
                column=0,
                sticky="w",
                padx=14,
                pady=5,
            )
            ctk.CTkEntry(
                window,
                textvariable=variable,
                font=self.ui_font("body"),
                fg_color="#101010",
                border_color="#3a3028",
                text_color="#f1e7d0",
            ).grid(row=offset, column=1, sticky="ew", padx=10, pady=5)
            ctk.CTkButton(
                window,
                text="Browse",
                width=90,
                height=self.ui_tokens.compact_button_height,
                font=self.ui_font("body"),
                fg_color="#3a3028",
                hover_color="#4a3c31",
                command=command,
            ).grid(row=offset, column=2, sticky="e", padx=(0, 14), pady=5)

        ctk.CTkSwitch(
            window,
            text="Use Dedicated Server features",
            variable=use_server_var,
            onvalue=True,
            offvalue=False,
            font=self.ui_font("body"),
            text_color="#f1e7d0",
            progress_color="#7d4429",
        ).grid(row=6, column=1, sticky="w", padx=10, pady=(8, 4))

        status_label = ctk.CTkLabel(
            window,
            text="No Conan files are written by this setup window.",
            font=self.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
            justify="left",
        )
        status_label.grid(row=7, column=0, columnspan=3, sticky="ew", padx=14, pady=(4, 12))

        def save_setup() -> None:
            client_root = path_from_setting(client_var.get())
            server_root = path_from_setting(server_var.get())
            if not validate_client_root(client_root):
                status_label.configure(
                    text="Conan client root is required and must contain ConanSandbox.exe or the Win64 shipping executable.",
                    text_color="#c98a2e",
                )
                return
            if use_server_var.get() and server_root and not validate_dedicated_server_root(server_root):
                status_label.configure(
                    text="Dedicated server root is not valid. Fix it, clear it, or turn off Dedicated Server features.",
                    text_color="#c98a2e",
                )
                return
            self.preferences.steamcmd_path = str(steamcmd_var.get() or "").strip()
            self.preferences.dedicated_server_enabled = bool(use_server_var.get())
            if not self.preferences.dedicated_server_enabled:
                server_var.set("")
            self.preferences.first_run_setup_completed = True
            self.preferences = self.preferences.normalized()
            self.update_local_paths(
                client_root=client_var.get(),
                dedicated_server_root=server_var.get(),
                workshop_content_dir=workshop_var.get(),
            )
            self.refresh_discovery()
            window.destroy()
            self.show_banner("success", "Setup saved. You can change paths later in Settings.")

        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=8, column=0, columnspan=3, sticky="e", padx=14, pady=(4, 14))
        ctk.CTkButton(
            controls,
            text="Skip For Now",
            width=120,
            height=self.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=lambda: (self.set_first_run_setup_completed(True), window.destroy()),
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Save Setup",
            width=130,
            height=self.ui_tokens.compact_button_height,
            fg_color="#7d4429",
            hover_color="#925333",
            command=save_setup,
        ).grid(row=0, column=1)
        window.transient(self)
        window.grab_set()

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
                known_workshop_content_dir=self.paths.workshop_content_dir,
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
        if hasattr(self, "notes_tab"):
            self.notes_tab.refresh()
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

    def backup_configs_and_saves_from_ui(self) -> None:
        records = self.backup_configs_and_saves()
        if records:
            self.notify_info("Backup Complete", f"Backed up {len(records)} config/save file(s).")
        else:
            self.notify_warning("Backup Complete", "No config or save database files were found to back up.")
        self._refresh_main_tabs()

    def open_client_root_folder(self) -> None:
        self.open_path_in_shell(self.paths.client_root)

    def open_dedicated_root_folder(self) -> None:
        self.open_path_in_shell(self.paths.dedicated_server_root)

    def open_dedicated_logs_folder(self) -> None:
        self.open_path_in_shell(self.paths.dedicated_server_log_dir)

    def open_workshop_content_folder(self) -> None:
        self.open_path_in_shell(self.paths.workshop_content_dir)

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
            mod_note_count=self.mod_notes.note_count(),
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

    def note_subjects(self, filter_value: str = "All"):
        self._ensure_workshop_services()
        subjects = subjects_for_mods(
            active_mods=self.active_mods,
            components=self.mod_library.list_components(),
            workshop_items=self.workshop_items,
        )
        return filter_note_subjects(subjects, self.mod_notes.list_notes(), filter_value)

    def note_for_key(self, key: str):
        return self.mod_notes.get(key)

    def note_text_for_key(self, key: str) -> str:
        note = self.mod_notes.get(key)
        return note.text if note else ""

    def note_text_for_active_entry(self, entry: ActiveModEntry) -> str:
        return self.note_text_for_key(note_key_for_active_entry(entry))

    def save_mod_note(self, subject, text: str) -> None:
        self.mod_notes.upsert(subject, text)
        self.last_action = f"Saved note for {subject.display_name}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("mod note", "saved", target=subject.key, details=subject.display_name)
        self._refresh_main_tabs()

    def clear_mod_note(self, key: str) -> None:
        cleared = self.mod_notes.clear(key)
        self.last_action = "Cleared mod note." if cleared else "No note text to clear."
        self.status_text = self.last_action
        self.show_banner("info", self.last_action)
        self._refresh_main_tabs()

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
            target_coverage=target_coverage or self.default_profile_coverage(),
            notes=notes,
        )
        self.named_mod_profiles = self.profile_store.list_mod_profiles()
        self.last_action = f"Saved mod profile {profile.name}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("profile save", "saved", target=", ".join(profile.target_coverage), details=profile.name)
        self._refresh_main_tabs()
        return profile

    def save_active_load_order_profile_from_ui(self, target: str = TARGET_BOTH) -> ModProfile | None:
        name = simpledialog.askstring(
            "Save Mod Load Order",
            "Load order name:",
            parent=self,
        )
        if not name:
            return None
        if target == TARGET_BOTH:
            coverage = self.default_profile_coverage()
        else:
            coverage = [target]
        profile = self.save_current_mod_profile(name, target_coverage=coverage)
        self.notify_info("Load Order Saved", f"Saved mod load order {profile.name}.")
        return profile

    def default_profile_coverage(self) -> list[str]:
        coverage = [TARGET_CLIENT]
        if self.dedicated_server_features_enabled():
            coverage.append(TARGET_DEDICATED_SERVER)
        return coverage

    def update_mod_profile_coverage(self, name: str, target_coverage: list[str], notes: str | None = None) -> None:
        if TARGET_DEDICATED_SERVER in target_coverage and not self.dedicated_server_features_enabled():
            self.notify_warning(
                "Dedicated Server Disabled",
                "This profile includes Dedicated Server coverage, but dedicated-server features are disabled.",
                popup=False,
            )
        try:
            profile = self.profile_store.update_mod_profile_metadata(
                name,
                target_coverage=target_coverage,
                notes=notes,
            )
        except ValueError as exc:
            self.notify_warning("Profile Update Failed", str(exc))
            return
        self.named_mod_profiles = self.profile_store.list_mod_profiles()
        self.last_action = f"Updated profile coverage for {profile.name}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("profile coverage", "updated", target=", ".join(profile.target_coverage), details=profile.name)
        self._refresh_main_tabs()

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

    def load_mod_profile(self, name: str) -> bool:
        profile = self.profile_store.get_mod_profile(name)
        if profile is None:
            self.notify_warning("Profile Missing", f"Profile not found: {name}", popup=False)
            return False
        self._ensure_workshop_services()
        warnings = profile_entry_warnings(profile.entries, self.workshop_items)
        self.active_mods = list(profile.entries)
        self.save_active_mods()
        self.last_action = f"Loaded mod profile {profile.name}."
        self.status_text = self.last_action
        if warnings:
            self.show_banner("warning", f"{self.last_action} {len(warnings)} warning(s); check Active Mods before applying.")
        else:
            self.show_banner("success", self.last_action)
        self.record_activity("profile load", "loaded", target=", ".join(profile.target_coverage), details=profile.name)
        self._refresh_main_tabs()
        return True

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

    def forget_library_rows(self, rows: list[tuple[str, str]]) -> int:
        component_ids = [value for kind, value in rows if kind == "component"]
        source_ids = [value for kind, value in rows if kind == "source"]
        workshop_ids = [value for kind, value in rows if kind == "workshop"]
        removed = self.mod_library.remove_components(component_ids)
        removed += self.mod_library.remove_sources(source_ids)
        if workshop_ids:
            removed += self.remove_workshop_cache_entries(workshop_ids, refresh=False)
        removed_component_ids = set(component_ids)
        removed_source_ids = set(source_ids)
        removed_workshop_ids = set(workshop_ids)
        before_active = len(self.active_mods)
        self.active_mods = [
            entry
            for entry in self.active_mods
            if entry.component_id not in removed_component_ids
            and entry.source_id not in removed_source_ids
            and entry.workshop_id not in removed_workshop_ids
        ]
        removed_active = before_active - len(self.active_mods)
        if removed_active:
            self.save_active_mods()
        self.last_action = (
            f"Forgot {removed} library/cache record(s) and removed {removed_active} matching active entr"
            f"{'y' if removed_active == 1 else 'ies'}. Files were not deleted."
        )
        self.status_text = self.last_action
        self.show_banner("success" if removed else "info", self.last_action)
        self.record_activity("library forget", "completed", target="library", details=self.last_action)
        self._refresh_main_tabs()
        return removed

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

    def set_active_mods_enabled(self, indices: list[int], enabled: bool) -> int:
        selected = selected_active_entries(self.active_mods, indices)
        if not selected:
            self.notify_warning("No Active Mods Selected", "Select one or more active mods first.", popup=False)
            return 0
        selected_ids = {id(entry) for entry in selected}
        for entry in self.active_mods:
            if id(entry) in selected_ids:
                entry.enabled = enabled
        self.save_active_mods()
        state = "enabled" if enabled else "disabled"
        self.last_action = f"{state.title()} {len(selected)} selected active mod(s)."
        self.status_text = self.last_action
        self.show_banner("info", self.last_action)
        self.record_activity("active mods bulk", state, target="active", details=f"{len(selected)} mod(s)")
        self._refresh_main_tabs()
        return len(selected)

    def remove_active_mods_at(self, indices: list[int]) -> int:
        valid = sorted({index for index in indices if 0 <= index < len(self.active_mods)}, reverse=True)
        if not valid:
            self.notify_warning("No Active Mods Selected", "Select one or more active mods first.", popup=False)
            return 0
        removed = []
        for index in valid:
            removed.append(self.active_mods.pop(index))
        self.save_active_mods()
        self.last_action = f"Removed {len(removed)} mod(s) from Active Load Order. Target files were not changed."
        self.status_text = self.last_action
        self.show_banner("info", self.last_action)
        self.record_activity("active mods remove", "removed", target="active", details=f"{len(removed)} mod(s)")
        self._refresh_main_tabs()
        return len(removed)

    def remove_duplicate_active_mods(self) -> int:
        seen: set[str] = set()
        kept: list[ActiveModEntry] = []
        removed = 0
        for entry in self.active_mods:
            key = _active_entry_identity(entry)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            kept.append(entry)
        if not removed:
            self.notify_info("No Duplicates", "No duplicate Active Load Order entries were found.")
            return 0
        self.active_mods = kept
        self.save_active_mods()
        self.last_action = f"Removed {removed} duplicate Active Load Order entr{'y' if removed == 1 else 'ies'}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("active mods dedupe", "completed", target="active", details=self.last_action)
        self._refresh_main_tabs()
        return removed

    def add_library_rows_to_active(self, rows: list[tuple[str, str]], *, insert_index: int | None = None) -> int:
        existing = {_active_entry_identity(active) for active in self.active_mods}
        entries: list[ActiveModEntry] = []
        for entry in self._active_entries_from_library_rows(rows, warn=False):
            entry_key = _active_entry_identity(entry)
            if entry_key in existing:
                continue
            existing.add(entry_key)
            entries.append(entry)
        if insert_index is None:
            self.active_mods.extend(entries)
            selected_index = len(self.active_mods) - 1 if entries else None
        else:
            target_index = max(0, min(int(insert_index), len(self.active_mods)))
            self.active_mods[target_index:target_index] = entries
            selected_index = target_index if entries else None
        added = len(entries)
        if added:
            self.save_active_mods()
        self.last_action = f"Added {added} selected library mod(s) to Active Load Order."
        self.status_text = self.last_action
        self.show_banner("success" if added else "info", self.last_action)
        if added:
            self.record_activity("active mods add", "added", target="active", details=f"{added} mod(s)")
        self._refresh_main_tabs(selected_mod_index=selected_index)
        return added

    def preview_sync_library_rows(self, target: str, rows: list[tuple[str, str]]) -> None:
        entries = self._active_entries_from_library_rows(rows, warn=True)
        self.preview_sync_entries(target, entries)

    def preview_sync_active_indices(self, target: str, indices: list[int]) -> None:
        self.preview_sync_entries(target, selected_active_entries(self.active_mods, indices))

    def preview_sync_entries(self, target: str, entries: list[ActiveModEntry]) -> None:
        if not entries:
            self.notify_warning("No Mods Selected", "Select one or more mods to install/sync.", popup=False)
            return
        plans = build_selected_sync_plans(
            self.paths,
            target,
            entries,
            target_apply_modes=self.target_apply_modes(),
        )
        self._show_apply_preview(plans)

    def preview_uninstall_active_indices(
        self,
        target: str,
        indices: list[int],
        *,
        quarantine_target_files: bool = False,
    ) -> None:
        entries = selected_active_entries(self.active_mods, indices)
        if not entries:
            self.notify_warning("No Active Mods Selected", "Select active mods to uninstall from the target.", popup=False)
            return
        plans = build_selected_uninstall_plans(
            self.paths,
            target,
            entries,
            target_apply_modes=self.target_apply_modes(),
        )
        self._show_selected_uninstall_preview(plans, quarantine_target_files=quarantine_target_files)

    def active_entry_target_labels(self, entry: ActiveModEntry) -> list[str]:
        return target_status_labels_for_entry(
            entry,
            client_mods_dir=self.paths.client_mods_dir,
            server_mods_dir=self.paths.dedicated_server_mods_dir if self.dedicated_server_features_enabled() else None,
            client_modlist_path=self.paths.client_modlist_path,
            server_modlist_path=(
                self.paths.dedicated_server_modlist_path if self.dedicated_server_features_enabled() else None
            ),
            target_apply_modes=self.target_apply_modes(),
        )

    def active_entry_target_states(self, entry: ActiveModEntry) -> dict[str, str]:
        states = {
            TARGET_CLIENT: target_install_state_for_entry(
                entry,
                mods_dir=self.paths.client_mods_dir,
                modlist_path=self.paths.client_modlist_path,
                apply_mode=self.preferences.client_mod_apply_mode,
            ),
        }
        if self.dedicated_server_features_enabled():
            states[TARGET_DEDICATED_SERVER] = target_install_state_for_entry(
                entry,
                mods_dir=self.paths.dedicated_server_mods_dir,
                modlist_path=self.paths.dedicated_server_modlist_path,
                apply_mode=self.preferences.dedicated_server_mod_apply_mode,
            )
        return states

    def open_path_in_shell(self, path: Path | None) -> None:
        if path is None:
            self.notify_warning("Path Missing", "No path is available for that item.", popup=False)
            return
        target = path if path.is_dir() else path.parent
        if not target.exists():
            self.notify_warning("Path Missing", f"Path does not exist yet:\n{target}", popup=False)
            return
        os.startfile(target)

    def copy_workshop_id(self, workshop_id: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(workshop_id)
        self.last_action = f"Copied Workshop ID {workshop_id}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)

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

    def refresh_workshop_cache(self) -> int:
        self._ensure_workshop_services()
        self.workshop_items = self.workshop.list_items()
        self.last_action = f"Refreshed {len(self.workshop_items)} cached Workshop item(s)."
        self.status_text = self.last_action
        self.show_banner("info", self.last_action)
        self._refresh_main_tabs()
        return len(self.workshop_items)

    def fetch_missing_workshop_metadata(self) -> int:
        self._ensure_workshop_services()
        ids = [
            item.workshop_id
            for item in self.workshop_items
            if item.workshop_id and not item.title and not item.display_name_override
        ]
        return self.fetch_workshop_metadata_for_ids(ids, action_label="Fetch Workshop titles")

    def refresh_selected_workshop_metadata(self, workshop_ids: list[str]) -> int:
        return self.fetch_workshop_metadata_for_ids(workshop_ids, action_label="Refresh Workshop metadata")

    def fetch_workshop_metadata_for_ids(self, workshop_ids: list[str], *, action_label: str = "Fetch Workshop metadata") -> int:
        self._ensure_workshop_services()
        ids = [workshop_id for workshop_id in dict.fromkeys(str(value).strip() for value in workshop_ids) if workshop_id]
        if not ids:
            self.notify_warning("No Workshop IDs", "Select or add Workshop IDs before fetching metadata.", popup=False)
            return 0
        try:
            metadata_items = fetch_workshop_metadata(ids)
        except WorkshopMetadataError as exc:
            self.last_action = f"{action_label} failed: {exc}"
            self.status_text = self.last_action
            self.show_banner("warning", self.last_action)
            self.record_activity("workshop metadata", "failed", target=", ".join(ids), details=str(exc))
            self._refresh_main_tabs()
            return 0
        self.workshop_items = self.workshop.merge_metadata(metadata_items)
        updated = self._update_generated_workshop_active_names(ids)
        self.last_action = f"{action_label}: updated {len(metadata_items)} Workshop item(s)."
        if updated:
            self.last_action += f" Refreshed {updated} active display name(s)."
        self.status_text = self.last_action
        self.show_banner("success" if metadata_items else "info", self.last_action)
        self.record_activity("workshop metadata", "completed", target=", ".join(ids), details=self.last_action)
        self._refresh_main_tabs()
        return len(metadata_items)

    def rename_workshop_display_name(self, workshop_id: str) -> bool:
        self._ensure_workshop_services()
        item = self.workshop_cache.get(workshop_id) if self.workshop_cache else None
        if item is None:
            self.notify_warning("Workshop Item Missing", "The selected Workshop item is not in the local cache.", popup=False)
            return False
        value = simpledialog.askstring(
            "Rename Workshop Display",
            "Display name (blank clears manual override):",
            initialvalue=item.display_name_override or workshop_display_name(item),
            parent=self,
        )
        if value is None:
            return False
        item.display_name_override = value.strip()
        self.workshop_items = self.workshop.merge_metadata([])
        if self.workshop_cache:
            self.workshop_cache.save(self.workshop_items)
        self._update_generated_workshop_active_names([workshop_id], force=True)
        self.last_action = f"Updated display name for Workshop {workshop_id}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self._refresh_main_tabs()
        return True

    def remove_workshop_cache_entries(self, workshop_ids: list[str], *, refresh: bool = True) -> int:
        self._ensure_workshop_services()
        ids = [str(value).strip() for value in workshop_ids if str(value).strip()]
        if not ids:
            self.notify_warning("No Workshop Items", "Select one or more Workshop cache entries first.", popup=False)
            return 0
        if not self.confirm_action(
            "bulk",
            "Forget Workshop Cache Entries",
            "Forget these Workshop cache entries?\n\n"
            + "\n".join(ids[:30])
            + ("\n..." if len(ids) > 30 else "")
            + "\n\nMatching Active Load Order entries will also be removed."
            + "\nSteam Workshop folders, SteamCMD files, and .pak files will not be deleted.",
        ):
            return 0
        removed = self.workshop.remove_ids(ids)
        id_set = set(ids)
        before_active = len(self.active_mods)
        self.active_mods = [entry for entry in self.active_mods if entry.workshop_id not in id_set]
        removed_active = before_active - len(self.active_mods)
        if removed_active:
            self.save_active_mods()
        self.workshop_items = self.workshop.list_items()
        self.last_action = (
            f"Removed {removed} Workshop cache entr{'y' if removed == 1 else 'ies'} and "
            f"{removed_active} matching active entr{'y' if removed_active == 1 else 'ies'}. Workshop files were not deleted."
        )
        self.status_text = self.last_action
        self.show_banner("success" if removed else "info", self.last_action)
        self.record_activity("workshop cache remove", "completed", target=", ".join(ids), details=self.last_action)
        if refresh:
            self._refresh_main_tabs()
        return removed

    def remove_all_workshop_cache_entries(self) -> int:
        self._ensure_workshop_services()
        return self.remove_workshop_cache_entries([item.workshop_id for item in self.workshop_items])

    def remove_missing_workshop_cache_entries(self) -> int:
        self._ensure_workshop_services()
        ids = [item.workshop_id for item in self.workshop_items if item.status == WORKSHOP_STATUS_MISSING]
        return self.remove_workshop_cache_entries(ids)

    def cancel_workshop_scan(self) -> None:
        self.workshop_scan_cancel_requested = True
        self.status_text = "Workshop scan cancel requested."
        self.show_banner("warning", self.status_text)

    def download_missing_workshop_items(self) -> None:
        self._ensure_workshop_services()
        self._start_workshop_steamcmd(missing_workshop_ids(self.workshop_items), action_label="Download Missing")

    def update_selected_workshop_item(self, workshop_id: str) -> None:
        self._start_workshop_steamcmd([workshop_id], action_label="Update Selected")

    def update_selected_workshop_items(self, workshop_ids: list[str]) -> None:
        self._start_workshop_steamcmd(workshop_ids, action_label="Update Selected")

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
        if not self._add_active_entry(entry, quiet=False):
            return False
        self.save_active_mods()
        self.last_action = f"Added Workshop {workshop_id} to Active Mods."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self._refresh_main_tabs()
        return True

    def _update_generated_workshop_active_names(self, workshop_ids: list[str], *, force: bool = False) -> int:
        self._ensure_workshop_services()
        ids = {str(value).strip() for value in workshop_ids if str(value).strip()}
        if not ids:
            return 0
        by_id = {item.workshop_id: item for item in self.workshop_items}
        changed = 0
        for entry in self.active_mods:
            if not entry.workshop_id or entry.workshop_id not in ids:
                continue
            item = by_id.get(entry.workshop_id)
            if item is None:
                continue
            new_name = workshop_display_name(item)
            if force or _active_workshop_name_is_generated(entry):
                if entry.display_name != new_name:
                    entry.display_name = new_name
                    changed += 1
        if changed:
            self.save_active_mods()
        return changed

    def _add_active_entry(self, entry: ActiveModEntry, *, quiet: bool) -> bool:
        entry_key = _active_entry_identity(entry)
        existing = {_active_entry_identity(active) for active in self.active_mods}
        if entry_key in existing:
            if not quiet:
                self.notify_info("Already Active", "That mod is already in Active Load Order.")
            return False
        self.active_mods.append(entry)
        return True

    def _active_entries_from_library_rows(self, rows: list[tuple[str, str]], *, warn: bool) -> list[ActiveModEntry]:
        self._ensure_workshop_services()
        entries: list[ActiveModEntry] = []
        warnings: list[str] = []
        for kind, value in rows:
            if kind == "component":
                component = self.mod_library.component_by_id(value)
                if component is None:
                    warnings.append(f"Library component missing: {value}")
                    continue
                entries.append(component_to_active_entry(component))
            elif kind == "workshop":
                item = self.workshop_cache.get(value) if self.workshop_cache else None
                if item is None:
                    warnings.append(f"Workshop item missing from cache: {value}")
                    continue
                if item.status != WORKSHOP_STATUS_DOWNLOADED:
                    warnings.append(f"Workshop {value} is not downloaded. Download/update it before target sync.")
                    continue
                if len(item.pak_paths) != 1:
                    warnings.append(f"Workshop {value} has {len(item.pak_paths)} pak file(s). Select a single pak/component first.")
                    continue
                entries.append(active_entry_from_workshop_item(item))
        if warn and warnings:
            self.notify_warning("Some Mods Need Attention", "\n".join(warnings), popup=False)
        return entries

    def link_active_indices_to_workshop_id(self, indices: list[int]) -> int:
        entries = selected_active_entries(self.active_mods, indices)
        if not entries:
            self.notify_warning("No Active Mods Selected", "Select one or more active mods to link.", popup=False)
            return 0
        raw_value = simpledialog.askstring("Link Workshop ID", "Workshop ID or URL:", parent=self)
        if not raw_value:
            return 0
        parsed = parse_workshop_ids(raw_value)
        if len(parsed.ids) != 1 or parsed.invalid_tokens:
            self.notify_warning(
                "Workshop ID Invalid",
                "Enter exactly one Steam Workshop ID or URL.",
                popup=False,
            )
            return 0
        self._ensure_workshop_services()
        workshop_id = parsed.ids[0]
        item = self.workshop_cache.get(workshop_id) if self.workshop_cache else None
        changed = 0
        for entry in entries:
            if entry.workshop_id == workshop_id:
                continue
            entry.workshop_id = workshop_id
            if item:
                entry.display_name = workshop_display_name(item)
            changed += 1
        if not changed:
            self.notify_info("Workshop Already Linked", f"Selected entries already link to Workshop {workshop_id}.")
            return 0
        self.save_active_mods()
        self.last_action = f"Linked {changed} active mod(s) to Workshop {workshop_id}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("workshop link", "completed", target=workshop_id, details=f"{changed} active mod(s)")
        self._refresh_main_tabs()
        return changed

    def rename_active_indices_display_name(self, indices: list[int]) -> int:
        entries = selected_active_entries(self.active_mods, indices)
        if not entries:
            self.notify_warning("No Active Mods Selected", "Select one active mod to rename.", popup=False)
            return 0
        if len(entries) > 1:
            self.notify_warning("Select One Mod", "Rename one active mod at a time.", popup=False)
            return 0
        entry = entries[0]
        value = simpledialog.askstring(
            "Rename Active Mod",
            "Display name (blank resets to source name):",
            initialvalue=entry.display_name or Path(entry.value).stem,
            parent=self,
        )
        if value is None:
            return 0
        entry.display_name = normalize_mod_display_name(value) if value.strip() else normalize_mod_display_name(Path(entry.value).stem)
        self.save_active_mods()
        self.last_action = f"Renamed active mod to {entry.display_name}."
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self._refresh_main_tabs()
        return 1

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

    def move_active_mods(self, indices: list[int], delta: int) -> list[int]:
        selected = {index for index in indices if 0 <= index < len(self.active_mods)}
        if not selected or delta == 0:
            return sorted(selected)
        if delta < 0:
            for index in range(1, len(self.active_mods)):
                if index in selected and index - 1 not in selected:
                    self.active_mods[index - 1], self.active_mods[index] = self.active_mods[index], self.active_mods[index - 1]
                    selected.remove(index)
                    selected.add(index - 1)
        else:
            for index in range(len(self.active_mods) - 2, -1, -1):
                if index in selected and index + 1 not in selected:
                    self.active_mods[index + 1], self.active_mods[index] = self.active_mods[index], self.active_mods[index + 1]
                    selected.remove(index)
                    selected.add(index + 1)
        self.save_active_mods()
        self.status_text = f"Moved {len(selected)} selected active mod(s)."
        self.show_banner("info", self.status_text)
        self._refresh_main_tabs()
        return sorted(selected)

    def move_active_mods_to_edge(self, indices: list[int], *, to_top: bool) -> list[int]:
        reordered, moved = move_items_to_edge(self.active_mods, indices, to_top=to_top)
        if not moved:
            return []
        self.active_mods = reordered
        self.save_active_mods()
        edge = "top" if to_top else "bottom"
        self.status_text = f"Moved {len(moved)} selected active mod(s) to the {edge}."
        self.show_banner("info", self.status_text)
        self._refresh_main_tabs()
        return moved

    def move_active_mods_to_index(self, indices: list[int], target_index: int) -> list[int]:
        reordered, moved = move_items_to_index(self.active_mods, indices, target_index)
        if not moved:
            return []
        self.active_mods = reordered
        self.save_active_mods()
        self.status_text = f"Moved {len(moved)} selected active mod(s)."
        self.show_banner("info", self.status_text)
        self._refresh_main_tabs()
        return moved

    def preview_apply_modlist(self, target: str) -> None:
        if not self.active_mods:
            self.notify_warning("No Active Mods", "Add or import mods before applying a modlist.")
            return
        plans = build_apply_plans(
            self.paths,
            target,
            self.active_mods,
            target_apply_modes=self.target_apply_modes(),
        )
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
        if not self.dedicated_server_features_enabled():
            enabled = len([entry for entry in self.active_mods if entry.enabled])
            return f"Client-only mode ({enabled} enabled mod(s))."
        return compare_client_server(self.paths).summary

    def dedicated_server_status(self) -> ServerProcessStatus:
        if not self.dedicated_server_features_enabled():
            return ServerProcessStatus(processes=[])
        return self.server_process.status()

    def dedicated_server_config(self) -> ServerConfigSnapshot:
        return read_server_config(self.paths)

    def dedicated_server_log_snapshot(self) -> ServerLogSnapshot:
        return read_server_log_snapshot(self.paths)

    def preview_server_config_edit(self, edit: ServerConfigEdit) -> None:
        if not self.dedicated_server_features_enabled():
            self.notify_warning(
                "Dedicated Server Disabled",
                "Enable dedicated-server features in Settings before editing dedicated server config.",
                popup=False,
            )
            return
        plan = build_server_config_edit_plan(
            self.paths,
            edit,
            process_status=self.dedicated_server_status(),
        )
        self._show_server_config_preview(plan)

    def launch_client_game_from_ui(self) -> None:
        result = launch_client_game(self.paths)
        self.last_action = result.message
        self.status_text = result.message
        self.record_activity("client launch", "requested" if result.started else "not started", target="client", details=result.message)
        self.show_banner("success" if result.started else "warning", result.message)
        if result.started:
            self.notify_info("Conan Exiles Launch Requested", f"{result.message}\nPID: {result.pid}")
        else:
            self.notify_warning("Conan Exiles Not Started", result.message)
        self._refresh_main_tabs()

    def launch_dedicated_server_from_ui(self) -> None:
        if not self.dedicated_server_features_enabled():
            self.notify_warning(
                "Dedicated Server Disabled",
                "Dedicated-server features are disabled. Enable them in Settings before starting a server.",
                popup=False,
            )
            return
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
        self.center_window(window, 920, 660)
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
        self.center_window(window, 860, 620)
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
        self.center_window(window, 900, 660)
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
        self.center_window(window, 860, 620)
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
        self.load_mod_profile(profile.name)
        window.destroy()

    def _show_snapshot_restore_preview(self, record: BackupRecord) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Preview Snapshot Restore")
        self.center_window(window, 780, 520)
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
        self.center_window(window, 860, 620)
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

    def _show_selected_uninstall_preview(
        self,
        plans: list[ModlistTargetPlan],
        *,
        quarantine_target_files: bool = False,
    ) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Preview Target Uninstall")
        self.center_window(window, 900, 660)
        window.minsize(760, 500)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            window,
            text="Preview Target Uninstall",
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
        text.insert("1.0", preview_selected_uninstall_text(plans, quarantine_target_files=quarantine_target_files))
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
            command=lambda: self._apply_selected_uninstall(plans, window, quarantine_target_files=False),
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Apply + Quarantine Copies",
            width=210,
            height=self.ui_tokens.compact_button_height,
            fg_color="#5d3424",
            hover_color="#70402c",
            command=lambda: self._apply_selected_uninstall(plans, window, quarantine_target_files=True),
        ).grid(row=0, column=2)
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

    def _apply_selected_uninstall(
        self,
        plans: list[ModlistTargetPlan],
        window: ctk.CTkToplevel,
        *,
        quarantine_target_files: bool,
    ) -> None:
        if quarantine_target_files and not self.confirm_action(
            "destructive",
            "Quarantine Target Copies",
            "Move manager-owned target copies out of the selected target Mods folder?\n\n"
            "Original imports, app library files, external links, and Steam Workshop cache folders are not touched.",
        ):
            return
        result = apply_selected_uninstall_plans(
            plans,
            self.backup,
            quarantine_target_files=quarantine_target_files,
        )
        if any(plan.target == TARGET_DEDICATED_SERVER for plan in plans) and result.written_paths:
            self.server_runtime.mark_restart_recommended("Dedicated Server modlist changed.")
        labels = [plan.label for plan in plans if plan.modlist_path != Path()]
        self.last_action = (
            f"Uninstalled selected mods from {', '.join(labels)}; "
            f"wrote {len(result.written_paths)} modlist file(s), "
            f"quarantined {len(result.quarantined_paths)} target file(s), "
            f"created {len(result.backup_ids)} backup(s)."
        )
        self.status_text = self.last_action
        self.show_banner("success", self.last_action)
        self.record_activity("target uninstall", "completed", target=", ".join(labels), details=self.last_action)
        window.destroy()
        if result.warnings:
            self.notify_warning("Target Uninstall Applied With Warnings", self.last_action + "\n\n" + "\n".join(result.warnings))
        else:
            self.notify_info("Target Uninstall Applied", self.last_action)
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
        if hasattr(self, "notes_tab"):
            self.notes_tab.refresh()
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


def _active_entry_identity(entry: ActiveModEntry) -> str:
    if entry.workshop_id:
        return f"workshop:{entry.workshop_id}"
    if entry.component_id:
        return f"component:{entry.component_id}"
    return f"value:{_entry_key(entry.value)}"


def _active_workshop_name_is_generated(entry: ActiveModEntry) -> bool:
    current = normalize_mod_display_name(entry.display_name or "")
    if not current:
        return True
    generated = {
        normalize_mod_display_name(f"Workshop {entry.workshop_id}"),
        normalize_mod_display_name(Path(entry.value).stem),
    }
    return current in generated


def _preview_text(plans: list[ModlistTargetPlan]) -> str:
    sections: list[str] = []
    for plan in plans:
        current = [entry.value for entry in plan.current_entries]
        proposed = plan.proposed_values
        lines = [
            f"Target: {plan.label}",
            f"modlist.txt: {plan.modlist_path if str(plan.modlist_path) != '.' else 'not configured'}",
            f"Mods folder: {plan.mods_dir if str(plan.mods_dir) != '.' else 'not configured'}",
            f"Apply mode: {'copy/sync to target Mods folder' if plan.apply_mode == APPLY_MODE_COPY else 'write source paths directly'}",
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
        elif plan.apply_mode == APPLY_MODE_SOURCE:
            lines.extend(["", "Target file copies:", "(none; modlist.txt will reference source paths directly)"])
        sections.append("\n".join(lines))
    return "\n\n" + ("-" * 72 + "\n\n").join(sections)


def _validation_label(path: Path | None, validator, label: str) -> str:
    if not path:
        return f"{label}: not set"
    return f"{label}: valid" if validator(path) else f"{label}: invalid or not found"


def _folder_validation_label(path: Path | None, label: str) -> str:
    if not path:
        return f"{label}: not set"
    return f"{label}: exists" if path.is_dir() else f"{label}: not found"


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
