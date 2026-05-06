from __future__ import annotations

import os
from datetime import UTC, datetime

from conan_manager.core.compatibility import (
    ENHANCED_LAUNCH_WINDOW,
    detect_enhanced_status,
    old_mod_warnings,
)
from conan_manager.core.discovery import discover_all
from conan_manager.core.lazy_tabs import LazyTabController
from conan_manager.core.list_formatting import format_active_mod_row
from conan_manager.core.needs_attention import build_needs_attention
from conan_manager.core.profile_diff import render_profile_modlist_diff
from conan_manager.core.startup import STARTUP_STEPS, startup_message
from conan_manager.models.app_paths import ConanAppPaths
from conan_manager.models.modlist import ActiveModEntry
from conan_manager.models.ui_state import BANNER_ERROR, BANNER_SUCCESS, banner
from conan_manager.models.workshop import WorkshopItem

from .conftest import create_fake_conan_library


def test_lazy_tab_controller_constructs_once() -> None:
    calls: list[str] = []
    controller = LazyTabController({"Workshop": lambda: calls.append("Workshop") or "tab"})

    first = controller.ensure("Workshop")
    second = controller.ensure("Workshop")

    assert first == "tab"
    assert second == "tab"
    assert calls == ["Workshop"]
    assert controller.is_constructed("Workshop")


def test_startup_messages_include_deferred_discovery_step() -> None:
    keys = [step.key for step in STARTUP_STEPS]

    assert keys.index("dashboard") < keys.index("discovery")
    assert startup_message("discovery") == "Discovering Steam and Conan paths..."
    assert startup_message("custom") == "custom"


def test_needs_attention_summary_uses_paths_and_enhanced_status() -> None:
    items = build_needs_attention(ConanAppPaths())

    assert "Conan Exiles Enhanced client was not detected." in items
    assert "Conan Exiles Dedicated Server was not detected." in items


def test_enhanced_detection_uses_build_ids(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])

    status = detect_enhanced_status(paths)

    assert status.label == "Enhanced / UE5 likely"
    assert "Steam build" in status.summary


def test_old_mod_warning_helper_uses_file_and_workshop_modified_time(tmp_path) -> None:
    old_pak = tmp_path / "OldMod.pak"
    old_pak.write_bytes(b"pak")
    old_ts = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    os.utime(old_pak, (old_ts, old_ts))
    workshop = WorkshopItem(workshop_id="123", modified_time=old_ts)

    warnings = old_mod_warnings([ActiveModEntry(str(old_pak))], [workshop], cutoff=ENHANCED_LAUNCH_WINDOW)

    assert any("OldMod.pak" in warning for warning in warnings)
    assert any("Workshop 123" in warning for warning in warnings)


def test_profile_diff_text_generation() -> None:
    diff = render_profile_modlist_diff([ActiveModEntry("A.pak")], [ActiveModEntry("B.pak")])

    assert "--- current active mods" in diff
    assert "+++ profile mods" in diff
    assert "-A.pak" in diff
    assert "+B.pak" in diff


def test_banner_state_helper_normalizes_kind_and_colors() -> None:
    success = banner(BANNER_SUCCESS, "Done")
    error = banner(BANNER_ERROR, "Failed")
    fallback = banner("odd", "Info")

    assert success.visible
    assert success.colors != error.colors
    assert fallback.kind == "info"


def test_large_active_mod_row_formatting_is_stable() -> None:
    entry = ActiveModEntry("C:/" + "very_long_folder/" * 30 + "Example.pak", display_name="Example")
    row = format_active_mod_row(512, entry, missing=True, max_value_length=90)

    assert row.startswith("512. [!]")
    assert "Example" in row
    assert len(row) < 150


def test_disabled_active_mod_row_is_marked_without_missing_flag() -> None:
    entry = ActiveModEntry("Example.pak", display_name="Example", enabled=False)

    row = format_active_mod_row(1, entry, missing=True)

    assert "[off]" in row
