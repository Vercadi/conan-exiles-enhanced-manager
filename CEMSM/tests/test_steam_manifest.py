from __future__ import annotations

from conan_manager.core.steam_manifest import parse_acf_text, read_app_manifest

from .conftest import write_appmanifest


def test_parse_acf_text_handles_nested_appstate() -> None:
    data = parse_acf_text(
        """
        "AppState"
        {
            "appid" "440900"
            "name" "Conan Exiles Enhanced"
            "InstalledDepots"
            {
                "440901"
                {
                    "manifest" "abc"
                }
            }
        }
        """
    )

    assert data["appid"] == "440900"
    assert data["name"] == "Conan Exiles Enhanced"
    assert data["InstalledDepots"]["440901"]["manifest"] == "abc"


def test_read_app_manifest_extracts_build_id(tmp_path) -> None:
    steamapps = tmp_path / "steamapps"
    manifest_path = write_appmanifest(steamapps, "443030", "Conan Exiles Dedicated Server", "Conan Exiles Dedicated Server", "23086292")

    manifest = read_app_manifest(manifest_path, library_root=tmp_path)

    assert manifest is not None
    assert manifest.appid == "443030"
    assert manifest.buildid == "23086292"
    assert manifest.installdir == "Conan Exiles Dedicated Server"
