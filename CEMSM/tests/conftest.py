from __future__ import annotations

from pathlib import Path


def write_appmanifest(steamapps: Path, appid: str, name: str, installdir: str, buildid: str) -> Path:
    path = steamapps / f"appmanifest_{appid}.acf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '"AppState"',
                "{",
                f'    "appid"        "{appid}"',
                f'    "name"        "{name}"',
                f'    "installdir"        "{installdir}"',
                f'    "buildid"        "{buildid}"',
                '    "LastUpdated"        "1778014716"',
                '    "SizeOnDisk"        "123456"',
                "}",
            ]
        ),
        encoding="utf-8",
    )
    return path


def create_fake_conan_library(tmp_path: Path) -> Path:
    steamapps = tmp_path / "SteamLibrary" / "steamapps"
    common = steamapps / "common"
    write_appmanifest(steamapps, "440900", "Conan Exiles Enhanced", "Conan Exiles", "23086684")
    write_appmanifest(steamapps, "443030", "Conan Exiles Dedicated Server", "Conan Exiles Dedicated Server", "23086292")

    client = common / "Conan Exiles"
    (client / "ConanSandbox" / "Binaries" / "Win64").mkdir(parents=True)
    (client / "ConanSandbox" / "Saved" / "Config" / "Windows").mkdir(parents=True)
    (client / "ConanSandbox" / "Saved" / "Logs").mkdir(parents=True)
    (client / "ConanSandbox.exe").write_text("", encoding="utf-8")
    (client / "ConanSandbox" / "Binaries" / "Win64" / "ConanSandbox-Win64-Shipping.exe").write_text("", encoding="utf-8")
    (client / "ConanSandbox" / "Saved" / "Config" / "Windows" / "ServerSettings.ini").write_text(
        "[ServerSettings]\nServerModList=\n",
        encoding="utf-8",
    )
    (client / "ConanSandbox" / "Saved" / "Game_0.db").write_bytes(b"client-db")

    server = common / "Conan Exiles Dedicated Server"
    (server / "ConanSandbox" / "Binaries" / "Win64").mkdir(parents=True)
    (server / "ConanSandbox" / "Saved" / "Config" / "WindowsServer").mkdir(parents=True)
    (server / "ConanSandbox" / "Saved" / "Logs").mkdir(parents=True)
    (server / "ConanSandboxServer.exe").write_text("", encoding="utf-8")
    (server / "ConanSandbox" / "Binaries" / "Win64" / "ConanSandboxServer-Win64-Shipping.exe").write_text(
        "",
        encoding="utf-8",
    )
    (server / "ConanSandbox" / "Saved" / "Config" / "WindowsServer" / "ServerSettings.ini").write_text(
        "[ServerSettings]\nServerModList=\n",
        encoding="utf-8",
    )
    (server / "ConanSandbox" / "Saved" / "Config" / "WindowsServer" / "GameUserSettings.ini").write_text(
        "[ScalabilityGroups]\n",
        encoding="utf-8",
    )
    (server / "ConanSandbox" / "Saved" / "game_0.db").write_bytes(b"server-db")

    (steamapps / "workshop" / "content" / "440900" / "1234567890").mkdir(parents=True)
    return steamapps
