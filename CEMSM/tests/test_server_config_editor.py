from __future__ import annotations

from pathlib import Path

from conan_manager.core.backup_manager import BackupManager
from conan_manager.core.discovery import discover_all
from conan_manager.core.server_config_editor import (
    IniDocument,
    ServerConfigEdit,
    apply_server_config_edit_plan,
    build_server_config_edit_plan,
    config_preview_text,
)
from conan_manager.core.support_diagnostics import redact_sensitive_text
from conan_manager.models.server import ProcessInfo, ServerProcessStatus

from .conftest import create_fake_conan_library


def test_ini_document_roundtrip_preserves_comments_unknown_keys_and_order() -> None:
    text = "\n".join(
        [
            "; header",
            "[ServerSettings]",
            "UnknownKey=KeepMe",
            "# another comment",
            "ServerName=Original",
            "",
            "[Other]",
            "Value=1",
            "",
        ]
    )

    document = IniDocument.from_text(text)

    assert document.to_text() == text
    assert document.get("ServerSettings", "UnknownKey") == "KeepMe"


def test_focused_key_update_preserves_unrelated_content() -> None:
    text = "\n".join(
        [
            "; header",
            "[ServerSettings]",
            "UnknownKey=KeepMe",
            "ServerName=Original ; inline",
            "[Other]",
            "Value=1",
        ]
    )
    document = IniDocument.from_text(text)

    document.set("ServerSettings", "ServerName", "Updated")
    rendered = document.to_text()

    assert "; header" in rendered
    assert "UnknownKey=KeepMe" in rendered
    assert "ServerName=Updated ; inline" in rendered
    assert "[Other]\nValue=1" in rendered


def test_config_diff_generation(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])

    plan = build_server_config_edit_plan(paths, ServerConfigEdit(server_name="Diff Test"))

    assert "ServerSettings.ini (current)" in plan.diff_text
    assert "+ServerName=Diff Test" in plan.diff_text
    assert "ServerSettings.ini" in config_preview_text(plan)


def test_apply_config_plan_backs_up_before_write(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")

    plan = build_server_config_edit_plan(paths, ServerConfigEdit(server_name="Backup Test"))
    result = apply_server_config_edit_plan(plan, backup)

    assert paths.dedicated_server_settings.read_text(encoding="utf-8").count("ServerName=Backup Test") == 1
    assert result.written_paths == [paths.dedicated_server_settings]
    assert len(result.backup_records) == 1
    assert Path(result.backup_records[0].backup_path).is_file()


def test_password_unchanged_vs_cleared_behavior(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    paths.dedicated_server_settings.write_text(
        "[ServerSettings]\nServerPassword=secret\nAdminPassword=admin\n",
        encoding="utf-8",
    )

    unchanged = build_server_config_edit_plan(paths, ServerConfigEdit(server_name="Name Only"))
    assert "ServerPassword=secret" in unchanged.changed_plans[0].proposed_text
    assert "AdminPassword=admin" in unchanged.changed_plans[0].proposed_text

    cleared = build_server_config_edit_plan(paths, ServerConfigEdit(clear_server_password=True))
    assert "ServerPassword=\n" in cleared.changed_plans[0].proposed_text
    assert "AdminPassword=admin" in cleared.changed_plans[0].proposed_text


def test_running_server_warning_plan(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    running = ServerProcessStatus(
        running=True,
        processes=[ProcessInfo(pid=99, name="ConanSandboxServer.exe")],
    )

    plan = build_server_config_edit_plan(paths, ServerConfigEdit(max_players="30"), process_status=running)

    assert plan.running_server
    assert any("running" in warning.casefold() for warning in plan.warnings)
    assert "WARNING" in config_preview_text(plan)


def test_diagnostics_and_activity_password_redaction() -> None:
    text = "AdminPassword=secret\nRconPassword=rcon-secret\nServerPassword=server-secret"

    redacted = redact_sensitive_text(text)

    assert "secret" not in redacted
    assert "AdminPassword=<redacted>" in redacted
    assert "RconPassword=<redacted>" in redacted
    assert "ServerPassword=<redacted>" in redacted


def test_server_mod_list_display_only_by_default(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    paths.dedicated_server_settings.write_text(
        "[ServerSettings]\nServerModList=111,222\n",
        encoding="utf-8",
    )

    plan = build_server_config_edit_plan(paths, ServerConfigEdit(server_mod_list="333,444"))

    assert not plan.has_changes
    assert any("ServerModList was not changed" in warning for warning in plan.warnings)


def test_server_mod_list_can_mirror_when_explicit(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])

    plan = build_server_config_edit_plan(
        paths,
        ServerConfigEdit(server_mod_list="333,444", mirror_server_mod_list=True),
    )

    assert "ServerModList=333,444" in plan.changed_plans[0].proposed_text


def test_motd_update_uses_existing_message_key(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    paths.dedicated_server_settings.write_text(
        "[ServerSettings]\nServerMessageOfTheDay=Old\n",
        encoding="utf-8",
    )

    plan = build_server_config_edit_plan(paths, ServerConfigEdit(motd="New message"))

    lines = plan.changed_plans[0].proposed_text.splitlines()
    assert "ServerMessageOfTheDay=New message" in lines
    assert "MessageOfTheDay=New message" not in lines
