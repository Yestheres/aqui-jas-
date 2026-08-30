from __future__ import annotations

import logging
from typing import Any

from .models import Action, ActionStatus, Plan, Risk
from .tools import ToolRegistry

log = logging.getLogger(__name__)


class ExecutionError(RuntimeError):
    pass


class Executor:
    """Executes already-validated actions. It never interprets natural language."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute(self, plan: Plan, *, confirmed: bool = False) -> list[tuple[Action, ActionStatus, Any]]:
        if plan.requires_confirmation and not confirmed:
            raise ExecutionError("This plan requires confirmation before execution.")

        results: list[tuple[Action, ActionStatus, Any]] = []
        for action in plan.actions:
            tool = self.registry.get(action.tool)
            if tool.risk != action.risk:
                raise ExecutionError(f"Risk mismatch for tool {action.tool}.")
            try:
                value = await tool.callback(**action.arguments)
            except Exception as exc:
                log.exception("Tool %s failed", action.tool)
                results.append((action, ActionStatus.FAILED, exc))
                raise ExecutionError(f"Tool {action.tool} failed.") from exc
            results.append((action, ActionStatus.EXECUTED, value))
        return results
