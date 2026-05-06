"""Testable lazy-tab construction state."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LazyTabController:
    factories: dict[str, Callable[[], Any]]
    constructed: dict[str, Any] = field(default_factory=dict)

    def ensure(self, name: str) -> Any:
        if name in self.constructed:
            return self.constructed[name]
        if name not in self.factories:
            raise KeyError(f"No tab factory registered for {name}")
        value = self.factories[name]()
        self.constructed[name] = value
        return value

    def is_constructed(self, name: str) -> bool:
        return name in self.constructed
