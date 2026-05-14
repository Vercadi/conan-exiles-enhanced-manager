from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from conan_manager.core.local_mod_library import (
    LocalModLibraryStore,
    component_to_active_entry,
    duplicate_component_keys,
    group_pak_files,
    normalize_mod_display_name,
    target_sync_labels,
)


def test_raw_pak_import_creates_managed_copy(tmp_path) -> None:
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak")
    store = LocalModLibraryStore(tmp_path / "data")

    imported = store.import_pak_files([pak])

    assert len(imported) == 1
    component = imported[0]
    assert component.primary_pak_path.is_file()
    assert component.primary_pak_path != pak
    assert component.primary_pak_path.read_bytes() == b"pak"
    assert component.primary_file.original_path == pak
    assert store.list_components()[0].component_id == component.component_id


def test_pak_companion_grouping_uses_selected_and_sibling_files(tmp_path) -> None:
    pak = tmp_path / "Example.pak"
    ucas = tmp_path / "Example.ucas"
    utoc = tmp_path / "Example.utoc"
    pak.write_bytes(b"pak")
    ucas.write_bytes(b"ucas")
    utoc.write_bytes(b"utoc")

    groups = group_pak_files([pak, ucas])

    assert len(groups) == 1
    assert groups[0].pak_path == pak
    assert sorted(path.suffix for path in groups[0].companion_paths) == [".ucas", ".utoc"]


def test_pak_companion_grouping_keeps_selected_same_stem_sidecar(tmp_path) -> None:
    pak = tmp_path / "Example.pak"
    sig = tmp_path / "Example.sig"
    pak.write_bytes(b"pak")
    sig.write_bytes(b"sig")

    groups = group_pak_files([pak, sig])

    assert groups[0].companion_paths == [sig]


def test_external_link_mode_keeps_original_paths(tmp_path) -> None:
    pak = tmp_path / "Linked.pak"
    pak.write_bytes(b"pak")
    store = LocalModLibraryStore(tmp_path / "data")

    imported = store.import_pak_files([pak], link_external=True)

    assert imported[0].primary_pak_path == pak
    assert imported[0].source_type == "external_link"


def test_external_link_status_detects_missing_file(tmp_path) -> None:
    pak = tmp_path / "Linked.pak"
    pak.write_bytes(b"pak")
    store = LocalModLibraryStore(tmp_path / "data")
    component = store.import_pak_files([pak], link_external=True)[0]

    pak.unlink()

    assert component.status == "missing_source"


def test_zip_inspection_one_mod_archive(tmp_path) -> None:
    archive_path = tmp_path / "one.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Example.pak", b"pak")
        archive.writestr("Example.ucas", b"ucas")
        archive.writestr("Example.sig", b"sig")
    store = LocalModLibraryStore(tmp_path / "data")

    inspection = store.inspect_archive(archive_path)
    imported = store.import_archive(archive_path)

    assert len(inspection.components) == 1
    assert inspection.components[0].companion_members == ["Example.ucas", "Example.sig"]
    assert len(imported) == 1
    assert imported[0].primary_pak_path.is_file()
    assert imported[0].companion_paths[0].suffix == ".ucas"


def test_display_name_normalization_strips_nexus_suffix_and_camel_case() -> None:
    name = normalize_mod_display_name("HeroicThralls v2.0-150-2-0-1777953219.zip")

    assert name == "Heroic Thralls v2.0"


def test_archive_import_stores_normalized_source_name(tmp_path) -> None:
    archive_path = tmp_path / "HeroicThralls v2.0-150-2-0-1777953219.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("HeroicThralls_v2.0/HeroicThralls.pak", b"pak")
    store = LocalModLibraryStore(tmp_path / "data")

    store.import_archive(archive_path)

    assert store.list_sources()[0].display_name == "Heroic Thralls v2.0"


def test_zip_inspection_multi_mod_archive(tmp_path) -> None:
    archive_path = tmp_path / "multi.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("First/First.pak", b"first")
        archive.writestr("Second/Second.pak", b"second")
    store = LocalModLibraryStore(tmp_path / "data")

    inspection = store.inspect_archive(archive_path)
    imported = store.import_archive(archive_path)

    assert inspection.ambiguous
    assert [component.display_name for component in inspection.components] == ["First", "Second"]
    assert len(imported) == 2
    assert len(store.list_sources()[0].component_ids) == 2


def test_variant_archive_requires_one_choice(tmp_path) -> None:
    archive_path = tmp_path / "variants.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Options/Fast/Fast.pak", b"fast")
        archive.writestr("Options/Slow/Slow.pak", b"slow")
    store = LocalModLibraryStore(tmp_path / "data")
    inspection = store.inspect_archive(archive_path)

    assert inspection.requires_variant_choice
    with pytest.raises(ValueError):
        store.import_archive(archive_path)

    imported = store.import_archive(archive_path, selected_component_ids=[inspection.components[0].component_id])

    assert len(imported) == 1
    assert imported[0].display_name == "Fast"


def test_duplicate_detection_by_hash(tmp_path) -> None:
    first = tmp_path / "First.pak"
    second = tmp_path / "Second.pak"
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    store = LocalModLibraryStore(tmp_path / "data")

    components = store.import_pak_files([first, second])

    assert duplicate_component_keys(components) == set()
    assert len(components) == 2


def test_reimporting_same_pak_does_not_create_duplicate_record(tmp_path) -> None:
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak")
    store = LocalModLibraryStore(tmp_path / "data")

    first = store.import_pak_files([pak])
    second = store.import_pak_files([pak])

    assert len(first) == 1
    assert second == []
    assert len(store.list_components()) == 1


def test_remove_library_component_forgets_record_without_deleting_managed_file(tmp_path) -> None:
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak")
    store = LocalModLibraryStore(tmp_path / "data")
    component = store.import_pak_files([pak])[0]
    managed = component.primary_pak_path

    removed = store.remove_components([component.component_id])

    assert removed == 1
    assert store.list_components() == []
    assert store.list_sources() == []
    assert managed.is_file()


def test_component_to_active_entry_preserves_companion_paths(tmp_path) -> None:
    pak = tmp_path / "Example.pak"
    ucas = tmp_path / "Example.ucas"
    pak.write_bytes(b"pak")
    ucas.write_bytes(b"ucas")
    store = LocalModLibraryStore(tmp_path / "data")
    component = store.import_pak_files([pak, ucas])[0]

    entry = component_to_active_entry(component)

    assert entry.component_id == component.component_id
    assert entry.requires_target_copy
    assert entry.companion_paths == [str(component.companion_paths[0])]


def test_target_sync_status_detects_matching_target_copy(tmp_path) -> None:
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak")
    store = LocalModLibraryStore(tmp_path / "data")
    component = store.import_pak_files([pak])[0]
    client_mods = tmp_path / "Client" / "ConanSandbox" / "Mods"
    client_mods.mkdir(parents=True)
    (client_mods / "Example.pak").write_bytes(b"pak")

    labels = target_sync_labels(component, client_mods_dir=client_mods)

    assert labels == ["Synced to Client"]
