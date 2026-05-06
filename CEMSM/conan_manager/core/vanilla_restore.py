"""Preview and apply empty/vanilla modlists without deleting pak files."""
from __future__ import annotations

from ..models.app_paths import ConanAppPaths
from ..models.modlist import ActiveModEntry, ModlistApplyResult, ModlistTargetPlan
from .backup_manager import BackupManager
from .modlist_service import apply_modlist_plans, build_apply_plans


def build_vanilla_restore_plans(paths: ConanAppPaths, target: str) -> list[ModlistTargetPlan]:
    return build_apply_plans(paths, target, [])


def apply_vanilla_restore(plans: list[ModlistTargetPlan], backup: BackupManager) -> ModlistApplyResult:
    for plan in plans:
        plan.proposed_entries = []
    return apply_modlist_plans(plans, backup)


def preview_vanilla_restore_text(plans: list[ModlistTargetPlan]) -> str:
    sections: list[str] = []
    for plan in plans:
        current = [entry.value for entry in plan.current_entries]
        removed_count = len(current)
        lines = [
            f"Target: {plan.label}",
            f"modlist.txt: {plan.modlist_path if str(plan.modlist_path) != '.' else 'not configured'}",
            f"Mods folder: {plan.mods_dir if str(plan.mods_dir) != '.' else 'not configured'}",
            f"Current entries removed from modlist: {removed_count}",
            f"Backup existing modlist: {'yes' if plan.backup_needed else 'no'}",
            "Pak files deleted: no",
            "",
            "Current:",
            *(current or ["  (empty or missing)"]),
            "",
            "Proposed:",
            "  (empty vanilla modlist)",
        ]
        if plan.warnings:
            lines.extend(["", "Warnings:", *plan.warnings])
        sections.append("\n".join(lines))
    return "\n\n" + ("-" * 72 + "\n\n").join(sections)
