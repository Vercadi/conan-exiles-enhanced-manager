from __future__ import annotations

from conan_manager.core.discovery import discover_all, validate_client_root, validate_dedicated_server_root
from conan_manager.models.app_paths import path_from_setting

from .conftest import create_fake_conan_library


def test_discovery_finds_client_server_and_workshop(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)

    paths = discover_all(extra_steamapps_dirs=[steamapps])

    assert paths.client_root is not None
    assert paths.dedicated_server_root is not None
    assert paths.client_manifest is not None
    assert paths.client_manifest.buildid == "23086684"
    assert paths.dedicated_server_manifest is not None
    assert paths.dedicated_server_manifest.buildid == "23086292"
    assert paths.workshop_content_dir is not None
    assert paths.workshop_content_dir.is_dir()
    assert len(paths.client_save_databases()) == 1
    assert len(paths.dedicated_server_save_databases()) == 1


def test_discovery_preserves_manually_configured_workshop_path(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    custom_workshop = tmp_path / "ManualSteam" / "steamapps" / "workshop" / "content" / "440900"

    paths = discover_all(extra_steamapps_dirs=[steamapps], known_workshop_content_dir=custom_workshop)

    assert paths.workshop_content_dir == custom_workshop


def test_clean_install_does_not_require_mods_folder(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])

    assert paths.client_mods_dir is not None
    assert not paths.client_mods_dir.exists()
    assert paths.dedicated_server_mods_dir is not None
    assert not paths.dedicated_server_mods_dir.exists()
    assert validate_client_root(paths.client_root)
    assert validate_dedicated_server_root(paths.dedicated_server_root)


def test_path_settings_treat_null_strings_as_unset() -> None:
    assert path_from_setting("") is None
    assert path_from_setting("null") is None
    assert path_from_setting("None") is None
