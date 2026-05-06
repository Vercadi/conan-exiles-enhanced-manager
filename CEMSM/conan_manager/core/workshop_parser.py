"""Steam Workshop URL/ID parsing."""
from __future__ import annotations

import re

from ..models.workshop import WorkshopParseResult

UINT64_MAX = 18446744073709551615
ID_PARAM_RE = re.compile(r"(?:[?&]id=|id=)(\d+)", re.IGNORECASE)
TOKEN_SPLIT_RE = re.compile(r"[\s,;]+")


def parse_workshop_ids(text: str) -> WorkshopParseResult:
    """Parse bare Workshop IDs and Steam Workshop URLs while preserving order."""
    result = WorkshopParseResult()
    seen: set[str] = set()
    for token in _tokens(text):
        workshop_id = _id_from_token(token)
        if workshop_id is None:
            result.invalid_tokens.append(token)
            continue
        if workshop_id not in seen:
            result.ids.append(workshop_id)
            seen.add(workshop_id)
    return result


def _tokens(text: str) -> list[str]:
    normalized = str(text or "").strip()
    if not normalized:
        return []
    return [token.strip() for token in TOKEN_SPLIT_RE.split(normalized) if token.strip()]


def _id_from_token(token: str) -> str | None:
    match = ID_PARAM_RE.search(token)
    candidate = match.group(1) if match else token
    if not candidate.isdigit():
        return None
    if int(candidate) > UINT64_MAX:
        return None
    return candidate
