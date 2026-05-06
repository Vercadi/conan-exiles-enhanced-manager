from __future__ import annotations

from pathlib import Path

from conan_manager.core.backup_manager import BackupManager
from conan_manager.core.discovery import discover_all
from conan_manager.core.modlist_service import (
    active_entry_from_pak,
    apply_modlist_plans,
    build_apply_plans,
    compare_client_server,
    compare_modlists,
    missing_entries,
    read_modlist,
    restore_latest_modlist,
)
from conan_manager.models.modlist import TARGET_BOTH, TARGET_CLIENT, ActiveModEntry

from .conftest import create_fake_conan_library


def test_read_modlist_preserves_order_and_resolves_relative_paths(tmp_path) -> None:
    mods_dir = tmp_path / "Mods"
    mods_dir.mkdir()
    first = mods_dir / "First.pak"
    second = mods_dir / "Second.pak"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    modlist = mods_dir / "modlist.txt"
    modlist.write_text("First.pak\nSecond.pak\n", encoding="utf-8")

    entries = read_modlist(modlist)

    assert [entry.value for entry in entries] == ["First.pak", "Second.pak"]
    assert [entry.exists for entry in entries] == [True, True]
    assert entries[0].resolved_path == first


def test_missing_pak_detection_handles_missing_full_paths(tmp_path) -> None:
    existing = tmp_path / "Existing.pak"
    missing = tmp_path / "Missing.pak"
    existing.write_bytes(b"pak")

    entries = [active_entry_from_pak(existing), active_entry_from_pak(missing)]

    assert missing_entries(entries) == [str(missing)]


def test_apply_creates_mods_folder_lazily_and_writes_modlist(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak")

    assert paths.client_mods_dir is not None
    assert not paths.client_mods_dir.exists()

    plans = build_apply_plans(paths, TARGET_CLIENT, [active_entry_from_pak(pak)])
    result = apply_modlist_plans(plans, backup)

    assert paths.client_mods_dir.is_dir()
    assert paths.client_modlist_path is not None
    assert (paths.client_mods_dir / "Example.pak").is_file()
    assert paths.client_modlist_path.read_text(encoding="utf-8") == "Example.pak\n"
    assert result.written_paths == [paths.client_modlist_path]
    assert result.copied_paths == [paths.client_mods_dir / "Example.pak"]
    assert result.backup_ids == []


def test_apply_backs_up_existing_modlist_before_overwrite(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    first = tmp_path / "First.pak"
    second = tmp_path / "Second.pak"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    apply_modlist_plans(build_apply_plans(paths, TARGET_CLIENT, [active_entry_from_pak(first)]), backup)
    result = apply_modlist_plans(build_apply_plans(paths, TARGET_CLIENT, [active_entry_from_pak(second)]), backup)

    assert len(result.backup_ids) == 1
    backups = backup.list_backups(category="modlists", source_path=paths.client_modlist_path)
    assert len(backups) == 1
    assert Path(backups[0].backup_path).read_text(encoding="utf-8") == "First.pak\n"


def test_restore_latest_modlist_restores_previous_content(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    first = tmp_path / "First.pak"
    second = tmp_path / "Second.pak"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    apply_modlist_plans(build_apply_plans(paths, TARGET_CLIENT, [active_entry_from_pak(first)]), backup)
    apply_modlist_plans(build_apply_plans(paths, TARGET_CLIENT, [active_entry_from_pak(second)]), backup)
    restored = restore_latest_modlist(backup, paths.client_modlist_path)

    assert restored is not None
    assert paths.client_modlist_path.read_text(encoding="utf-8") == "First.pak\n"


def test_client_server_parity_detects_order_mismatch(tmp_path) -> None:
    client = [ActiveModEntry("A.pak"), ActiveModEntry("B.pak")]
    server = [ActiveModEntry("B.pak"), ActiveModEntry("A.pak")]
    parity = compare_modlists(
        [entry for entry in _as_read_entries(client)],
        [entry for entry in _as_read_entries(server)],
    )

    assert not parity.matches
    assert parity.order_mismatch


def test_apply_to_both_then_compare_client_server_matches(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    pak = tmp_path / "Shared.pak"
    pak.write_bytes(b"pak")

    apply_modlist_plans(build_apply_plans(paths, TARGET_BOTH, [active_entry_from_pak(pak)]), backup)
    parity = compare_client_server(paths)

    assert parity.matches
    assert parity.client_count == 1
    assert parity.server_count == 1


def test_apply_copies_companion_files_and_writes_only_pak(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    pak = tmp_path / "Companion.pak"
    ucas = tmp_path / "Companion.ucas"
    utoc = tmp_path / "Companion.utoc"
    pak.write_bytes(b"pak")
    ucas.write_bytes(b"ucas")
    utoc.write_bytes(b"utoc")
    entry = ActiveModEntry(str(pak), companion_paths=[str(ucas), str(utoc)])

    result = apply_modlist_plans(build_apply_plans(paths, TARGET_CLIENT, [entry]), backup)

    assert paths.client_modlist_path.read_text(encoding="utf-8") == "Companion.pak\n"
    assert (paths.client_mods_dir / "Companion.pak").read_bytes() == b"pak"
    assert (paths.client_mods_dir / "Companion.ucas").read_bytes() == b"ucas"
    assert (paths.client_mods_dir / "Companion.utoc").read_bytes() == b"utoc"
    assert len(result.copied_paths) == 3


def test_apply_backs_up_same_name_target_pak_before_overwrite(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    paths.client_mods_dir.mkdir(parents=True)
    existing = paths.client_mods_dir / "Overwrite.pak"
    existing.write_bytes(b"old")
    source = tmp_path / "Overwrite.pak"
    source.write_bytes(b"new")

    result = apply_modlist_plans(build_apply_plans(paths, TARGET_CLIENT, [active_entry_from_pak(source)]), backup)

    assert existing.read_bytes() == b"new"
    mod_backups = backup.list_backups(category="mods", source_path=existing)
    assert len(mod_backups) == 1
    assert Path(mod_backups[0].backup_path).read_bytes() == b"old"
    assert any(backup_id.startswith("mods_") for backup_id in result.backup_ids)


def test_apply_skips_copy_when_source_is_already_target_file(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    paths.client_mods_dir.mkdir(parents=True)
    source = paths.client_mods_dir / "AlreadyThere.pak"
    source.write_bytes(b"pak")

    result = apply_modlist_plans(build_apply_plans(paths, TARGET_CLIENT, [active_entry_from_pak(source)]), backup)

    assert paths.client_modlist_path.read_text(encoding="utf-8") == "AlreadyThere.pak\n"
    assert result.copied_paths == []
    assert backup.list_backups(category="mods", source_path=source) == []


def test_disabled_entries_are_not_written(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    enabled = tmp_path / "Enabled.pak"
    disabled = tmp_path / "Disabled.pak"
    enabled.write_bytes(b"enabled")
    disabled.write_bytes(b"disabled")

    apply_modlist_plans(
        build_apply_plans(
            paths,
            TARGET_CLIENT,
            [ActiveModEntry(str(enabled)), ActiveModEntry(str(disabled), enabled=False)],
        ),
        backup,
    )

    assert paths.client_modlist_path.read_text(encoding="utf-8") == "Enabled.pak\n"
    assert not (paths.client_mods_dir / "Disabled.pak").exists()


def _as_read_entries(entries: list[ActiveModEntry]):
    from conan_manager.models.modlist import ModlistEntry

    return [ModlistEntry(value=entry.value) for entry in entries]
