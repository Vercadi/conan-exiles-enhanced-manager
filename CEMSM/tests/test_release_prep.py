from __future__ import annotations

from pathlib import Path

from conan_manager.core.release_guidance import (
    first_run_guidance,
    steamcmd_setup_guidance,
    steamcmd_may_need_account,
    workshop_download_failure_summary,
)
from conan_manager.core.project_links import GITHUB_REPO, GITHUB_URL, KOFI_URL, PATREON_URL
from conan_manager.core.update_checker import (
    ReleaseAsset,
    is_newer_version,
    pick_preferred_asset,
    release_info_from_api,
)
from conan_manager.models.app_paths import ConanAppPaths
from conan_manager.models.app_preferences import AppPreferences


def test_preferences_roundtrip_release_settings() -> None:
    preferences = AppPreferences(
        ui_size="large",
        dedicated_server_launch_args="-Messaging -log",
        confirmation_mode="none",
        show_result_popups=False,
        auto_check_updates=True,
        steamcmd_path="C:/steamcmd/steamcmd.exe",
        steamcmd_username="steam-user",
    )

    loaded = AppPreferences.from_dict(preferences.to_dict())

    assert loaded.ui_size == "large"
    assert loaded.confirmation_mode == "none"
    assert loaded.show_result_popups is False
    assert loaded.auto_check_updates is True
    assert loaded.steamcmd_path == "C:/steamcmd/steamcmd.exe"
    assert loaded.steamcmd_username == "steam-user"


def test_preferences_normalize_invalid_release_settings() -> None:
    preferences = AppPreferences(ui_size="tiny", confirmation_mode="everything").normalized()

    assert preferences.ui_size == "default"
    assert preferences.confirmation_mode == "destructive_only"


def test_update_checker_version_comparison() -> None:
    assert is_newer_version("v0.8.1", "0.8.0")
    assert is_newer_version("1.0.0", "0.9.9")
    assert not is_newer_version("0.8.0", "0.8.0")
    assert not is_newer_version("0.7.9", "0.8.0")
    assert not is_newer_version("preview", "0.8.0")


def test_update_checker_release_api_parsing_and_asset_choice() -> None:
    release = release_info_from_api(
        {
            "tag_name": "v0.8.2",
            "html_url": "https://example.invalid/releases/v0.8.2",
            "assets": [
                {"name": "checksums.txt", "browser_download_url": "https://example.invalid/checksums.txt"},
                {"name": "ConanManager.zip", "browser_download_url": "https://example.invalid/app.zip", "size": 42},
            ],
        }
    )

    assert release.version == "0.8.2"
    assert release.preferred_asset is not None
    assert release.preferred_asset.name == "ConanManager.zip"


def test_update_checker_ignores_checksum_assets() -> None:
    asset = pick_preferred_asset(
        [
            ReleaseAsset("release.sha256", "https://example.invalid/release.sha256"),
            ReleaseAsset("portable.exe", "https://example.invalid/portable.exe"),
        ]
    )

    assert asset is not None
    assert asset.name == "portable.exe"


def test_public_project_links_are_conan_specific() -> None:
    assert GITHUB_REPO == "Vercadi/conan-exiles-enhanced-manager"
    assert GITHUB_URL.endswith("/conan-exiles-enhanced-manager")
    assert "ko-fi.com/vercadi" in KOFI_URL
    assert "Vercadi" in PATREON_URL


def test_readme_and_changelog_cover_release_candidate_features() -> None:
    root = Path(__file__).resolve().parents[2]
    readme = (root / "README.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "SteamCMD Setup" in readme
    assert "Workshop downloads" in readme
    assert "Safety Model" in readme
    assert "Screenshots" in readme
    assert "v1.1.0" in changelog
    assert "v1.0.0" in changelog


def test_build_scripts_and_spec_exclude_runtime_data() -> None:
    root = Path(__file__).resolve().parents[1]
    build_script = (root / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    export_script = (root / "scripts" / "prepare_public_export.ps1").read_text(encoding="utf-8")
    spec = (root / "conan_exiles_enhanced_manager.spec").read_text(encoding="utf-8")

    assert "PyInstaller" in build_script
    assert "compileall" in build_script
    assert "pytest" in build_script
    assert "docs/" in spec
    assert "steamcmd" in spec
    assert "Implementation docs under docs/ are intentionally excluded." in export_script
    assert '"data", "backups", "logs", "steamcmd", "tmp", "build", "dist"' in export_script
    assert "Remove-Item -Recurse -Force" in export_script
    assert '$_.Extension -in @(".pyc", ".pyo")' in export_script


def test_public_export_root_files_exist_and_dev_docs_are_excluded() -> None:
    root = Path(__file__).resolve().parents[2]

    assert (root / "LICENSE").is_file()
    assert (root / ".gitignore").is_file()
    assert (root / "PRIVACY_POLICY.md").is_file()
    assert (root / "README.md").is_file()
    assert (root / "CHANGELOG.md").is_file()
    export_script = (root / "CEMSM" / "scripts" / "prepare_public_export.ps1").read_text(encoding="utf-8")
    assert 'Join-Path $RepoRoot "docs"' not in export_script


def test_first_run_guidance_and_workshop_failure_summary() -> None:
    messages = first_run_guidance(ConanAppPaths())
    summary = workshop_download_failure_summary("line\nERROR! Download item failed because login required")

    assert any("Conan Exiles Enhanced was not detected" in message for message in messages)
    assert any("Dedicated Server was not detected" in message for message in messages)
    assert any("SteamCMD is not configured" in message for message in messages)
    assert "login required" in summary
    assert steamcmd_may_need_account("License missing")
    assert "Settings > SteamCMD" in steamcmd_setup_guidance()
