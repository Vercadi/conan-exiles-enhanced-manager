from __future__ import annotations

import inspect

from conan_manager.core.mod_notes_store import (
    ModNotesStore,
    filter_note_subjects,
    note_key_for_active_entry,
    subjects_for_mods,
)
from conan_manager.core.size_formatting import format_bytes
from conan_manager.models.local_mod_library import ModComponent, ModFile, SOURCE_LOCAL_FILES
from conan_manager.models.modlist import ActiveModEntry
from conan_manager.models.workshop import WorkshopItem
from conan_manager.ui.app_window import AppWindow
from conan_manager.ui.tabs.active_mods_tab import FILTER_CHOICES
from conan_manager.ui.tabs.settings_tab import SettingsTab


def test_size_formatter_uses_readable_units() -> None:
    assert format_bytes(None) == "unknown"
    assert format_bytes(0) == "0 B"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1536) == "1.50 KB"
    assert format_bytes(5 * 1024 * 1024) == "5.00 MB"


def test_notes_store_roundtrip_and_subject_filters(tmp_path) -> None:
    store = ModNotesStore(tmp_path)
    entry = ActiveModEntry("C:/Mods/AdvancedGliders.pak", display_name="Advanced Gliders", workshop_id="3720667122")
    component = ModComponent(
        component_id="mod_1",
        source_id="src_1",
        display_name="Local Mod",
        source_type=SOURCE_LOCAL_FILES,
        primary_file=ModFile(path=tmp_path / "Local.pak"),
    )
    workshop = WorkshopItem(workshop_id="3720667122", title="Enhanced Gliders")
    subjects = subjects_for_mods(active_mods=[entry], components=[component], workshop_items=[workshop])
    subject = next(item for item in subjects if item.key == "workshop:3720667122")

    store.upsert(subject, "Admin command: DataCmd Example")
    loaded = ModNotesStore(tmp_path)

    assert loaded.get("workshop:3720667122").text == "Admin command: DataCmd Example"
    assert note_key_for_active_entry(entry) == "workshop:3720667122"
    assert [item.key for item in filter_note_subjects(subjects, loaded.list_notes(), "Has Notes")] == [
        "workshop:3720667122"
    ]
    assert any(item.key == "workshop:3720667122" for item in filter_note_subjects(subjects, loaded.list_notes(), "In Active Load Order"))


def test_existing_active_and_component_notes_migrate_once(tmp_path) -> None:
    store = ModNotesStore(tmp_path)
    active = ActiveModEntry("A.pak", display_name="A", notes="Active note")
    component = ModComponent(
        component_id="mod_1",
        source_id="src_1",
        display_name="Component",
        source_type=SOURCE_LOCAL_FILES,
        primary_file=ModFile(path=tmp_path / "Component.pak"),
        notes="Component note",
    )

    first = store.migrate_existing_notes(active_mods=[active], components=[component], workshop_items=[])
    second = store.migrate_existing_notes(active_mods=[active], components=[component], workshop_items=[])

    assert first == 2
    assert second == 0
    assert store.get("path:a.pak").text == "Active note"
    assert store.get("component:mod_1").text == "Component note"


def test_library_inactive_filter_is_available() -> None:
    assert "Inactive / Not Active" in FILTER_CHOICES


def test_settings_tab_no_longer_builds_duplicate_workshop_card() -> None:
    source = inspect.getsource(SettingsTab._build)

    assert '"Steam Workshop"' not in source
    assert "Workshop content 440900" in source


def test_main_tab_refresh_includes_notes_tab() -> None:
    source = inspect.getsource(AppWindow._refresh_main_tabs)

    assert 'hasattr(self, "notes_tab")' in source
    assert "self.notes_tab.refresh()" in source
