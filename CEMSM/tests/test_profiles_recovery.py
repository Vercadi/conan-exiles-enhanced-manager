from __future__ import annotations

from pathlib import Path

import pytest

from conan_manager.core.activity_log import ActivityLog
from conan_manager.core.backup_manager import BackupManager, BackupRecord
from conan_manager.core.discovery import discover_all
from conan_manager.core.modlist_service import active_entry_from_pak, apply_modlist_plans, build_apply_plans
from conan_manager.core.profile_store import ProfileStore
from conan_manager.core.profile_warnings import profile_entry_warnings
from conan_manager.core.snapshot_service import list_snapshots, restore_snapshot_record, validate_snapshot_record
from conan_manager.core.support_diagnostics import SupportDiagnosticsService
from conan_manager.core.vanilla_restore import apply_vanilla_restore, build_vanilla_restore_plans
from conan_manager.models.activity import ActivityRecord
from conan_manager.models.hosted import HostedProfile
from conan_manager.models.modlist import TARGET_CLIENT, ActiveModEntry
from conan_manager.models.profiles import ModProfile, ServerProfile, TARGET_HOSTED
from conan_manager.models.workshop import WORKSHOP_STATUS_MISSING, WorkshopItem

from .conftest import create_fake_conan_library


def test_profile_serialization_roundtrip() -> None:
    mod_profile = ModProfile(
        name="Solo",
        entries=[ActiveModEntry("Example.pak", workshop_id="123")],
        target_coverage=[TARGET_CLIENT, TARGET_HOSTED],
        notes="test notes",
    )
    server_profile = ServerProfile(name="Dedicated", hosted_profile_name="Host", dedicated_launch_args="-Messaging")

    assert ModProfile.from_dict(mod_profile.to_dict()).entries[0].workshop_id == "123"
    assert ServerProfile.from_dict(server_profile.to_dict()).hosted_profile_name == "Host"


def test_profile_store_save_load_duplicate_rename_delete(tmp_path) -> None:
    store = ProfileStore(tmp_path)
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak")

    saved = store.save_mod_profile(
        name="Solo",
        entries=[active_entry_from_pak(pak)],
        target_coverage=[TARGET_CLIENT],
        notes="notes",
    )
    duplicate = store.duplicate_mod_profile("Solo", "Solo Copy")
    renamed = store.rename_mod_profile("Solo Copy", "Renamed")
    deleted = store.delete_mod_profile("Renamed")
    loaded = ProfileStore(tmp_path)

    assert saved.name == "Solo"
    assert duplicate.name == "Solo Copy"
    assert renamed.name == "Renamed"
    assert deleted
    assert loaded.get_mod_profile("Solo") is not None
    assert loaded.get_mod_profile("Renamed") is None
    assert loaded.get_mod_profile("Vanilla").entries == []


def test_vanilla_restore_creates_backup_and_does_not_delete_paks(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    backup = BackupManager(tmp_path / "backups")
    pak = tmp_path / "Example.pak"
    pak.write_bytes(b"pak")

    apply_modlist_plans(build_apply_plans(paths, TARGET_CLIENT, [active_entry_from_pak(pak)]), backup)
    plans = build_vanilla_restore_plans(paths, TARGET_CLIENT)
    result = apply_vanilla_restore(plans, backup)

    assert pak.is_file()
    assert paths.client_modlist_path.read_text(encoding="utf-8") == ""
    assert len(result.backup_ids) == 1
    assert backup.list_backups(category="modlists", source_path=paths.client_modlist_path)


def test_snapshot_listing_and_validated_restore(tmp_path) -> None:
    source = tmp_path / "ServerSettings.ini"
    source.write_text("before", encoding="utf-8")
    backup = BackupManager(tmp_path / "backups")
    record = backup.backup_file(source, category="configs", description="settings")
    source.write_text("after", encoding="utf-8")

    snapshots = list_snapshots(backup, category="configs")
    restored = restore_snapshot_record(backup, record.backup_id)

    assert snapshots[0].backup_id == record.backup_id
    assert restored.backup_id == record.backup_id
    assert source.read_text(encoding="utf-8") == "before"


def test_restore_validation_rejects_unregistered_and_outside_backup(tmp_path) -> None:
    backup = BackupManager(tmp_path / "backups")

    missing = validate_snapshot_record(backup, "missing")
    assert not missing.ok

    outside = tmp_path / "outside.ini"
    outside.write_text("bad", encoding="utf-8")
    backup._records.append(
        BackupRecord(
            backup_id="bad",
            timestamp="2026-01-01T00:00:00",
            category="configs",
            source_path=str(tmp_path / "dest.ini"),
            backup_path=str(outside),
        )
    )
    bad = validate_snapshot_record(backup, "bad")

    assert not bad.ok
    with pytest.raises(ValueError):
        restore_snapshot_record(backup, "bad")


def test_activity_timeline_is_bounded(tmp_path) -> None:
    log = ActivityLog(tmp_path, limit=3)

    for index in range(5):
        log.append(action="test", result="ok", target=str(index))

    loaded = ActivityLog(tmp_path, limit=3)
    records = loaded.list_records()

    assert len(records) == 3
    assert records[0].target == "4"
    assert records[-1].target == "2"


def test_diagnostics_redacts_hosted_secrets_and_includes_activity(tmp_path) -> None:
    steamapps = create_fake_conan_library(tmp_path)
    paths = discover_all(extra_steamapps_dirs=[steamapps])
    service = SupportDiagnosticsService()
    profile = HostedProfile(
        name="Host",
        protocol="sftp",
        host="example.invalid",
        username="admin",
        password="super-secret",
        private_key_path=tmp_path / "id_rsa",
    )
    activity = [ActivityRecord(action="profile save", result="saved", target="client", details="Solo")]

    report = service.build_report(
        paths=paths,
        data_dir=tmp_path / "data",
        backup_root=tmp_path / "backups",
        hosted_profiles=[profile],
        activity_records=activity,
    )

    assert "profile save" in report
    assert "super-secret" not in report
    assert str(tmp_path / "id_rsa") not in report
    assert "<configured>" in report or "Host" in report


def test_missing_workshop_and_local_pak_warnings(tmp_path) -> None:
    missing = tmp_path / "Missing.pak"
    entries = [
        ActiveModEntry(str(missing), source_type="local_pak"),
        ActiveModEntry("WorkshopMissing.pak", source_type="workshop", workshop_id="123"),
        ActiveModEntry("Other.pak", source_type="workshop", workshop_id="456"),
    ]
    workshop = [WorkshopItem(workshop_id="456", status=WORKSHOP_STATUS_MISSING)]

    warnings = profile_entry_warnings(entries, workshop)

    assert any("Missing source pak/archive" in warning for warning in warnings)
    assert any("Workshop 123 is not in the local cache" in warning for warning in warnings)
    assert any("Workshop 456 is missing" in warning for warning in warnings)
