from __future__ import annotations

import re
from typing import Any

from .catalog import ACTION_DESCRIPTIONS, required_risk
from .plan import AgentPlan

_REF = re.compile(r"^\$(action_[A-Za-z0-9_-]+)\.result\.([A-Za-z0-9_]+)$")


class PlanValidationError(ValueError):
    pass


def _scan_refs(value: Any, action_index: dict[str, int], current_index: int) -> None:
    if isinstance(value, str):
        match = _REF.match(value)
        if match:
            action_id = match.group(1)
            if action_id not in action_index:
                raise PlanValidationError(
                    f"Referência para ação inexistente: {action_id}"
                )
            if action_index[action_id] >= current_index:
                raise PlanValidationError(
                    f"Ação {action_id} precisa aparecer antes da ação que a referencia."
                )
    elif isinstance(value, dict):
        for item in value.values():
            _scan_refs(item, action_index, current_index)
    elif isinstance(value, list):
        for item in value:
            _scan_refs(item, action_index, current_index)


def validate_plan(plan: AgentPlan) -> None:
    if plan.version != 1:
        raise PlanValidationError("Versão de plano não suportada.")
    if plan.mode not in {"plan", "preview"}:
        raise PlanValidationError("A IA só pode produzir planos em modo plan/preview.")
    if not plan.reason.strip():
        raise PlanValidationError("O plano precisa informar o motivo.")
    if len(plan.actions) > 25:
        raise PlanValidationError("O plano excede o limite de 25 ações.")

    action_index = {action.id: index for index, action in enumerate(plan.actions)}
    if len(action_index) != len(plan.actions):
        raise PlanValidationError("IDs de ações precisam ser únicos.")

    for index, action in enumerate(plan.actions):
        if action.type not in ACTION_DESCRIPTIONS:
            raise PlanValidationError(f"Ação não permitida: {action.type}")
        minimum = required_risk(action.type)
        if minimum == "high" and action.risk != "high":
            raise PlanValidationError(
                f"Ação perigosa {action.type} precisa ser classificada como high."
            )
        if action.risk in {"medium", "high"} and not action.requires_confirmation:
            raise PlanValidationError(
                f"Ação {action.id} exige confirmação explícita."
            )
        _scan_refs(action.target, action_index, index)
        _scan_refs(action.input, action_index, index)


def resolve_refs(value: Any, results: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, str):
        match = _REF.match(value)
        if not match:
            return value
        action_id, field = match.groups()
        if action_id not in results:
            raise PlanValidationError(
                f"Resultado de {action_id} ainda não existe."
            )
        if field not in results[action_id]:
            raise PlanValidationError(
                f"Campo {field} não existe no resultado de {action_id}."
            )
        return results[action_id][field]

    if isinstance(value, dict):
        return {key: resolve_refs(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_refs(item, results) for item in value]
    return value
