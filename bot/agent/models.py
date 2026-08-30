from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionStatus(StrEnum):
    PLANNED = "planned"
    APPROVED = "approved"
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class Action:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    risk: Risk = Risk.LOW


@dataclass(slots=True, frozen=True)
class Plan:
    reason: str
    actions: tuple[Action, ...]
    requires_confirmation: bool

    @classmethod
    def from_actions(cls, reason: str, actions: list[Action]) -> "Plan":
        return cls(
            reason=reason,
            actions=tuple(actions),
            requires_confirmation=any(
                action.risk in {Risk.MEDIUM, Risk.HIGH} for action in actions
            ),
        )
