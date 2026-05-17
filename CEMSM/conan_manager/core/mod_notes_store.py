"""Persistent per-mod notes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..models.local_mod_library import ModComponent
from ..models.mod_notes import ModNote
from ..models.modlist import ActiveModEntry
from ..models.workshop import WorkshopItem
from ..utils.json_io import read_json, write_json


@dataclass(frozen=True)
class NoteSubject:
    key: str
    display_name: str
    source_type: str
    workshop_id: str = ""
    component_id: str = ""
    source_id: str = ""
    active: bool = False


class ModNotesStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "mod_notes.json"
        self._notes: dict[str, ModNote] = {}
        self.load()

    def load(self) -> list[ModNote]:
        data = read_json(self.path)
        notes = [
            ModNote.from_dict(item)
            for item in data.get("notes", [])
            if isinstance(item, dict) and str(item.get("key") or "").strip()
        ]
        self._notes = {note.key: note for note in notes}
        return self.list_notes()

    def save(self) -> None:
        ordered = sorted(self._notes.values(), key=lambda note: note.updated_at or note.created_at, reverse=True)
        write_json(self.path, {"notes": [note.to_dict() for note in ordered]})

    def list_notes(self) -> list[ModNote]:
        return list(self._notes.values())

    def get(self, key: str) -> ModNote | None:
        return self._notes.get(str(key or ""))

    def note_count(self) -> int:
        return sum(1 for note in self._notes.values() if note.text.strip())

    def upsert(self, subject: NoteSubject, text: str) -> ModNote:
        key = subject.key
        now = _now()
        existing = self._notes.get(key)
        note = ModNote(
            key=key,
            display_name=subject.display_name,
            source_type=subject.source_type,
            text=str(text or ""),
            workshop_id=subject.workshop_id,
            component_id=subject.component_id,
            source_id=subject.source_id,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._notes[key] = note
        self.save()
        return note

    def clear(self, key: str) -> bool:
        note = self._notes.get(key)
        if note is None or not note.text:
            return False
        note.text = ""
        note.updated_at = _now()
        self.save()
        return True

    def migrate_existing_notes(
        self,
        *,
        active_mods: list[ActiveModEntry],
        components: list[ModComponent],
        workshop_items: list[WorkshopItem],
    ) -> int:
        subjects = subjects_for_mods(active_mods=active_mods, components=components, workshop_items=workshop_items)
        by_key = {subject.key: subject for subject in subjects}
        migrated = 0
        for entry in active_mods:
            if _should_migrate_note(entry.notes):
                key = note_key_for_active_entry(entry)
                subject = by_key.get(key) or NoteSubject(
                    key=key,
                    display_name=entry.display_name or Path(entry.value).stem,
                    source_type=entry.source_type,
                    workshop_id=entry.workshop_id or "",
                    component_id=entry.component_id,
                    source_id=entry.source_id,
                    active=True,
                )
                migrated += self._migrate_note(subject, entry.notes)
        for component in components:
            if _should_migrate_note(component.notes):
                subject = by_key.get(note_key_for_component(component)) or NoteSubject(
                    key=note_key_for_component(component),
                    display_name=component.display_name,
                    source_type=component.source_type,
                    component_id=component.component_id,
                    source_id=component.source_id,
                )
                migrated += self._migrate_note(subject, component.notes)
        if migrated:
            self.save()
        return migrated

    def _migrate_note(self, subject: NoteSubject, text: str) -> int:
        existing = self._notes.get(subject.key)
        if existing and existing.text.strip():
            return 0
        now = _now()
        self._notes[subject.key] = ModNote(
            key=subject.key,
            display_name=subject.display_name,
            source_type=subject.source_type,
            text=text,
            workshop_id=subject.workshop_id,
            component_id=subject.component_id,
            source_id=subject.source_id,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        return 1


def subjects_for_mods(
    *,
    active_mods: list[ActiveModEntry],
    components: list[ModComponent],
    workshop_items: list[WorkshopItem],
) -> list[NoteSubject]:
    active_keys = {note_key_for_active_entry(entry) for entry in active_mods}
    subjects: dict[str, NoteSubject] = {}
    for item in workshop_items:
        key = note_key_for_workshop(item.workshop_id)
        subjects[key] = NoteSubject(
            key=key,
            display_name=item.display_title,
            source_type="workshop",
            workshop_id=item.workshop_id,
            active=key in active_keys,
        )
    for component in components:
        key = note_key_for_component(component)
        subjects[key] = NoteSubject(
            key=key,
            display_name=component.display_name,
            source_type=component.source_type,
            component_id=component.component_id,
            source_id=component.source_id,
            active=key in active_keys,
        )
    for entry in active_mods:
        key = note_key_for_active_entry(entry)
        subjects[key] = NoteSubject(
            key=key,
            display_name=entry.display_name or Path(entry.value).stem or "Unnamed mod",
            source_type=entry.source_type,
            workshop_id=entry.workshop_id or "",
            component_id=entry.component_id,
            source_id=entry.source_id,
            active=True,
        )
    return sorted(subjects.values(), key=lambda subject: subject.display_name.casefold())


def filter_note_subjects(
    subjects: list[NoteSubject],
    notes: list[ModNote],
    filter_value: str,
) -> list[NoteSubject]:
    note_keys = {note.key for note in notes if note.text.strip()}
    if filter_value == "In Active Load Order":
        return [subject for subject in subjects if subject.active]
    if filter_value == "Has Notes":
        return [subject for subject in subjects if subject.key in note_keys]
    return list(subjects)


def note_key_for_active_entry(entry: ActiveModEntry) -> str:
    if entry.workshop_id:
        return note_key_for_workshop(entry.workshop_id)
    if entry.component_id:
        return f"component:{entry.component_id}"
    return f"path:{_path_key(entry.value)}"


def note_key_for_component(component: ModComponent) -> str:
    return f"component:{component.component_id}"


def note_key_for_workshop(workshop_id: str) -> str:
    return f"workshop:{str(workshop_id or '').strip()}"


def _path_key(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").casefold()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _should_migrate_note(text: str) -> bool:
    stripped = str(text or "").strip()
    return bool(stripped and stripped != "Enhanced compatibility unknown")
