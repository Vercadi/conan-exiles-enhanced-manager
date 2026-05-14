"""Managed local mod library and archive import support."""
from __future__ import annotations

import hashlib
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..models.local_mod_library import (
    SOURCE_ARCHIVE,
    SOURCE_EXTERNAL_LINK,
    SOURCE_LOCAL_FILES,
    ModComponent,
    ModFile,
    ModLibraryState,
    ModSource,
)
from ..models.modlist import ActiveModEntry
from ..utils.filesystem import ensure_dir
from ..utils.json_io import read_json, write_json

COMPANION_SUFFIXES = {".ucas", ".utoc"}
IMPORT_HASH_BYTES = 1024 * 1024


@dataclass(frozen=True)
class PakFileGroup:
    pak_path: Path
    companion_paths: list[Path] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return normalize_mod_display_name(self.pak_path.stem)


@dataclass(frozen=True)
class ArchiveComponentCandidate:
    component_id: str
    display_name: str
    pak_member: str
    companion_members: list[str] = field(default_factory=list)
    variant_group_id: str = ""


@dataclass(frozen=True)
class ArchiveInspection:
    archive_path: Path
    components: list[ArchiveComponentCandidate]
    ambiguous: bool = False

    @property
    def requires_variant_choice(self) -> bool:
        return any(component.variant_group_id for component in self.components)

    @property
    def variant_group_ids(self) -> list[str]:
        return sorted({component.variant_group_id for component in self.components if component.variant_group_id})


class LocalModLibraryStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.library_path = data_dir / "local_mod_library.json"
        self.local_mods_dir = data_dir / "local_mods"
        self.archives_dir = data_dir / "archives"
        self.state = ModLibraryState.from_dict(read_json(self.library_path))

    def list_sources(self) -> list[ModSource]:
        return list(self.state.sources)

    def list_components(self) -> list[ModComponent]:
        return list(self.state.components)

    def component_by_id(self, component_id: str) -> ModComponent | None:
        for component in self.state.components:
            if component.component_id == component_id:
                return component
        return None

    def remove_components(self, component_ids: list[str]) -> int:
        ids = {str(value).strip() for value in component_ids if str(value).strip()}
        if not ids:
            return 0
        before = len(self.state.components)
        self.state.components = [component for component in self.state.components if component.component_id not in ids]
        for source in self.state.sources:
            source.component_ids = [component_id for component_id in source.component_ids if component_id not in ids]
        self.state.sources = [source for source in self.state.sources if source.component_ids]
        removed = before - len(self.state.components)
        if removed:
            self.save()
        return removed

    def remove_sources(self, source_ids: list[str]) -> int:
        ids = {str(value).strip() for value in source_ids if str(value).strip()}
        if not ids:
            return 0
        component_ids = {
            component_id
            for source in self.state.sources
            if source.source_id in ids
            for component_id in source.component_ids
        }
        before_sources = len(self.state.sources)
        self.state.sources = [source for source in self.state.sources if source.source_id not in ids]
        self.state.components = [component for component in self.state.components if component.component_id not in component_ids]
        removed = before_sources - len(self.state.sources)
        if removed:
            self.save()
        return removed

    def import_pak_files(self, paths: list[Path], *, link_external: bool = False) -> list[ModComponent]:
        groups = group_pak_files(paths)
        imported: list[ModComponent] = []
        for group in groups:
            if self._duplicate_for_pak(group.pak_path):
                continue
            source_id = _new_id("src")
            component_id = _new_id("mod")
            source_type = SOURCE_EXTERNAL_LINK if link_external else SOURCE_LOCAL_FILES
            source_dir = group.pak_path.parent if link_external else self.local_mods_dir / component_id
            ensure_dir(source_dir)
            primary = _file_record(
                group.pak_path if link_external else _copy_to_dir(group.pak_path, source_dir),
                role="pak",
                original_path=group.pak_path,
            )
            companions = [
                _file_record(
                    companion if link_external else _copy_to_dir(companion, source_dir),
                    role="companion",
                    original_path=companion,
                )
                for companion in group.companion_paths
            ]
            component = ModComponent(
                component_id=component_id,
                source_id=source_id,
                display_name=group.display_name,
                source_type=source_type,
                primary_file=primary,
                companion_files=companions,
            )
            source = ModSource(
                source_id=source_id,
                source_type=source_type,
                display_name=group.display_name,
                original_path=group.pak_path,
                managed_path=source_dir,
                component_ids=[component_id],
                size=primary.size,
                modified_time=primary.modified_time,
                sha256=primary.sha256,
            )
            self.state.sources.append(source)
            self.state.components.append(component)
            imported.append(component)
        self.save()
        return imported

    def inspect_archive(self, archive_path: Path) -> ArchiveInspection:
        return inspect_zip_archive(archive_path)

    def import_archive(self, archive_path: Path, *, selected_component_ids: list[str] | None = None) -> list[ModComponent]:
        inspection = self.inspect_archive(archive_path)
        selected = _validate_archive_selection(inspection, selected_component_ids)
        if not selected:
            return []

        source_id = _new_id("arc")
        archive_dir = self.archives_dir / source_id
        extracted_dir = archive_dir / "components"
        ensure_dir(extracted_dir)
        managed_archive = _copy_to_dir(archive_path, archive_dir)

        imported: list[ModComponent] = []
        component_ids: list[str] = []
        with zipfile.ZipFile(archive_path) as archive:
            for candidate in selected:
                component_id = _new_id("mod")
                component_dir = extracted_dir / component_id
                ensure_dir(component_dir)
                primary = _extract_member(archive, candidate.pak_member, component_dir, role="pak")
                companions = [
                    _extract_member(archive, member, component_dir, role="companion")
                    for member in candidate.companion_members
                ]
                component = ModComponent(
                    component_id=component_id,
                    source_id=source_id,
                    display_name=normalize_mod_display_name(candidate.display_name),
                    source_type=SOURCE_ARCHIVE,
                    primary_file=primary,
                    companion_files=companions,
                    variant_group_id=candidate.variant_group_id,
                    selected_variant=True,
                )
                imported.append(component)
                component_ids.append(component_id)

        source = ModSource(
            source_id=source_id,
            source_type=SOURCE_ARCHIVE,
            display_name=normalize_mod_display_name(archive_path.stem),
            original_path=archive_path,
            managed_path=managed_archive,
            component_ids=component_ids,
            size=managed_archive.stat().st_size,
            modified_time=managed_archive.stat().st_mtime,
            sha256=sha256_file(managed_archive),
        )
        self.state.sources.append(source)
        self.state.components.extend(imported)
        self.save()
        return imported

    def save(self) -> None:
        ensure_dir(self.data_dir)
        write_json(self.library_path, self.state.to_dict())

    def _duplicate_for_pak(self, pak_path: Path) -> bool:
        resolved = str(pak_path.resolve()).casefold() if pak_path.exists() else str(pak_path).casefold()
        filename = pak_path.name.casefold()
        for component in self.state.components:
            original = component.primary_file.original_path
            if original:
                original_key = str(original.resolve()).casefold() if original.exists() else str(original).casefold()
                if original_key == resolved:
                    return True
            if component.primary_file.path.name.casefold() == filename and component.primary_file.sha256 and pak_path.is_file():
                if component.primary_file.sha256 == sha256_file(pak_path):
                    return True
        return False


def component_to_active_entry(component: ModComponent) -> ActiveModEntry:
    return ActiveModEntry(
        value=str(component.primary_pak_path),
        display_name=component.display_name,
        source_type="archive_component" if component.source_type == SOURCE_ARCHIVE else (
            "external_link" if component.source_type == SOURCE_EXTERNAL_LINK else "managed_local"
        ),
        component_id=component.component_id,
        source_id=component.source_id,
        companion_paths=[str(path) for path in component.companion_paths],
        enabled=component.enabled,
    )


def group_pak_files(paths: list[Path]) -> list[PakFileGroup]:
    selected = [Path(path) for path in paths]
    by_key = {_path_key(path): path for path in selected}
    pak_paths = sorted({path for path in selected if path.suffix.casefold() == ".pak"}, key=lambda path: str(path))
    groups: list[PakFileGroup] = []
    for pak in pak_paths:
        companions: list[Path] = []
        for suffix in COMPANION_SUFFIXES:
            sibling = pak.with_suffix(suffix)
            selected_companion = by_key.get(_path_key(sibling))
            if selected_companion and selected_companion.is_file():
                companions.append(selected_companion)
            elif sibling.is_file():
                companions.append(sibling)
        companions.extend(
            path
            for path in selected
            if path.is_file()
            and path.suffix.casefold() not in {".pak", *COMPANION_SUFFIXES}
            and path.parent == pak.parent
            and path.stem.casefold() == pak.stem.casefold()
        )
        groups.append(PakFileGroup(pak_path=pak, companion_paths=sorted(set(companions), key=lambda path: path.name.casefold())))
    return groups


def inspect_zip_archive(archive_path: Path) -> ArchiveInspection:
    with zipfile.ZipFile(archive_path) as archive:
        members = [member for member in archive.namelist() if not member.endswith("/")]
    pak_members = sorted(member for member in members if PurePosixPath(member).suffix.casefold() == ".pak")
    member_lookup = {member.casefold(): member for member in members}
    components: list[ArchiveComponentCandidate] = []
    variant_groups = _variant_groups_for_members(pak_members)
    for pak_member in pak_members:
        pak_path = PurePosixPath(pak_member)
        companions: list[str] = []
        for suffix in COMPANION_SUFFIXES:
            companion = str(pak_path.with_suffix(suffix))
            found = member_lookup.get(companion.casefold())
            if found:
                companions.append(found)
        companions.extend(
            member
            for member in members
            if member.casefold() not in {pak_member.casefold(), *(companion.casefold() for companion in companions)}
            and PurePosixPath(member).suffix.casefold() != ".pak"
            and PurePosixPath(member).parent == pak_path.parent
            and PurePosixPath(member).stem.casefold() == pak_path.stem.casefold()
        )
        components.append(
            ArchiveComponentCandidate(
                component_id=_candidate_id(pak_member),
                display_name=normalize_mod_display_name(pak_path.stem),
                pak_member=pak_member,
                companion_members=companions,
                variant_group_id=variant_groups.get(pak_member, ""),
            )
        )
    ambiguous = len(components) > 1 and not any(component.variant_group_id for component in components)
    return ArchiveInspection(archive_path=archive_path, components=components, ambiguous=ambiguous)


def duplicate_component_keys(components: list[ModComponent]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for component in components:
        key = component.primary_file.path.name.casefold()
        if component.primary_file.sha256:
            key += ":" + component.primary_file.sha256
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return duplicates


def target_sync_labels(
    component: ModComponent,
    *,
    client_mods_dir: Path | None = None,
    server_mods_dir: Path | None = None,
) -> list[str]:
    labels: list[str] = []
    for label, mods_dir in (("Client", client_mods_dir), ("Server", server_mods_dir)):
        if not mods_dir:
            continue
        target = mods_dir / component.primary_file.path.name
        if target.is_file() and _same_size(target, component.primary_file.path):
            labels.append(f"Synced to {label}")
    return labels


def normalize_mod_display_name(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\.(zip|pak)$", "", text, flags=re.IGNORECASE)
    text = _strip_nexus_archive_suffix(text)
    text = text.replace("_", " ")
    text = re.sub(r"[-]+", " ", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "Unnamed mod"


def _strip_nexus_archive_suffix(value: str) -> str:
    parts = value.split("-")
    if len(parts) < 3:
        return value
    index = len(parts)
    while index > 0 and parts[index - 1].isdigit():
        index -= 1
    numeric_tail = parts[index:]
    if len(numeric_tail) >= 2 and len(numeric_tail[-1]) >= 8:
        return "-".join(parts[:index]).strip("- ") or value
    return value


def _same_size(left: Path, right: Path) -> bool:
    return left.is_file() and right.is_file() and left.stat().st_size == right.stat().st_size


def _validate_archive_selection(
    inspection: ArchiveInspection,
    selected_component_ids: list[str] | None,
) -> list[ArchiveComponentCandidate]:
    components = list(inspection.components)
    if not components:
        return []
    if selected_component_ids is None:
        if inspection.requires_variant_choice:
            raise ValueError("Archive contains variants; select exactly one option before importing.")
        return components

    selected_ids = set(selected_component_ids)
    selected = [component for component in components if component.component_id in selected_ids]
    for group_id in inspection.variant_group_ids:
        choices = [component for component in selected if component.variant_group_id == group_id]
        if len(choices) != 1:
            raise ValueError(f"Variant group {group_id} requires exactly one selected option.")
    return selected


def _variant_groups_for_members(pak_members: list[str]) -> dict[str, str]:
    groups: dict[str, list[str]] = {}
    for member in pak_members:
        parts = PurePosixPath(member).parts
        lowered = [part.casefold() for part in parts]
        marker_index = next(
            (index for index, part in enumerate(lowered) if "variant" in part or "option" in part),
            None,
        )
        if marker_index is None:
            continue
        group_id = "/".join(parts[: marker_index + 1])
        groups.setdefault(group_id, []).append(member)
    return {member: group_id for group_id, members in groups.items() if len(members) > 1 for member in members}


def _extract_member(archive: zipfile.ZipFile, member: str, dest_dir: Path, *, role: str) -> ModFile:
    target = _dedupe_path(dest_dir / PurePosixPath(member).name)
    with archive.open(member) as source, target.open("wb") as handle:
        shutil.copyfileobj(source, handle)
    return _file_record(target, role=role, original_path=None)


def _copy_to_dir(source: Path, dest_dir: Path) -> Path:
    ensure_dir(dest_dir)
    destination = _dedupe_path(dest_dir / source.name)
    shutil.copy2(source, destination)
    return destination


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _file_record(path: Path, *, role: str, original_path: Path | None) -> ModFile:
    return ModFile(
        path=path,
        role=role,
        original_path=original_path,
        size=path.stat().st_size if path.is_file() else 0,
        modified_time=path.stat().st_mtime if path.is_file() else 0.0,
        sha256=sha256_file(path) if path.is_file() else "",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(IMPORT_HASH_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_id(member: str) -> str:
    return hashlib.sha1(member.encode("utf-8")).hexdigest()[:16]


def _path_key(path: Path) -> str:
    return str(path).replace("\\", "/").casefold()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
