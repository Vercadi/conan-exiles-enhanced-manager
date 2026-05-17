"""Public Steam Workshop metadata lookup."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONAN_WORKSHOP_APP_ID = 440900
STEAM_PUBLISHED_FILE_DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"


class WorkshopMetadataError(RuntimeError):
    """Raised when the public Steam metadata endpoint cannot be read."""


@dataclass(frozen=True)
class WorkshopMetadata:
    workshop_id: str
    title: str = ""
    file_size: int = 0
    time_updated: int = 0
    consumer_app_id: int = 0
    creator_app_id: int = 0
    preview_url: str = ""
    tags: list[str] = field(default_factory=list)
    result: int = 0
    fetched_at: float = 0.0
    warning: str = ""

    @property
    def ok(self) -> bool:
        return self.result == 1


def build_published_file_details_payload(workshop_ids: list[str]) -> str:
    ids = _clean_workshop_ids(workshop_ids)
    pairs: list[tuple[str, str]] = [("itemcount", str(len(ids))), ("format", "json")]
    pairs.extend((f"publishedfileids[{index}]", workshop_id) for index, workshop_id in enumerate(ids))
    return urlencode(pairs)


def fetch_workshop_metadata(
    workshop_ids: list[str],
    *,
    timeout: float = 8.0,
    request_opener: Callable[..., Any] | None = None,
) -> list[WorkshopMetadata]:
    ids = _clean_workshop_ids(workshop_ids)
    if not ids:
        return []
    payload = build_published_file_details_payload(ids).encode("utf-8")
    request = Request(
        STEAM_PUBLISHED_FILE_DETAILS_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    opener = request_opener or urlopen
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read()
    except Exception as exc:  # pragma: no cover - exact network exception types vary by platform
        raise WorkshopMetadataError(f"Steam Workshop metadata request failed: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise WorkshopMetadataError(f"Steam Workshop metadata response was not valid JSON: {exc}") from exc
    return parse_published_file_details_response(data, fetched_at=time.time())


def parse_published_file_details_response(data: dict[str, Any], *, fetched_at: float | None = None) -> list[WorkshopMetadata]:
    response = data.get("response") if isinstance(data, dict) else None
    details = response.get("publishedfiledetails") if isinstance(response, dict) else None
    if not isinstance(details, list):
        return []
    timestamp = time.time() if fetched_at is None else float(fetched_at)
    return [_metadata_from_detail(detail, timestamp) for detail in details if isinstance(detail, dict)]


def _metadata_from_detail(detail: dict[str, Any], fetched_at: float) -> WorkshopMetadata:
    workshop_id = str(detail.get("publishedfileid") or "").strip()
    consumer_app_id = _safe_int(detail.get("consumer_app_id"))
    warning = ""
    if consumer_app_id and consumer_app_id != CONAN_WORKSHOP_APP_ID:
        warning = f"Workshop item belongs to app {consumer_app_id}, expected {CONAN_WORKSHOP_APP_ID}."
    return WorkshopMetadata(
        workshop_id=workshop_id,
        title=str(detail.get("title") or "").strip(),
        file_size=_safe_int(detail.get("file_size")),
        time_updated=_safe_int(detail.get("time_updated")),
        consumer_app_id=consumer_app_id,
        creator_app_id=_safe_int(detail.get("creator_app_id")),
        preview_url=str(detail.get("preview_url") or ""),
        tags=[str(item.get("tag") or "") for item in detail.get("tags", []) if isinstance(item, dict) and item.get("tag")],
        result=_safe_int(detail.get("result")),
        fetched_at=fetched_at,
        warning=warning,
    )


def _clean_workshop_ids(workshop_ids: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in workshop_ids:
        workshop_id = str(value or "").strip()
        if not workshop_id or not workshop_id.isdigit() or workshop_id in seen:
            continue
        cleaned.append(workshop_id)
        seen.add(workshop_id)
    return cleaned


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
