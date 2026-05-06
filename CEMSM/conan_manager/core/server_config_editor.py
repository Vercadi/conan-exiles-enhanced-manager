"""INI-preserving dedicated server config editing."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models.app_paths import ConanAppPaths
from ..models.server import ServerProcessStatus
from .backup_manager import BackupManager, BackupRecord

SECTION_SERVER = "ServerSettings"
SECTION_STEAM = "OnlineSubsystemSteam"
SECTION_RCON = "RConPlugin"
SECTION_URL = "URL"


@dataclass
class IniLine:
    raw: str
    section: str = ""
    key: str = ""
    value: str = ""
    is_section: bool = False
    is_key_value: bool = False


class IniDocument:
    """Line-oriented INI document that keeps unrelated text intact."""

    def __init__(self, lines: list[IniLine] | None = None):
        self.lines = lines or []

    @classmethod
    def from_text(cls, text: str) -> "IniDocument":
        lines: list[IniLine] = []
        current_section = ""
        for raw in text.splitlines(keepends=True):
            line = raw.rstrip("\r\n")
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1].strip()
                lines.append(IniLine(raw=raw, section=current_section, is_section=True))
                continue
            parsed = _parse_key_value_line(line)
            if parsed:
                key, value = parsed
                lines.append(
                    IniLine(
                        raw=raw,
                        section=current_section,
                        key=key,
                        value=value,
                        is_key_value=True,
                    )
                )
            else:
                lines.append(IniLine(raw=raw, section=current_section))
        return cls(lines)

    def to_text(self) -> str:
        return "".join(line.raw for line in self.lines)

    def get(self, section: str, key: str) -> str:
        line = self._find_line(section, key)
        return line.value if line else ""

    def set(self, section: str, key: str, value: str) -> None:
        line = self._find_line(section, key)
        if line:
            line.raw = _replace_value(line.raw, str(value))
            parsed = _parse_key_value_line(line.raw.rstrip("\r\n"))
            line.value = parsed[1] if parsed else str(value)
            return

        insert_at = self._section_insert_index(section)
        new_line = IniLine(
            raw=f"{key}={value}\n",
            section=section,
            key=key,
            value=str(value),
            is_key_value=True,
        )
        if insert_at is not None:
            if insert_at > 0 and not self.lines[insert_at - 1].raw.endswith(("\n", "\r")):
                self.lines[insert_at - 1].raw += "\n"
            self.lines.insert(insert_at, new_line)
            return

        if self.lines and not self.lines[-1].raw.endswith(("\n", "\r")):
            self.lines[-1].raw += "\n"
        if self.lines and self.lines[-1].raw.strip():
            self.lines.append(IniLine(raw="\n"))
        self.lines.append(IniLine(raw=f"[{section}]\n", section=section, is_section=True))
        self.lines.append(new_line)

    def _find_line(self, section: str, key: str) -> IniLine | None:
        section_key = section.casefold()
        key_key = key.casefold()
        for line in self.lines:
            if line.is_key_value and line.section.casefold() == section_key and line.key.casefold() == key_key:
                return line
        return None

    def _section_insert_index(self, section: str) -> int | None:
        section_key = section.casefold()
        in_section = False
        last_index: int | None = None
        for index, line in enumerate(self.lines):
            if line.is_section:
                if line.section.casefold() == section_key:
                    in_section = True
                    last_index = index + 1
                    continue
                if in_section:
                    return index
            if in_section:
                last_index = index + 1
        return last_index


@dataclass
class ServerConfigEdit:
    server_name: str | None = None
    server_password: str | None = None
    clear_server_password: bool = False
    admin_password: str | None = None
    clear_admin_password: bool = False
    max_players: str | None = None
    pvp_enabled: str | None = None
    battleye_enabled: str | None = None
    game_port: str | None = None
    query_port: str | None = None
    rcon_enabled: str | None = None
    rcon_password: str | None = None
    clear_rcon_password: bool = False
    rcon_port: str | None = None
    motd: str | None = None
    server_mod_list: str | None = None
    mirror_server_mod_list: bool = False


@dataclass
class ConfigFileEditPlan:
    path: Path
    current_text: str
    proposed_text: str
    description: str

    @property
    def changed(self) -> bool:
        return self.current_text != self.proposed_text

    @property
    def diff(self) -> str:
        if not self.changed:
            return ""
        return "".join(
            difflib.unified_diff(
                self.current_text.splitlines(keepends=True),
                self.proposed_text.splitlines(keepends=True),
                fromfile=f"{self.path.name} (current)",
                tofile=f"{self.path.name} (proposed)",
            )
        )


@dataclass
class ServerConfigEditPlan:
    file_plans: list[ConfigFileEditPlan] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    running_server: bool = False

    @property
    def changed_plans(self) -> list[ConfigFileEditPlan]:
        return [plan for plan in self.file_plans if plan.changed]

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_plans)

    @property
    def diff_text(self) -> str:
        diffs = [plan.diff for plan in self.changed_plans if plan.diff]
        return "\n".join(diffs) if diffs else "No config changes staged."


@dataclass
class ServerConfigApplyResult:
    written_paths: list[Path] = field(default_factory=list)
    backup_records: list[BackupRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_server_config_edit_plan(
    paths: ConanAppPaths,
    edit: ServerConfigEdit,
    *,
    process_status: ServerProcessStatus | None = None,
) -> ServerConfigEditPlan:
    plan = ServerConfigEditPlan()
    if process_status and process_status.running:
        plan.running_server = True
        plan.warnings.append("Dedicated server is running. Stop it before applying config changes when possible.")

    settings_path = paths.dedicated_server_settings
    engine_path = paths.dedicated_server_engine_ini
    game_path = paths.dedicated_server_game_ini
    game_user_path = paths.dedicated_server_game_user_settings

    if not paths.dedicated_server_config_dir:
        plan.warnings.append("Dedicated server config folder is not configured.")
        return plan

    settings_doc = _read_document(settings_path)
    engine_doc = _read_document(engine_path)
    game_doc = _read_document(game_path)
    game_user_doc = _read_document(game_user_path)

    _set_optional(settings_doc, SECTION_SERVER, "ServerName", edit.server_name)
    _set_secret(settings_doc, SECTION_SERVER, "ServerPassword", edit.server_password, edit.clear_server_password)
    _set_secret(settings_doc, SECTION_SERVER, "AdminPassword", edit.admin_password, edit.clear_admin_password)
    _set_optional(settings_doc, SECTION_SERVER, "MaxPlayers", edit.max_players)
    _set_optional(settings_doc, SECTION_SERVER, "PVPEnabled", edit.pvp_enabled)
    _set_optional(settings_doc, SECTION_SERVER, "IsBattlEyeEnabled", edit.battleye_enabled)
    _set_optional(settings_doc, SECTION_SERVER, "Port", edit.game_port)
    _set_optional(settings_doc, SECTION_SERVER, _motd_key(settings_doc), edit.motd)
    if edit.mirror_server_mod_list:
        _set_optional(settings_doc, SECTION_SERVER, "ServerModList", edit.server_mod_list or "")

    _set_optional(engine_doc, SECTION_URL, "Port", edit.game_port)
    _set_optional(engine_doc, SECTION_STEAM, "QueryPort", edit.query_port)
    _set_optional(engine_doc, SECTION_RCON, "RconEnabled", edit.rcon_enabled)
    _set_secret(engine_doc, SECTION_RCON, "RconPassword", edit.rcon_password, edit.clear_rcon_password)
    _set_optional(engine_doc, SECTION_RCON, "RconPort", edit.rcon_port)

    for path, current, document, description in [
        (settings_path, _read_text(settings_path), settings_doc, "Server settings"),
        (engine_path, _read_text(engine_path), engine_doc, "Engine/RCON settings"),
        (game_path, _read_text(game_path), game_doc, "Game settings"),
        (game_user_path, _read_text(game_user_path), game_user_doc, "Game user settings"),
    ]:
        if path:
            file_plan = ConfigFileEditPlan(
                path=path,
                current_text=current,
                proposed_text=document.to_text(),
                description=description,
            )
            if file_plan.changed:
                plan.file_plans.append(file_plan)
    if edit.server_mod_list and not edit.mirror_server_mod_list:
        plan.warnings.append("ServerModList was not changed because mirror option is disabled.")
    return plan


def apply_server_config_edit_plan(plan: ServerConfigEditPlan, backup: BackupManager) -> ServerConfigApplyResult:
    result = ServerConfigApplyResult(warnings=list(plan.warnings))
    for file_plan in plan.changed_plans:
        if file_plan.path.is_file():
            record = backup.backup_file(
                file_plan.path,
                category="configs",
                description=f"{file_plan.description} backup before config edit",
            )
            if record:
                result.backup_records.append(record)
        file_plan.path.parent.mkdir(parents=True, exist_ok=True)
        file_plan.path.write_text(file_plan.proposed_text, encoding="utf-8")
        result.written_paths.append(file_plan.path)
    return result


def config_preview_text(plan: ServerConfigEditPlan) -> str:
    rows: list[str] = []
    if plan.running_server:
        rows.append("WARNING: Dedicated server appears to be running.")
        rows.append("")
    if plan.warnings:
        rows.append("Warnings:")
        rows.extend(f"- {warning}" for warning in plan.warnings)
        rows.append("")
    rows.append("Files that will change:")
    if plan.changed_plans:
        rows.extend(f"- {file_plan.path}" for file_plan in plan.changed_plans)
    else:
        rows.append("- none")
    rows.append("")
    rows.append("Backups that will be created:")
    changed_existing = [file_plan for file_plan in plan.changed_plans if file_plan.path.is_file()]
    if changed_existing:
        rows.extend(f"- {file_plan.path}" for file_plan in changed_existing)
    else:
        rows.append("- none")
    rows.append("")
    rows.append("Diff:")
    rows.append(plan.diff_text)
    return "\n".join(rows)


def _set_optional(document: IniDocument, section: str, key: str, value: str | None) -> None:
    if value is not None:
        document.set(section, key, value)


def _set_secret(document: IniDocument, section: str, key: str, value: str | None, clear: bool) -> None:
    if clear:
        document.set(section, key, "")
    elif value is not None:
        document.set(section, key, value)


def _motd_key(document: IniDocument) -> str:
    for key in ("MessageOfTheDay", "ServerMessageOfTheDay", "MOTD"):
        if document.get(SECTION_SERVER, key):
            return key
    return "MessageOfTheDay"


def _read_document(path: Path | None) -> IniDocument:
    return IniDocument.from_text(_read_text(path))


def _read_text(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_key_value_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", ";")) or "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    return key, _strip_inline_comment(value).strip()


def _replace_value(raw: str, value: str) -> str:
    eol = ""
    body = raw
    if raw.endswith("\r\n"):
        body = raw[:-2]
        eol = "\r\n"
    elif raw.endswith("\n"):
        body = raw[:-1]
        eol = "\n"
    match = re.match(r"^([^=]*=\s*)(.*)$", body)
    if not match:
        return f"{raw}={value}{eol}"
    prefix, current_value = match.groups()
    suffix = _inline_comment_suffix(current_value)
    return f"{prefix}{value}{suffix}{eol}"


def _strip_inline_comment(value: str) -> str:
    suffix_index = _inline_comment_index(value)
    if suffix_index is None:
        return value
    return value[:suffix_index]


def _inline_comment_suffix(value: str) -> str:
    suffix_index = _inline_comment_index(value)
    if suffix_index is None:
        return ""
    return value[suffix_index:]


def _inline_comment_index(value: str) -> int | None:
    for marker in (" ;", " #"):
        index = value.find(marker)
        if index >= 0:
            return index
    return None
