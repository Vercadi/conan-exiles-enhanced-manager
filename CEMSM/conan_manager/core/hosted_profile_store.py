"""Persistent hosted server profiles."""
from __future__ import annotations

from pathlib import Path

from ..models.hosted import HostedProfile
from ..utils.json_io import read_json, write_json


class HostedProfileStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "hosted_profiles.json"
        self._profiles: list[HostedProfile] = []
        self.load()

    def load(self) -> list[HostedProfile]:
        data = read_json(self.path)
        self._profiles = [
            HostedProfile.from_dict(item)
            for item in data.get("profiles", [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        return self.list_profiles()

    def save(self, profiles: list[HostedProfile]) -> None:
        deduped: dict[str, HostedProfile] = {}
        for profile in profiles:
            normalized = profile.normalized()
            deduped[normalized.name] = normalized
        self._profiles = list(deduped.values())
        write_json(self.path, {"profiles": [profile.to_dict() for profile in self._profiles]})

    def upsert(self, profile: HostedProfile) -> HostedProfile:
        normalized = profile.normalized()
        profiles = [item for item in self._profiles if item.name != normalized.name]
        profiles.append(normalized)
        self.save(profiles)
        return normalized

    def list_profiles(self) -> list[HostedProfile]:
        return list(self._profiles)

    def get(self, name: str) -> HostedProfile | None:
        for profile in self._profiles:
            if profile.name == name:
                return profile
        return None
