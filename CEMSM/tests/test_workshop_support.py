from __future__ import annotations

from pathlib import Path

from conan_manager.core.modlist_service import active_entry_from_workshop_item
from conan_manager.core.workshop_cache import WorkshopCache
from conan_manager.core.workshop_parser import UINT64_MAX, parse_workshop_ids
from conan_manager.core.workshop_service import WorkshopService
from conan_manager.models.workshop import (
    WORKSHOP_STATUS_DOWNLOADED,
    WORKSHOP_STATUS_DUPLICATE_PAK,
    WORKSHOP_STATUS_MISSING,
    WORKSHOP_STATUS_NO_PAK,
    WorkshopItem,
)


def test_parse_workshop_url_and_bare_id_preserves_order() -> None:
    result = parse_workshop_ids(
        "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890123456789\n987654321"
    )

    assert result.ids == ["1234567890123456789", "987654321"]
    assert result.invalid_tokens == []


def test_parse_workshop_ids_is_uint64_safe_and_reports_invalid_tokens() -> None:
    too_large = str(UINT64_MAX + 1)
    result = parse_workshop_ids(f"{UINT64_MAX}, {too_large}, abc")

    assert result.ids == [str(UINT64_MAX)]
    assert result.invalid_tokens == [too_large, "abc"]


def test_parse_comma_newline_and_semicolon_input() -> None:
    result = parse_workshop_ids("111,222\n333;444")

    assert result.ids == ["111", "222", "333", "444"]


def test_workshop_scan_reports_downloaded_no_pak_duplicate_and_missing(tmp_path) -> None:
    workshop_root = tmp_path / "steamapps" / "workshop" / "content" / "440900"
    downloaded = workshop_root / "111"
    no_pak = workshop_root / "222"
    duplicate = workshop_root / "333"
    downloaded.mkdir(parents=True)
    no_pak.mkdir(parents=True)
    duplicate.mkdir(parents=True)
    (downloaded / "Example.pak").write_bytes(b"pak")
    (no_pak / "readme.txt").write_text("no pak", encoding="utf-8")
    (duplicate / "One.pak").write_bytes(b"one")
    (duplicate / "Two.pak").write_bytes(b"two")

    cache = WorkshopCache(tmp_path / "data")
    service = WorkshopService(cache)
    service.add_ids(["444"], workshop_root)
    items = {item.workshop_id: item for item in service.scan(workshop_root)}

    assert items["111"].status == WORKSHOP_STATUS_DOWNLOADED
    assert items["111"].pak_paths == [downloaded / "Example.pak"]
    assert items["222"].status == WORKSHOP_STATUS_NO_PAK
    assert items["333"].status == WORKSHOP_STATUS_DUPLICATE_PAK
    assert items["444"].status == WORKSHOP_STATUS_MISSING


def test_workshop_cache_roundtrip_preserves_metadata(tmp_path) -> None:
    cache = WorkshopCache(tmp_path / "data")
    item = WorkshopItem(
        workshop_id="123",
        title="A Test Mod",
        folder_path=tmp_path / "123",
        pak_paths=[tmp_path / "123" / "Test.pak"],
        local_size=99,
        modified_time=123.5,
        status=WORKSHOP_STATUS_DOWNLOADED,
        compatibility_note="Enhanced compatibility unknown",
    )

    cache.save([item])
    loaded = WorkshopCache(tmp_path / "data").list_items()

    assert len(loaded) == 1
    assert loaded[0].workshop_id == "123"
    assert loaded[0].title == "A Test Mod"
    assert loaded[0].pak_paths == [tmp_path / "123" / "Test.pak"]


def test_downloaded_workshop_item_can_become_active_mod_entry(tmp_path) -> None:
    pak = tmp_path / "SomeWorkshopMod.pak"
    pak.write_bytes(b"pak")
    item = WorkshopItem(
        workshop_id="999",
        title="Some Workshop Mod",
        pak_paths=[pak],
        status=WORKSHOP_STATUS_DOWNLOADED,
    )

    entry = active_entry_from_workshop_item(item)

    assert entry.value == str(pak)
    assert entry.display_name == "Some Workshop Mod"
    assert entry.source_type == "workshop"
    assert entry.workshop_id == "999"
