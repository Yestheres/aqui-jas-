from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

ALLOWED_RISKS = {"low", "medium", "high"}
ALLOWED_MODES = {"plan", "preview"}
ALLOWED_ON_ERROR = {"stop_and_report", "continue"}
_REF = re.compile(r"^\$(action_[A-Za-z0-9_-]+)\.result\.([A-Za-z0-9_]+)$")


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


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_plan(text: str, guild_id: int) -> AgentPlan:
    try:
        data = json.loads(_clean_json(text))
    except json.JSONDecodeError as exc:
        raise ValueError("A IA não retornou um JSON válido.") from exc

    if not isinstance(data, dict):
        raise ValueError("O plano da IA precisa ser um objeto JSON.")
    if data.get("version") != 1:
        raise ValueError("Versão de plano não suportada.")

    mode = str(data.get("mode", "plan"))
    if mode not in ALLOWED_MODES:
        raise ValueError("Modo de plano inválido.")

    if str(data.get("guild_id", guild_id)) != str(guild_id):
        raise ValueError("O plano aponta para outro servidor.")

    reason = str(data.get("reason", "")).strip()
    if not reason:
        raise ValueError("O plano precisa informar o motivo.")

    raw_checks = data.get("checks", [])
    if not isinstance(raw_checks, list):
        raise ValueError("checks precisa ser uma lista.")

    raw_actions = data.get("actions", [])
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

        risk = str(raw.get("risk", "low"))
        if risk not in ALLOWED_RISKS:
            raise ValueError(f"Risco inválido em {action_id}.")

        target = raw.get("target") or {}
        input_data = raw.get("input") or {}
        if not isinstance(target, dict) or not isinstance(input_data, dict):
            raise ValueError(f"target/input de {action_id} precisam ser objetos.")

        actions.append(
            ActionSpec(
                id=action_id,
                type=str(raw.get("type", "")),
                target=dict(target),
                input=dict(input_data),
                risk=risk,
                requires_confirmation=bool(
                    raw.get("requires_confirmation", risk in {"medium", "high"})
                ),
            )
        )

    execution = data.get("execution") or {}
    if not isinstance(execution, dict):
        raise ValueError("execution precisa ser um objeto.")

    on_error = str(execution.get("on_error", "stop_and_report"))
    if on_error not in ALLOWED_ON_ERROR:
        raise ValueError("execution.on_error inválido.")

    return AgentPlan(
        version=1,
        mode=mode,
        guild_id=guild_id,
        reason=reason,
        checks=[str(item) for item in raw_checks],
        actions=actions,
        on_error=on_error,
        dry_run=bool(execution.get("dry_run", True)),
        audit_reason=str(execution.get("audit_reason", reason)),
    )


def resolve_refs(value: Any, results: dict[str, dict[str, Any]]) -> Any:
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
        return {key: resolve_refs(item, results) for key, item in value.items()}

    if isinstance(value, list):
        return [resolve_refs(item, results) for item in value]

    return value
