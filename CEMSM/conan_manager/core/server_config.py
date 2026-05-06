"""Read-only Conan dedicated server config parsing."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ..models.app_paths import ConanAppPaths
from ..models.server import ServerConfigSnapshot


def read_server_config(paths: ConanAppPaths) -> ServerConfigSnapshot:
    snapshot = ServerConfigSnapshot(
        server_settings_path=paths.dedicated_server_settings,
        engine_ini_path=paths.dedicated_server_engine_ini,
    )
    server_settings = parse_ini_like(paths.dedicated_server_settings)
    engine_ini = parse_ini_like(paths.dedicated_server_engine_ini)

    server_values = flatten_sections(server_settings)
    engine_values = flatten_sections(engine_ini)

    snapshot.server_name = first_value(server_values, "servername")
    snapshot.server_password_set = bool(first_value(server_values, "serverpassword"))
    snapshot.admin_password_set = bool(first_value(server_values, "adminpassword"))
    snapshot.max_players = first_value(server_values, "maxplayers")
    snapshot.pvp_enabled = first_value(server_values, "pvpenabled")
    snapshot.battleye_enabled = first_value(server_values, "isbattleyeenabled")
    snapshot.server_mod_list = first_value(server_values, "servermodlist")

    snapshot.game_port = first_value(engine_values, "port") or first_value(server_values, "port") or "7777"
    snapshot.query_port = first_value(engine_values, "queryport") or first_value(server_values, "queryport") or "27015"
    snapshot.rcon_enabled = first_value(engine_values, "rconenabled") or first_value(server_values, "rconenabled")
    snapshot.rcon_port = first_value(engine_values, "rconport") or first_value(server_values, "rconport") or "25575"
    snapshot.rcon_password_set = bool(first_value(engine_values, "rconpassword") or first_value(server_values, "rconpassword"))
    return snapshot


def parse_ini_like(path: Path | None) -> dict[str, dict[str, str]]:
    if not path or not path.is_file():
        return {}
    sections: dict[str, dict[str, str]] = defaultdict(dict)
    current = ""
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        sections[current][key.strip()] = value.strip()
    return dict(sections)


def flatten_sections(sections: dict[str, dict[str, str]]) -> dict[str, list[str]]:
    flattened: dict[str, list[str]] = defaultdict(list)
    for values in sections.values():
        for key, value in values.items():
            flattened[key.casefold()].append(value)
    return dict(flattened)


def first_value(values: dict[str, list[str]], key: str) -> str:
    matches = values.get(key.casefold(), [])
    return matches[0] if matches else ""
