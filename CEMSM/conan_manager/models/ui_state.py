from __future__ import annotations

from dataclasses import dataclass


BANNER_INFO = "info"
BANNER_SUCCESS = "success"
BANNER_WARNING = "warning"
BANNER_ERROR = "error"
BANNER_KINDS = (BANNER_INFO, BANNER_SUCCESS, BANNER_WARNING, BANNER_ERROR)


@dataclass(frozen=True)
class BannerState:
    kind: str = BANNER_INFO
    message: str = ""
    visible: bool = False

    def normalized(self) -> "BannerState":
        kind = self.kind if self.kind in BANNER_KINDS else BANNER_INFO
        message = str(self.message or "").strip()
        return BannerState(kind=kind, message=message, visible=bool(message and self.visible))

    @property
    def colors(self) -> tuple[str, str]:
        state = self.normalized()
        if state.kind == BANNER_SUCCESS:
            return "#183a26", "#74ad7f"
        if state.kind == BANNER_WARNING:
            return "#3a2a14", "#c98a2e"
        if state.kind == BANNER_ERROR:
            return "#3a1717", "#d06b61"
        return "#172533", "#7aa4c7"


def banner(kind: str, message: str) -> BannerState:
    return BannerState(kind=kind, message=message, visible=True).normalized()
