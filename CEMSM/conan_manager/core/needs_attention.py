"""Dashboard attention summary generation."""
from __future__ import annotations

from ..models.app_paths import ConanAppPaths
from ..models.modlist import ActiveModEntry
from ..models.server import ServerRuntimeState
from ..models.workshop import WorkshopItem
from .compatibility import EnhancedStatus, old_mod_warnings


def build_needs_attention(
    paths: ConanAppPaths,
    *,
    server_runtime: ServerRuntimeState | None = None,
    active_mods: list[ActiveModEntry] | None = None,
    workshop_items: list[WorkshopItem] | None = None,
    enhanced_status: EnhancedStatus | None = None,
) -> list[str]:
    items: list[str] = []
    if not paths.client_root:
        items.append("Conan Exiles Enhanced client was not detected.")
    if not paths.dedicated_server_root:
        items.append("Conan Exiles Dedicated Server was not detected.")
    if paths.client_root and not paths.client_config_dir:
        items.append("Client config folder path could not be resolved.")
    if paths.dedicated_server_root and not paths.dedicated_server_config_dir:
        items.append("Dedicated server config folder path could not be resolved.")
    if paths.workshop_content_dir and not paths.workshop_content_dir.is_dir():
        items.append("Workshop content folder is expected but does not exist yet.")
    if paths.client_root and not paths.client_save_databases():
        items.append("No client save database files found.")
    if paths.dedicated_server_root and not paths.dedicated_server_save_databases():
        items.append("No dedicated server save database files found.")
    if server_runtime and server_runtime.restart_recommended:
        items.append(f"Dedicated Server restart recommended: {server_runtime.restart_reason}")
    if enhanced_status and enhanced_status.label == "Unknown":
        items.append("Enhanced/Legacy status could not be determined from local files yet.")
    items.extend(old_mod_warnings(active_mods or [], workshop_items or [])[:5])
    return items
