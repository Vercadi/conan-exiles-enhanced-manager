from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModNote:
    key: str
    display_name: str = ""
    source_type: str = ""
    text: str = ""
    workshop_id: str = ""
    component_id: str = ""
    source_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "source_type": self.source_type,
            "text": self.text,
            "workshop_id": self.workshop_id,
            "component_id": self.component_id,
            "source_id": self.source_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModNote":
        return cls(
            key=str(data.get("key") or ""),
            display_name=str(data.get("display_name") or ""),
            source_type=str(data.get("source_type") or ""),
            text=str(data.get("text") or ""),
            workshop_id=str(data.get("workshop_id") or ""),
            component_id=str(data.get("component_id") or ""),
            source_id=str(data.get("source_id") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )
