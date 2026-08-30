from __future__ import annotations

import json
import re
from typing import Any

from .models import AgentPlan, ActionSpec, Risk

ALLOWED_MODES = {"plan", "preview", "execute"}
ALLOWED_ON_ERROR = {"stop_and_report", "continue"}
_REF = re.compile(r"^\$(action_[A-Za-z0-9_-]+)\.result\.([A-Za-z0-9_]+)$")


def _clean_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_plan(text: str, guild_id: int) -> AgentPlan:
    try:
        data = json.loads(_clean_json(text))
    except json.JSONDecodeError as exc:
        raise ValueError("A IA não retornou um JSON válido.") from exc

    if not isinstance(data, dict):
        raise ValueError("O plano precisa ser um objeto JSON.")
    if data.get("version") != 1:
        raise ValueError("Versão de plano não suportada.")

    mode = str(data.get("mode", "plan"))
    if mode not in ALLOWED_MODES:
        raise ValueError("Modo de plano inválido.")
    if str(data.get("guild_id")) != str(guild_id):
        raise ValueError("O plano aponta para outro servidor.")

    reason = str(data.get("reason", "")).strip()
    if not reason:
        raise ValueError("O plano precisa informar o motivo.")

    raw_checks = data.get("checks", [])
    raw_actions = data.get("actions", [])
    if not isinstance(raw_checks, list):
        raise ValueError("checks precisa ser uma lista.")
    if not isinstance(raw_actions, list):
        raise ValueError("actions precisa ser uma lista.")

    actions: list[ActionSpec] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_actions, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"action {index} precisa ser um objeto.")

        action_id = str(raw.get("id", f"action_{index}"))
        if action_id in seen_ids:
            raise ValueError(f"ID de ação duplicado: {action_id}")
        seen_ids.add(action_id)

        risk = Risk(str(raw.get("risk", "low")))
        requires = bool(raw.get("requires_confirmation", risk != Risk.LOW))
        actions.append(
            ActionSpec(
                id=action_id,
                type=str(raw.get("type", "")),
                target=dict(raw.get("target") or {}),
                input=dict(raw.get("input") or {}),
                risk=risk,
                requires_confirmation=requires,
            )
        )

    execution = dict(data.get("execution") or {})
    on_error = str(execution.get("on_error", "stop_and_report"))
    if on_error not in ALLOWED_ON_ERROR:
        raise ValueError("execution.on_error inválido.")

    return AgentPlan(
        version=1,
        mode=mode,
        guild_id=guild_id,
        reason=reason,
        checks=tuple(str(item) for item in raw_checks),
        actions=tuple(actions),
        on_error=on_error,
        dry_run=bool(execution.get("dry_run", True)),
        audit_reason=str(execution.get("audit_reason", reason)),
    )


def resolve_refs(value: Any, results: dict[str, dict[str, Any]]) -> Any:
    """Resolve $action_X.result.field references after previous actions run."""
    if isinstance(value, str):
        match = _REF.match(value)
        if not match:
            return value

        action_id, field = match.groups()
        if action_id not in results:
            raise ValueError(f"Resultado de {action_id} ainda não existe.")
        if field not in results[action_id]:
            raise ValueError(f"Campo {field} não existe no resultado de {action_id}.")
        return results[action_id][field]

    if isinstance(value, dict):
        return {
            key: resolve_refs(item, results)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [resolve_refs(item, results) for item in value]

    return value
