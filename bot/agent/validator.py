from __future__ import annotations

import re
from typing import Any

from .catalog import required_risk
from .plan import AgentPlan

_REF = re.compile(r"^\$(action_[A-Za-z0-9_-]+)\.result\.([A-Za-z0-9_]+)$")


class PlanValidationError(ValueError):
    pass


def _scan_refs(value: Any, action_ids: set[str]) -> None:
    if isinstance(value, str):
        match = _REF.match(value)
        if match and match.group(1) not in action_ids:
            raise PlanValidationError(f"Referência para ação inexistente: {match.group(1)}")
    elif isinstance(value, dict):
        for item in value.values():
            _scan_refs(item, action_ids)
    elif isinstance(value, list):
        for item in value:
            _scan_refs(item, action_ids)


def validate_plan(plan: AgentPlan) -> None:
    if len(plan.actions) > 25:
        raise PlanValidationError("O plano excede o limite de 25 ações.")
    ids = {action.id for action in plan.actions}
    for action in plan.actions:
        if not action.type:
            raise PlanValidationError(f"Ação {action.id} não possui type.")
        if required_risk(action.type) == "high" and action.risk != "high":
            raise PlanValidationError(
                f"Ação perigosa {action.type} precisa ser classificada como high."
            )
        if action.risk in {"medium", "high"} and not action.requires_confirmation:
            raise PlanValidationError(f"Ação {action.id} exige confirmação.")
        _scan_refs(action.target, ids)
        _scan_refs(action.input, ids)


def resolve_refs(value: Any, results: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, str):
        match = _REF.match(value)
        if not match:
            return value
        action_id, field = match.groups()
        if action_id not in results:
            raise PlanValidationError(f"Resultado de {action_id} ainda não existe.")
        if field not in results[action_id]:
            raise PlanValidationError(f"Campo {field} não existe no resultado de {action_id}.")
        return results[action_id][field]
    if isinstance(value, dict):
        return {key: resolve_refs(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_refs(item, results) for item in value]
    return value
