from __future__ import annotations

from pathlib import Path

from conan_manager.core.steamcmd_workshop import (
    build_workshop_download_command,
    detect_steamcmd_path,
    downloaded_workshop_ids,
    missing_workshop_ids,
    parse_steamcmd_progress,
    run_workshop_download,
    steamcmd_workshop_root,
    validate_steamcmd_path,
)
from conan_manager.core.workshop_cache import WorkshopCache
from conan_manager.core.workshop_service import WorkshopService
from conan_manager.models.workshop import (
    WORKSHOP_STATUS_DOWNLOADED,
    WORKSHOP_STATUS_MISSING,
    WorkshopItem,
)


def test_steamcmd_path_validation_and_detection(tmp_path) -> None:
    steamcmd = tmp_path / "steamcmd" / "steamcmd.exe"
    steamcmd.parent.mkdir()
    steamcmd.write_text("", encoding="utf-8")

    assert validate_steamcmd_path(steamcmd).ok
    assert not validate_steamcmd_path(tmp_path / "not-steam.exe").ok
    assert detect_steamcmd_path(tmp_path).name == "steamcmd.exe"
    assert steamcmd_workshop_root(steamcmd) == steamcmd.parent / "steamapps" / "workshop" / "content" / "440900"


def test_workshop_download_command_uses_anonymous_login() -> None:
    command = build_workshop_download_command(Path("C:/steamcmd/steamcmd.exe"), ["111", "222"])

    assert command[:3] == ["C:\\steamcmd\\steamcmd.exe", "+login", "anonymous"] or command[:3] == [
        "C:/steamcmd/steamcmd.exe",
        "+login",
        "anonymous",
    ]
    assert command.count("+workshop_download_item") == 2
    assert "440900" in command
    assert command[-1] == "+quit"


def test_workshop_download_command_never_contains_plaintext_password() -> None:
    command = build_workshop_download_command(
        Path("steamcmd.exe"),
        ["111"],
        username="user@example.com",
    )

    assert "+login" in command
    assert "user@example.com" in command
    assert "password" not in " ".join(command).casefold()
    assert "secret" not in " ".join(command).casefold()


def test_fake_steamcmd_runner_success_and_failure(tmp_path) -> None:
    steamcmd = tmp_path / "steamcmd.exe"
    steamcmd.write_text("", encoding="utf-8")
    progress = []

    def ok_runner(command, *, cwd=None, progress_callback=None, cancel_event=None):
        from conan_manager.core.steamcmd_workshop import SteamCmdRunResult

        if progress_callback:
            progress_callback(parse_steamcmd_progress("Success. Downloaded item 111"))
        return SteamCmdRunResult(command=command, returncode=0, output_lines=["Success. Downloaded item 111"])

    def fail_runner(command, *, cwd=None, progress_callback=None, cancel_event=None):
        from conan_manager.core.steamcmd_workshop import SteamCmdRunResult

        return SteamCmdRunResult(command=command, returncode=1, output_lines=["ERROR! Download item 111 failed"])

    ok = run_workshop_download(steamcmd, ["111"], runner=ok_runner, progress_callback=progress.append)
    failed = run_workshop_download(steamcmd, ["111"], runner=fail_runner)

    assert ok.ok
    assert progress[0].kind == "success"
    assert not failed.ok
    assert "ERROR" in failed.output_text


def test_progress_log_parsing_extracts_status_and_id() -> None:
    success = parse_steamcmd_progress("Success. Downloaded item 1234567890")
    failed = parse_steamcmd_progress("ERROR! Download item 987654321 failed")
    progress = parse_steamcmd_progress("Update state 61%")

    assert success.kind == "success"
    assert success.workshop_id == "1234567890"
    assert failed.kind == "error"
    assert failed.workshop_id == "987654321"
    assert progress.kind == "progress"


def test_workshop_cache_refresh_after_fake_download_scan_roots(tmp_path) -> None:
    steamcmd_root = tmp_path / "steamcmd" / "steamapps" / "workshop" / "content" / "440900"
    item_dir = steamcmd_root / "111"
    item_dir.mkdir(parents=True)
    (item_dir / "Downloaded.pak").write_bytes(b"pak")
    service = WorkshopService(WorkshopCache(tmp_path / "data"))
    service.add_ids(["111"], None)

    items = {item.workshop_id: item for item in service.scan_roots([steamcmd_root])}

    assert items["111"].status == WORKSHOP_STATUS_DOWNLOADED
    assert items["111"].pak_paths == [item_dir / "Downloaded.pak"]


def test_download_missing_selects_only_missing_items() -> None:
    items = [
        WorkshopItem(workshop_id="111", status=WORKSHOP_STATUS_MISSING),
        WorkshopItem(workshop_id="222", status=WORKSHOP_STATUS_DOWNLOADED),
    ]

    assert missing_workshop_ids(items) == ["111"]


def test_update_all_selects_downloaded_items_only() -> None:
    items = [
        WorkshopItem(workshop_id="111", status=WORKSHOP_STATUS_MISSING),
        WorkshopItem(workshop_id="222", status=WORKSHOP_STATUS_DOWNLOADED),
    ]

    assert downloaded_workshop_ids(items) == ["222"]
