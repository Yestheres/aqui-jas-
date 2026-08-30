from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .models import Risk

ToolCallback = Callable[..., Awaitable[Any]]


@dataclass(slots=True, frozen=True)
class Tool:
    name: str
    description: str
    risk: Risk
    callback: ToolCallback


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)
