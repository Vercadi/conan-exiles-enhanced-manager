from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiTokens:
    name: str
    page_title: int
    title: int
    card_title: int
    row_title: int
    body: int
    small: int
    mono: int
    button_height: int
    compact_button_height: int
    panel_wrap: int


def ui_tokens_for_size(size_name: str) -> UiTokens:
    size = (size_name or "default").strip().lower()
    if size == "compact":
        return UiTokens(
            name="compact",
            page_title=18,
            title=16,
            card_title=12,
            row_title=11,
            body=11,
            small=10,
            mono=10,
            button_height=28,
            compact_button_height=24,
            panel_wrap=440,
        )
    if size == "large":
        return UiTokens(
            name="large",
            page_title=22,
            title=20,
            card_title=14,
            row_title=13,
            body=13,
            small=12,
            mono=12,
            button_height=36,
            compact_button_height=30,
            panel_wrap=580,
        )
    return UiTokens(
        name="default",
        page_title=20,
        title=18,
        card_title=13,
        row_title=12,
        body=12,
        small=11,
        mono=11,
        button_height=32,
        compact_button_height=26,
        panel_wrap=520,
    )
