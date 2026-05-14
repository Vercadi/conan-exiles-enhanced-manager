"""Conan modlist.txt read, compare, apply, and restore logic."""
from __future__ import annotations

import difflib
import logging
import shutil
from pathlib import Path

from ..models.app_paths import ConanAppPaths
from ..models.modlist import (
    TARGET_BOTH,
    TARGET_CLIENT,
    TARGET_DEDICATED_SERVER,
    TARGET_LABELS,
    APPLY_MODE_COPY,
    APPLY_MODE_SOURCE,
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
from ..utils.naming import timestamp_slug
from .backup_manager import BackupManager, BackupRecord
from .local_mod_library import normalize_mod_display_name
from .workshop_service import workshop_display_name

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
        display_name=normalize_mod_display_name(path.stem),
        source_type="local_pak",
    )


def active_entry_from_workshop_item(item: WorkshopItem) -> ActiveModEntry:
    if item.primary_pak is None:
        raise ValueError(f"Workshop item {item.workshop_id} has no pak file.")
    return ActiveModEntry(
        value=str(item.primary_pak),
        display_name=workshop_display_name(item),
        source_type="workshop",
        workshop_id=item.workshop_id,
        companion_paths=[str(path) for path in _same_stem_companions(item.primary_pak)],
        notes=item.compatibility_note,
    )


def active_entries_from_modlist(path: Path) -> list[ActiveModEntry]:
    return [
        ActiveModEntry(
            value=entry.value,
            display_name=normalize_mod_display_name(display_name_from_value(entry.value)),
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
    *,
    target_apply_modes: dict[str, str] | None = None,
) -> list[ModlistTargetPlan]:
    plans: list[ModlistTargetPlan] = []
    active_entries = [entry for entry in entries if entry.enabled]
    targets = _expand_targets(target)
    for target_value in targets:
        apply_mode = _apply_mode_for_target(target_value, target_apply_modes)
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
                    apply_mode=apply_mode,
                )
            )
            continue
        current_entries = read_modlist(modlist_path)
        target_values, file_copies, warnings = _target_modlist_values_and_copies(
            active_entries,
            mods_dir,
            apply_mode=apply_mode,
        )
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
                apply_mode=apply_mode,
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


def build_selected_sync_plans(
    paths: ConanAppPaths,
    target: str,
    selected_entries: list[ActiveModEntry],
    *,
    target_apply_modes: dict[str, str] | None = None,
) -> list[ModlistTargetPlan]:
    """Plan adding/syncing selected entries to a target without replacing unrelated entries."""
    plans: list[ModlistTargetPlan] = []
    selected_entries = [entry for entry in selected_entries if entry.enabled]
    for selected_plan in build_apply_plans(paths, target, selected_entries, target_apply_modes=target_apply_modes):
        if selected_plan.mods_dir == Path() or selected_plan.modlist_path == Path():
            plans.append(selected_plan)
            continue

        current_values = [entry.value for entry in selected_plan.current_entries]
        selected_values = selected_plan.proposed_values
        selected_keys = _identity_keys_for_values(selected_values)
        kept_values = [
            value
            for value in current_values
            if not _value_matches_identity(value, selected_keys)
        ]
        selected_plan.target_modlist_values = kept_values + selected_values
        plans.append(selected_plan)
    return plans


def build_selected_uninstall_plans(
    paths: ConanAppPaths,
    target: str,
    selected_entries: list[ActiveModEntry],
    *,
    target_apply_modes: dict[str, str] | None = None,
) -> list[ModlistTargetPlan]:
    """Plan removing selected entries from target modlists without deleting source files."""
    plans: list[ModlistTargetPlan] = []
    selected_entries = [entry for entry in selected_entries if entry.normalized_value]
    for selected_plan in build_apply_plans(paths, target, selected_entries, target_apply_modes=target_apply_modes):
        if selected_plan.mods_dir == Path() or selected_plan.modlist_path == Path():
            plans.append(selected_plan)
            continue

        selected_values = selected_plan.proposed_values
        selected_keys = _identity_keys_for_values(selected_values)
        selected_keys.update(_identity_keys_for_values(entry.normalized_value for entry in selected_entries))
        current_values = [entry.value for entry in selected_plan.current_entries]
        remaining = [
            value
            for value in current_values
            if not _value_matches_identity(value, selected_keys)
        ]
        quarantine_paths = _manager_owned_target_paths(selected_plan)
        selected_plan.proposed_entries = []
        selected_plan.target_modlist_values = remaining
        selected_plan.quarantine_paths = quarantine_paths
        plans.append(selected_plan)
    return plans


def apply_selected_uninstall_plans(
    plans: list[ModlistTargetPlan],
    backup: BackupManager,
    *,
    quarantine_target_files: bool = False,
) -> ModlistApplyResult:
    """Apply selected uninstall plans, optionally moving manager-owned target copies to quarantine."""
    result = ModlistApplyResult()
    for plan in plans:
        if plan.mods_dir == Path() or plan.modlist_path == Path():
            result.warnings.extend(plan.warnings)
            continue
        ensure_dir(plan.modlist_path.parent)
        if plan.modlist_path.is_file():
            record = backup.backup_file(
                plan.modlist_path,
                category="modlists",
                description=f"{plan.label} modlist backup before selected uninstall",
            )
            if record:
                result.backup_ids.append(record.backup_id)
        plan.modlist_path.write_text(render_modlist_values(plan.proposed_values), encoding="utf-8")
        result.written_paths.append(plan.modlist_path)
        if quarantine_target_files:
            for path in _dedupe_paths(plan.quarantine_paths):
                if not path.is_file():
                    continue
                record = backup.backup_file(
                    path,
                    category="mods",
                    description=f"{plan.label} target mod backup before quarantine",
                )
                if record:
                    result.backup_ids.append(record.backup_id)
                quarantine_path = _quarantine_path(backup, path)
                ensure_dir(quarantine_path.parent)
                shutil.move(str(path), str(quarantine_path))
                result.quarantined_paths.append(quarantine_path)
        result.warnings.extend(plan.warnings)
        log.info("Removed selected Conan mods for %s: %s", plan.label, plan.modlist_path)
    return result


def preview_selected_uninstall_text(
    plans: list[ModlistTargetPlan],
    *,
    quarantine_target_files: bool = False,
) -> str:
    sections: list[str] = []
    for plan in plans:
        current = [entry.value for entry in plan.current_entries]
        proposed = plan.proposed_values
        diff = "\n".join(
            difflib.unified_diff(
                current,
                proposed,
                fromfile=f"{plan.label} current modlist.txt",
                tofile=f"{plan.label} proposed modlist.txt",
                lineterm="",
            )
        )
        lines = [
            f"Target: {plan.label}",
            f"modlist.txt: {plan.modlist_path if str(plan.modlist_path) != '.' else 'not configured'}",
            f"Mods folder: {plan.mods_dir if str(plan.mods_dir) != '.' else 'not configured'}",
            f"Backup existing modlist: {'yes' if plan.backup_needed else 'no'}",
            f"Target file quarantine: {'yes' if quarantine_target_files else 'no'}",
            "Original source files deleted: no",
            "Steam Workshop cache deleted/unsubscribed: no",
            "",
            "Current -> Proposed diff:",
            diff or "  (no modlist entry changes)",
        ]
        if quarantine_target_files:
            lines.extend(["", "Manager-owned target files to quarantine:"])
            lines.extend(str(path) for path in _dedupe_paths(plan.quarantine_paths) if path.is_file())
            if not any(path.is_file() for path in plan.quarantine_paths):
                lines.append("  (none found)")
        if plan.warnings:
            lines.extend(["", "Warnings:", *plan.warnings])
        sections.append("\n".join(lines))
    return "\n\n" + ("-" * 72 + "\n\n").join(sections)


def render_modlist_text(entries: list[ActiveModEntry]) -> str:
    values = [entry.normalized_value for entry in entries if entry.enabled and entry.normalized_value]
    return render_modlist_values(values)


def render_modlist_values(values: list[str]) -> str:
    values = [normalize_modlist_value(value) for value in values if normalize_modlist_value(value)]
    return "\n".join(values) + ("\n" if values else "")


def target_status_labels_for_entry(
    entry: ActiveModEntry,
    *,
    client_mods_dir: Path | None = None,
    server_mods_dir: Path | None = None,
    client_modlist_path: Path | None = None,
    server_modlist_path: Path | None = None,
    target_apply_modes: dict[str, str] | None = None,
) -> list[str]:
    labels: list[str] = []
    for label, mods_dir, modlist_path in (
        ("Client", client_mods_dir, client_modlist_path),
        ("Server", server_mods_dir, server_modlist_path),
    ):
        if not mods_dir:
            continue
        target_value = TARGET_CLIENT if label == "Client" else TARGET_DEDICATED_SERVER
        state = target_install_state_for_entry(
            entry,
            mods_dir=mods_dir,
            modlist_path=modlist_path,
            apply_mode=_apply_mode_for_target(target_value, target_apply_modes),
        )
        labels.append(target_install_state_label(label, state))
    return labels


def target_install_state_for_entry(
    entry: ActiveModEntry,
    *,
    mods_dir: Path | None,
    modlist_path: Path | None,
    apply_mode: str = APPLY_MODE_COPY,
) -> str:
    if not mods_dir or not modlist_path:
        return "not_configured"

    current_values = [entry.value for entry in read_modlist(modlist_path)]
    target_values, _file_copies, _warnings = _target_modlist_values_and_copies(
        [entry],
        mods_dir,
        apply_mode=apply_mode,
    )
    candidate_values = [entry.normalized_value, *target_values]
    candidate_keys = _identity_keys_for_values(candidate_values)
    in_order = any(_value_matches_identity(value, candidate_keys) for value in current_values)
    file_status = _entry_target_status(entry, mods_dir, apply_mode=apply_mode)

    if file_status == "Missing source for":
        return "missing_source"
    if in_order:
        if file_status == "Synced to":
            return "synced"
        if file_status == "Outdated on":
            return "outdated"
        if file_status == "Missing on":
            return "missing_file"
        return "in_order"
    if file_status == "Synced to":
        return "file_only"
    return "not_in_order"


def target_install_state_label(target_label: str, state: str) -> str:
    text = {
        "synced": "synced",
        "in_order": "in order",
        "not_in_order": "not in order",
        "missing_source": "source missing",
        "missing_file": "listed, pak missing",
        "outdated": "outdated",
        "file_only": "file only",
        "not_configured": "not configured",
    }.get(state, state.replace("_", " "))
    return f"{target_label}: {text}"


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
    *,
    apply_mode: str = APPLY_MODE_COPY,
) -> tuple[list[str], list[TargetFileCopy], list[str]]:
    values: list[str] = []
    copies: list[TargetFileCopy] = []
    warnings: list[str] = []
    for entry in entries:
        value = entry.normalized_value
        if not value:
            continue
        if entry.requires_target_copy and apply_mode == APPLY_MODE_COPY:
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


def _apply_mode_for_target(target: str, target_apply_modes: dict[str, str] | None) -> str:
    if not target_apply_modes:
        return APPLY_MODE_COPY
    mode = target_apply_modes.get(target, APPLY_MODE_COPY)
    return mode if mode in {APPLY_MODE_COPY, APPLY_MODE_SOURCE} else APPLY_MODE_COPY


def _same_stem_companions(pak_path: Path) -> list[Path]:
    companions: list[Path] = []
    for suffix in (".ucas", ".utoc"):
        companion = pak_path.with_suffix(suffix)
        if companion.is_file():
            companions.append(companion)
    companions.extend(
        path
        for path in pak_path.parent.glob(f"{pak_path.stem}.*")
        if path.is_file() and path.suffix.casefold() not in {".pak", ".ucas", ".utoc"}
    )
    return sorted(set(companions), key=lambda path: path.name.casefold())


def _identity_keys_for_values(values) -> set[str]:
    keys: set[str] = set()
    for value in values:
        text = normalize_modlist_value(value)
        if not text:
            continue
        normalized = text.replace("\\", "/").casefold()
        keys.add(normalized)
        name = Path(text).name
        if name:
            keys.add(name.casefold())
    return keys


def _value_matches_identity(value: str, keys: set[str]) -> bool:
    return bool(_identity_keys_for_values([value]) & keys)


def _manager_owned_target_paths(plan: ModlistTargetPlan) -> list[Path]:
    paths: list[Path] = []
    paths.extend(
        copy.target_path
        for copy in plan.file_copies
        if not _same_file_path(copy.source_path, copy.target_path)
    )
    return _dedupe_paths(paths)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    deduped: list[Path] = []
    for path in paths:
        key = str(path).replace("\\", "/").casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _quarantine_path(backup: BackupManager, source: Path) -> Path:
    base = backup.backup_root / "quarantine" / timestamp_slug()
    candidate = base / source.name
    counter = 1
    while candidate.exists():
        candidate = base / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    return candidate


def _entry_target_status(entry: ActiveModEntry, mods_dir: Path, *, apply_mode: str = APPLY_MODE_COPY) -> str:
    value = entry.normalized_value
    if not value:
        return ""
    source = resolve_entry_path(value)
    if apply_mode == APPLY_MODE_SOURCE:
        resolved = resolve_entry_path(value, mods_dir)
        if resolved is None or not resolved.is_file():
            return "Missing source for"
        return "Synced to"
    if entry.requires_target_copy:
        if source is None or not source.is_file():
            return "Missing source for"
        target = mods_dir / source.name
        if not target.is_file():
            return "Missing on"
        try:
            return "Synced to" if target.stat().st_size == source.stat().st_size else "Outdated on"
        except OSError:
            return "Outdated on"
    resolved = resolve_entry_path(value, mods_dir)
    if resolved is None or not resolved.is_file():
        return "Missing on"
    return "Synced to"


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
