"""Named mod and server profile persistence."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..models.modlist import ActiveModEntry
from ..models.profiles import ModProfile, ServerProfile, utc_timestamp
from ..utils.json_io import read_json, write_json


class ProfileStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "profiles.json"
        self._mod_profiles: list[ModProfile] = []
        self._server_profiles: list[ServerProfile] = []
        self.load()

    def load(self) -> None:
        data = read_json(self.path)
        self._mod_profiles = [
            ModProfile.from_dict(item)
            for item in data.get("mod_profiles", [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        self._server_profiles = [
            ServerProfile.from_dict(item)
            for item in data.get("server_profiles", [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        if not any(profile.name == "Vanilla" for profile in self._mod_profiles):
            self._mod_profiles.insert(
                0,
                ModProfile(name="Vanilla", entries=[], notes="No mods. Writes an empty modlist when applied."),
            )
            self._save()

    def list_mod_profiles(self) -> list[ModProfile]:
        return list(self._mod_profiles)

    def list_server_profiles(self) -> list[ServerProfile]:
        return list(self._server_profiles)

    def get_mod_profile(self, name: str) -> ModProfile | None:
        for profile in self._mod_profiles:
            if profile.name == name:
                return profile
        return None

    def get_server_profile(self, name: str) -> ServerProfile | None:
        for profile in self._server_profiles:
            if profile.name == name:
                return profile
        return None

    def save_mod_profile(
        self,
        *,
        name: str,
        entries: list[ActiveModEntry],
        target_coverage: list[str],
        notes: str = "",
    ) -> ModProfile:
        existing = self.get_mod_profile(name)
        now = utc_timestamp()
        profile = ModProfile(
            name=name,
            entries=list(entries),
            target_coverage=target_coverage,
            notes=notes,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        ).normalized()
        self._mod_profiles = [item for item in self._mod_profiles if item.name != profile.name]
        if profile.name == "Vanilla":
            self._mod_profiles.insert(0, profile)
        else:
            self._mod_profiles.append(profile)
        self._save()
        return profile

    def save_server_profile(self, profile: ServerProfile) -> ServerProfile:
        existing = self.get_server_profile(profile.name)
        now = utc_timestamp()
        saved = replace(
            profile.normalized(),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        ).normalized()
        self._server_profiles = [item for item in self._server_profiles if item.name != saved.name]
        self._server_profiles.append(saved)
        self._save()
        return saved

    def duplicate_mod_profile(self, source_name: str, new_name: str) -> ModProfile:
        source = self._require_mod(source_name)
        return self.save_mod_profile(
            name=new_name,
            entries=list(source.entries),
            target_coverage=list(source.target_coverage),
            notes=source.notes,
        )

    def rename_mod_profile(self, old_name: str, new_name: str) -> ModProfile:
        source = self._require_mod(old_name)
        if old_name == "Vanilla":
            raise ValueError("The Vanilla profile cannot be renamed.")
        self._mod_profiles = [item for item in self._mod_profiles if item.name != old_name]
        renamed = replace(source, name=new_name, updated_at=utc_timestamp()).normalized()
        self._mod_profiles.append(renamed)
        self._save()
        return renamed

    def delete_mod_profile(self, name: str) -> bool:
        if name == "Vanilla":
            raise ValueError("The Vanilla profile cannot be deleted.")
        before = len(self._mod_profiles)
        self._mod_profiles = [item for item in self._mod_profiles if item.name != name]
        changed = len(self._mod_profiles) != before
        if changed:
            self._save()
        return changed

    def _require_mod(self, name: str) -> ModProfile:
        profile = self.get_mod_profile(name)
        if profile is None:
            raise ValueError(f"Mod profile not found: {name}")
        return profile

    def _save(self) -> None:
        write_json(
            self.path,
            {
                "mod_profiles": [profile.to_dict() for profile in self._mod_profiles],
                "server_profiles": [profile.to_dict() for profile in self._server_profiles],
            },
        )
