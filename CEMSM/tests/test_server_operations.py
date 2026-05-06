from __future__ import annotations

from conan_manager.core.discovery import discover_all
from conan_manager.core.server_config import read_server_config
from conan_manager.core.server_launcher import build_launch_plan, split_launch_args
from conan_manager.core.server_logs import filter_mod_related_lines, read_server_log_snapshot
from conan_manager.core.server_process import ServerProcessService
from conan_manager.models.server import ProcessInfo, ServerRuntimeState

from .conftest import create_fake_conan_library


def test_process_detection_uses_injected_process_list() -> None:
    service = ServerProcessService(
        process_provider=lambda: [
            ProcessInfo(pid=1, name="notepad.exe"),
            ProcessInfo(pid=2, name="ConanSandboxServer-Win64-Shipping.exe"),
        ]
    )

    status = service.status()

    assert status.running
    assert status.processes[0].pid == 2
    assert "ConanSandboxServer-Win64-Shipping.exe" in status.summary


def test_server_config_parser_extracts_core_fields(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    paths.dedicated_server_settings.write_text(
        "\n".join(
            [
                "[ServerSettings]",
                "ServerName=The Exiled Test",
                "ServerPassword=secret",
                "AdminPassword=admin-secret",
                "MaxPlayers=40",
                "PVPEnabled=True",
                "IsBattlEyeEnabled=False",
                "ServerModList=111,222",
            ]
        ),
        encoding="utf-8",
    )
    paths.dedicated_server_engine_ini.write_text(
        "\n".join(
            [
                "[OnlineSubsystemSteam]",
                "QueryPort=27016",
                "[RConPlugin]",
                "RconEnabled=True",
                "RconPort=25576",
                "RconPassword=rcon-secret",
            ]
        ),
        encoding="utf-8",
    )

    config = read_server_config(paths)

    assert config.server_name == "The Exiled Test"
    assert config.server_password_set
    assert config.admin_password_set
    assert config.max_players == "40"
    assert config.pvp_enabled == "True"
    assert config.battleye_enabled == "False"
    assert config.server_mod_list == "111,222"
    assert config.query_port == "27016"
    assert config.rcon_enabled == "True"
    assert config.rcon_port == "25576"
    assert config.rcon_password_set


def test_log_tail_and_filter_behavior(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    log_file = paths.dedicated_server_log_dir / "ConanSandbox.log"
    log_file.write_text(
        "\n".join(
            [
                "ordinary line",
                "LogModManager: Starting mod runtime module.",
                "LogPakFile: Display: Mounted Pak file example.pak",
                "LogTemp: Warning: something happened",
            ]
        ),
        encoding="utf-8",
    )

    snapshot = read_server_log_snapshot(paths, tail_lines=10)

    assert snapshot.log_path == log_file
    assert "ordinary line" in snapshot.tail
    assert "LogModManager" in snapshot.filtered
    assert "Mounted Pak" in snapshot.filtered
    assert "Warning" in snapshot.filtered
    assert "ordinary line" not in snapshot.filtered


def test_filter_mod_related_lines_is_case_insensitive() -> None:
    filtered = filter_mod_related_lines("one\nlogmodmanager: ok\ntwo\nerror: bad")

    assert filtered.splitlines() == ["logmodmanager: ok", "error: bad"]


def test_launch_command_builder_uses_root_executable_and_args(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])

    plan = build_launch_plan(paths, "-Messaging -log")

    assert plan is not None
    assert plan.executable == paths.dedicated_server_root / "ConanSandboxServer.exe"
    assert plan.args == ["-Messaging", "-log"]
    assert plan.command == [str(plan.executable), "-Messaging", "-log"]


def test_split_launch_args_handles_empty_string() -> None:
    assert split_launch_args("") == []


def test_restart_required_state_marker() -> None:
    state = ServerRuntimeState()

    state.mark_restart_recommended("Dedicated Server modlist changed.")
    assert state.restart_recommended
    assert state.restart_reason == "Dedicated Server modlist changed."

    state.clear_restart_recommended()
    assert not state.restart_recommended
    assert state.restart_reason == ""
