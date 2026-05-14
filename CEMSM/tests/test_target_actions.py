from __future__ import annotations

from pathlib import Path

from conan_manager.core.backup_manager import BackupManager
from conan_manager.core.discovery import discover_all
from conan_manager.core.modlist_service import (
    active_entry_from_pak,
    active_entry_from_workshop_item,
    apply_modlist_plans,
    apply_selected_uninstall_plans,
    build_selected_sync_plans,
    build_selected_uninstall_plans,
    preview_selected_uninstall_text,
    read_modlist,
    target_install_state_for_entry,
    target_install_state_label,
)
from conan_manager.core.target_actions import (
    ROW_ACTIVE,
    ROW_LIBRARY_COMPONENT,
    ROW_LIBRARY_WORKSHOP,
    classify_dropped_mod_files,
    context_menu_actions,
    invert_indices,
    move_items_to_edge,
    move_items_to_index,
    next_first_letter_index,
    selected_active_entries,
)
from conan_manager.core.vanilla_restore import apply_vanilla_restore, build_vanilla_restore_plans
from conan_manager.models.modlist import TARGET_BOTH, TARGET_CLIENT, TARGET_DEDICATED_SERVER, ActiveModEntry
from conan_manager.models.workshop import WORKSHOP_STATUS_DOWNLOADED, WorkshopItem

from .conftest import create_fake_conan_library


def test_multi_select_helpers_preserve_active_order() -> None:
    entries = [ActiveModEntry("A.pak"), ActiveModEntry("B.pak"), ActiveModEntry("C.pak")]

    selected = selected_active_entries(entries, [2, 0, 0])

    assert [entry.value for entry in selected] == ["A.pak", "C.pak"]
    assert invert_indices(4, [1, 3]) == [0, 2]


def test_first_letter_navigation_wraps_from_current_row() -> None:
    labels = ["Advanced Gliders", "Heroic Thralls", "Hosav UI", "Improved Quality"]

    assert next_first_letter_index(labels, "h", start=0) == 1
    assert next_first_letter_index(labels, "h", start=1) == 2
    assert next_first_letter_index(labels, "a", start=2) == 0
    assert next_first_letter_index(labels, "z", start=0) is None


def test_context_menu_actions_route_by_row_kind() -> None:
    assert "sync_client" in context_menu_actions(ROW_LIBRARY_COMPONENT)
    assert "download_update" in context_menu_actions(ROW_LIBRARY_WORKSHOP)
    assert "uninstall_server" in context_menu_actions(ROW_ACTIVE)


def test_move_items_to_edge_preserves_selected_order() -> None:
    values = ["A", "B", "C", "D", "E"]

    top_values, top_indices = move_items_to_edge(values, [3, 1], to_top=True)
    bottom_values, bottom_indices = move_items_to_edge(values, [3, 1], to_top=False)

    assert top_values == ["B", "D", "A", "C", "E"]
    assert top_indices == [0, 1]
    assert bottom_values == ["A", "C", "E", "B", "D"]
    assert bottom_indices == [3, 4]


def test_move_items_to_index_accounts_for_removed_selected_items() -> None:
    values = ["A", "B", "C", "D", "E"]

    moved_values, moved_indices = move_items_to_index(values, [1, 3], 4)

    assert moved_values == ["A", "C", "B", "D", "E"]
    assert moved_indices == [2, 3]


def test_dropped_mod_file_classification_preserves_supported_groups() -> None:
    grouped = classify_dropped_mod_files(
        [
            Path("Example.pak"),
            Path("Example.ucas"),
            Path("Archive.zip"),
            Path("modlist.txt"),
            Path("notes.txt"),
        ]
    )

    assert grouped.pak_files == [Path("Example.pak"), Path("Example.ucas")]
    assert grouped.archive_files == [Path("Archive.zip")]
    assert grouped.modlist_files == [Path("modlist.txt")]
    assert grouped.ignored_files == [Path("notes.txt")]


def test_selected_sync_preserves_existing_target_entries_and_copies_selected(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    existing = tmp_path / "Existing.pak"
    selected = tmp_path / "Selected.pak"
    existing.write_bytes(b"existing")
    selected.write_bytes(b"selected")
    apply_modlist_plans(build_selected_sync_plans(paths, TARGET_CLIENT, [active_entry_from_pak(existing)]), backup)

    plans = build_selected_sync_plans(paths, TARGET_CLIENT, [active_entry_from_pak(selected)])
    result = apply_modlist_plans(plans, backup)

    assert paths.client_modlist_path.read_text(encoding="utf-8") == "Existing.pak\nSelected.pak\n"
    assert (paths.client_mods_dir / "Selected.pak").read_bytes() == b"selected"
    assert result.copied_paths == [paths.client_mods_dir / "Selected.pak"]


def test_selected_workshop_sync_preserves_workshop_cache(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    workshop_pak = steamapps / "workshop" / "content" / "440900" / "111" / "WorkshopMod.pak"
    workshop_pak.parent.mkdir(parents=True, exist_ok=True)
    workshop_pak.write_bytes(b"workshop")
    item = WorkshopItem(workshop_id="111", pak_paths=[workshop_pak], status=WORKSHOP_STATUS_DOWNLOADED)

    plans = build_selected_sync_plans(paths, TARGET_DEDICATED_SERVER, [active_entry_from_workshop_item(item)])
    apply_modlist_plans(plans, backup)

    assert workshop_pak.is_file()
    assert (paths.dedicated_server_mods_dir / "WorkshopMod.pak").read_bytes() == b"workshop"
    assert paths.dedicated_server_modlist_path.read_text(encoding="utf-8") == "WorkshopMod.pak\n"


def test_target_install_state_reports_synced_and_not_in_order(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    source = tmp_path / "AdvancedGliders.pak"
    source.write_bytes(b"pak")
    entry = active_entry_from_pak(source)
    apply_modlist_plans(build_selected_sync_plans(paths, TARGET_CLIENT, [entry]), backup)

    client_state = target_install_state_for_entry(
        entry,
        mods_dir=paths.client_mods_dir,
        modlist_path=paths.client_modlist_path,
    )
    server_state = target_install_state_for_entry(
        entry,
        mods_dir=paths.dedicated_server_mods_dir,
        modlist_path=paths.dedicated_server_modlist_path,
    )

    assert client_state == "synced"
    assert target_install_state_label("Client", client_state) == "Client: synced"
    assert server_state == "not_in_order"


def test_uninstall_selected_generates_diff_and_backs_up_without_deleting_pak(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    keep = tmp_path / "Keep.pak"
    remove = tmp_path / "Remove.pak"
    keep.write_bytes(b"keep")
    remove.write_bytes(b"remove")
    apply_modlist_plans(
        build_selected_sync_plans(paths, TARGET_CLIENT, [active_entry_from_pak(keep), active_entry_from_pak(remove)]),
        backup,
    )

    plans = build_selected_uninstall_plans(paths, TARGET_CLIENT, [active_entry_from_pak(remove)])
    preview = preview_selected_uninstall_text(plans)
    result = apply_selected_uninstall_plans(plans, backup)

    assert "-Remove.pak" in preview
    assert paths.client_modlist_path.read_text(encoding="utf-8") == "Keep.pak\n"
    assert (paths.client_mods_dir / "Remove.pak").is_file()
    assert backup.list_backups(category="modlists", source_path=paths.client_modlist_path)
    assert len(result.backup_ids) == 1


def test_optional_quarantine_moves_only_target_copy_not_source(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    source = tmp_path / "QuarantineMe.pak"
    source.write_bytes(b"source")
    entry = active_entry_from_pak(source)
    apply_modlist_plans(build_selected_sync_plans(paths, TARGET_CLIENT, [entry]), backup)

    plans = build_selected_uninstall_plans(paths, TARGET_CLIENT, [entry])
    result = apply_selected_uninstall_plans(plans, backup, quarantine_target_files=True)

    assert source.is_file()
    assert not (paths.client_mods_dir / "QuarantineMe.pak").exists()
    assert len(result.quarantined_paths) == 1
    assert result.quarantined_paths[0].read_bytes() == b"source"


def test_restore_vanilla_target_both_writes_empty_modlists_without_deleting_paks(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak")
    apply_modlist_plans(build_selected_sync_plans(paths, TARGET_BOTH, [active_entry_from_pak(pak)]), backup)

    result = apply_vanilla_restore(build_vanilla_restore_plans(paths, TARGET_BOTH), backup)

    assert pak.is_file()
    assert read_modlist(paths.client_modlist_path) == []
    assert read_modlist(paths.dedicated_server_modlist_path) == []
    assert len(result.backup_ids) == 2
