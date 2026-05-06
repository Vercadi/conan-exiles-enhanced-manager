"""Conan modlist.txt read, compare, apply, and restore logic."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ..models.app_paths import ConanAppPaths
from ..models.modlist import (
    TARGET_BOTH,
    TARGET_CLIENT,
    TARGET_DEDICATED_SERVER,
    TARGET_LABELS,
    ActiveModEntry,
    ModlistApplyResult,
    ModlistEntry,
    ModlistParity,
    ModlistTargetPlan,
    TargetFileCopy,
    display_name_from_value,
    normalize_modlist_value,
)
from ..models.workshop import WorkshopItem
from ..utils.filesystem import ensure_dir
from .backup_manager import BackupManager, BackupRecord

log = logging.getLogger(__name__)


def read_modlist(path: Path) -> list[ModlistEntry]:
    """Read a Conan modlist.txt and preserve non-empty entry order."""
    if not path.is_file():
        return []
    entries: list[ModlistEntry] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines, start=1):
        value = normalize_modlist_value(line)
        if not value:
            continue
        resolved = resolve_entry_path(value, path.parent)
        entries.append(
            ModlistEntry(
                value=value,
                line_number=index,
                resolved_path=resolved,
                exists=bool(resolved and resolved.is_file()),
            )
        )
    return entries


def active_entry_from_pak(path: Path) -> ActiveModEntry:
    return ActiveModEntry(
        value=str(path),
        display_name=path.stem,
        source_type="local_pak",
    )


def active_entry_from_workshop_item(item: WorkshopItem) -> ActiveModEntry:
    if item.primary_pak is None:
        raise ValueError(f"Workshop item {item.workshop_id} has no pak file.")
    return ActiveModEntry(
        value=str(item.primary_pak),
        display_name=item.title or item.primary_pak.stem,
        source_type="workshop",
        workshop_id=item.workshop_id,
        notes=item.compatibility_note,
    )


def active_entries_from_modlist(path: Path) -> list[ActiveModEntry]:
    return [
        ActiveModEntry(
            value=entry.value,
            display_name=display_name_from_value(entry.value),
            source_type="modlist",
        )
        for entry in read_modlist(path)
    ]


def missing_entries(entries: list[ActiveModEntry | ModlistEntry], base_dir: Path | None = None) -> list[str]:
    missing: list[str] = []
    for entry in entries:
        if isinstance(entry, ActiveModEntry) and not entry.enabled:
            continue
        value = entry.normalized_value
        if not value:
            continue
        resolved = resolve_entry_path(value, base_dir)
        if resolved is None or not resolved.is_file():
            missing.append(value)
    return missing


def compare_modlists(client_entries: list[ModlistEntry], server_entries: list[ModlistEntry]) -> ModlistParity:
    client_values = [entry.normalized_value for entry in client_entries]
    server_values = [entry.normalized_value for entry in server_entries]
    if client_values == server_values:
        return ModlistParity(matches=True, client_count=len(client_values), server_count=len(server_values))

    client_set = {_comparison_key(value) for value in client_values}
    server_set = {_comparison_key(value) for value in server_values}
    missing_on_client = [
        value for value in server_values if _comparison_key(value) not in client_set
    ]
    missing_on_server = [
        value for value in client_values if _comparison_key(value) not in server_set
    ]
    order_mismatch = not missing_on_client and not missing_on_server and client_values != server_values
    return ModlistParity(
        matches=False,
        client_count=len(client_values),
        server_count=len(server_values),
        missing_on_client=missing_on_client,
        missing_on_server=missing_on_server,
        order_mismatch=order_mismatch,
    )


def compare_client_server(paths: ConanAppPaths) -> ModlistParity:
    return compare_modlists(
        read_modlist(paths.client_modlist_path) if paths.client_modlist_path else [],
        read_modlist(paths.dedicated_server_modlist_path) if paths.dedicated_server_modlist_path else [],
    )


def build_apply_plans(
    paths: ConanAppPaths,
    target: str,
    entries: list[ActiveModEntry],
) -> list[ModlistTargetPlan]:
    plans: list[ModlistTargetPlan] = []
    active_entries = [entry for entry in entries if entry.enabled]
    targets = _expand_targets(target)
    for target_value in targets:
        mods_dir = _mods_dir_for_target(paths, target_value)
        modlist_path = _modlist_path_for_target(paths, target_value)
        label = TARGET_LABELS.get(target_value, target_value)
        if mods_dir is None or modlist_path is None:
            plans.append(
                ModlistTargetPlan(
                    target=target_value,
                    label=label,
                    mods_dir=Path(),
                    modlist_path=Path(),
                    proposed_entries=list(active_entries),
                    warnings=[f"{label} path is not configured."],
                )
            )
            continue
        current_entries = read_modlist(modlist_path)
        target_values, file_copies, warnings = _target_modlist_values_and_copies(active_entries, mods_dir)
        plans.append(
            ModlistTargetPlan(
                target=target_value,
                label=label,
                mods_dir=mods_dir,
                modlist_path=modlist_path,
                current_entries=current_entries,
                proposed_entries=list(active_entries),
                target_modlist_values=target_values,
                file_copies=file_copies,
                warnings=warnings,
            )
        )
    return plans


def apply_modlist_plans(plans: list[ModlistTargetPlan], backup: BackupManager) -> ModlistApplyResult:
    result = ModlistApplyResult()
    for plan in plans:
        if plan.mods_dir == Path() or plan.modlist_path == Path():
            result.warnings.extend(plan.warnings)
            continue

        ensure_dir(plan.mods_dir)
        for copy_plan in _dedupe_file_copies(plan.file_copies):
            if not copy_plan.source_path.is_file():
                result.warnings.append(f"Missing source file: {copy_plan.source_path}")
                continue
            if _same_file_path(copy_plan.source_path, copy_plan.target_path):
                continue
            ensure_dir(copy_plan.target_path.parent)
            if copy_plan.target_path.is_file():
                record = backup.backup_file(
                    copy_plan.target_path,
                    category="mods",
                    description=f"{plan.label} mod file backup before overwrite",
                )
                if record:
                    result.backup_ids.append(record.backup_id)
            shutil.copy2(copy_plan.source_path, copy_plan.target_path)
            result.copied_paths.append(copy_plan.target_path)

        if plan.modlist_path.is_file():
            record = backup.backup_file(
                plan.modlist_path,
                category="modlists",
                description=f"{plan.label} modlist backup before apply",
            )
            if record:
                result.backup_ids.append(record.backup_id)

        text = render_modlist_values(plan.proposed_values)
        plan.modlist_path.write_text(text, encoding="utf-8")
        result.written_paths.append(plan.modlist_path)
        result.warnings.extend(plan.warnings)
        log.info("Wrote Conan modlist for %s: %s", plan.label, plan.modlist_path)
    return result


def render_modlist_text(entries: list[ActiveModEntry]) -> str:
    values = [entry.normalized_value for entry in entries if entry.enabled and entry.normalized_value]
    return render_modlist_values(values)


def render_modlist_values(values: list[str]) -> str:
    values = [normalize_modlist_value(value) for value in values if normalize_modlist_value(value)]
    return "\n".join(values) + ("\n" if values else "")


def latest_modlist_backup(backup: BackupManager, modlist_path: Path) -> BackupRecord | None:
    records = backup.list_backups(category="modlists", source_path=modlist_path)
    if not records:
        return None
    return sorted(records, key=lambda record: record.timestamp)[-1]


def restore_latest_modlist(backup: BackupManager, modlist_path: Path) -> BackupRecord | None:
    record = latest_modlist_backup(backup, modlist_path)
    if record is None:
        return None
    backup.restore_backup(record, dest_path=modlist_path)
    return record


def resolve_entry_path(value: str, base_dir: Path | None = None) -> Path | None:
    value = normalize_modlist_value(value)
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if base_dir:
        return base_dir / candidate
    return candidate


def _target_modlist_values_and_copies(
    entries: list[ActiveModEntry],
    mods_dir: Path,
) -> tuple[list[str], list[TargetFileCopy], list[str]]:
    values: list[str] = []
    copies: list[TargetFileCopy] = []
    warnings: list[str] = []
    for entry in entries:
        value = entry.normalized_value
        if not value:
            continue
        if entry.requires_target_copy:
            source = resolve_entry_path(value)
            if source is None or not source.is_file():
                warnings.append(f"Missing pak: {value}")
                continue
            target = mods_dir / source.name
            copies.append(TargetFileCopy(source_path=source, target_path=target))
            values.append(target.name)
            for companion_value in entry.companion_paths:
                companion = resolve_entry_path(companion_value)
                if companion is None or not companion.is_file():
                    warnings.append(f"Missing companion file: {companion_value}")
                    continue
                copies.append(TargetFileCopy(source_path=companion, target_path=mods_dir / companion.name))
        else:
            values.append(value)
            resolved = resolve_entry_path(value, mods_dir)
            if resolved is None or not resolved.is_file():
                warnings.append(f"Missing pak: {value}")
    return values, copies, warnings


def _dedupe_file_copies(copies: list[TargetFileCopy]) -> list[TargetFileCopy]:
    seen: set[str] = set()
    deduped: list[TargetFileCopy] = []
    for copy_plan in copies:
        key = str(copy_plan.target_path).replace("\\", "/").casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(copy_plan)
    return deduped


def _same_file_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left).replace("\\", "/").casefold() == str(right).replace("\\", "/").casefold()


def _expand_targets(target: str) -> list[str]:
    if target == TARGET_BOTH:
        return [TARGET_CLIENT, TARGET_DEDICATED_SERVER]
    return [target]


def _mods_dir_for_target(paths: ConanAppPaths, target: str) -> Path | None:
    if target == TARGET_CLIENT:
        return paths.client_mods_dir
    if target == TARGET_DEDICATED_SERVER:
        return paths.dedicated_server_mods_dir
    return None


def _modlist_path_for_target(paths: ConanAppPaths, target: str) -> Path | None:
    if target == TARGET_CLIENT:
        return paths.client_modlist_path
    if target == TARGET_DEDICATED_SERVER:
        return paths.dedicated_server_modlist_path
    return None


def _comparison_key(value: str) -> str:
    return normalize_modlist_value(value).replace("\\", "/").casefold()
