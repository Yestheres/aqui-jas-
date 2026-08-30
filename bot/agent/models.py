"""Backward-compatible Agent models.

Kept intentionally small so older deployments/import paths do not crash while
all new execution logic lives in plan.py/validator.py/service.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True)
class ActionSpec:
    id: str
    type: str
    target: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] = field(default_factory=dict)
    risk: str = "low"
    requires_confirmation: bool = False


@dataclass(slots=True)
class AgentPlan:
    version: int
    mode: str
    guild_id: int
    reason: str
    checks: list[str]
    actions: list[ActionSpec]
    on_error: str = "stop_and_report"
    dry_run: bool = True
    audit_reason: str = ""

    @property
    def requires_confirmation(self) -> bool:
        return any(action.requires_confirmation for action in self.actions)
