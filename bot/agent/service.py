from __future__ import annotations

import json
from typing import Any

import discord

from ..ai.client import AIClient, AIConfig
from .discord_tools import execute_action
from .plan import AgentPlan, parse_plan, resolve_refs
from .prompt import build_prompt, SYSTEM_PROMPT
from .validator import validate_plan


class AgentService:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    @staticmethod
    def guild_context(guild: discord.Guild) -> str:
        channels = [
            f"{c.id}:{c.name}:{c.__class__.__name__}:parent={getattr(c, 'category_id', None)}"
            for c in guild.channels[:200]
        ]
        roles = [f"{r.id}:{r.name}:pos={r.position}" for r in guild.roles[-100:]]
        return (
            f"name={guild.name!r}\nmembers={guild.member_count or 0}\n"
            "channels:\n" + "\n".join(channels) + "\nroles:\n" + "\n".join(roles)
        )

    def _global_fallback(self) -> tuple[str, str, str] | None:
        settings = getattr(self.bot, "settings", None)
        if settings is None or not settings.ai_api_key:
            return None
        return (
            settings.ai_api_key,
            settings.ai_base_url or "https://openrouter.ai/api/v1",
            settings.ai_model or "openrouter/free",
        )

    async def generate_plan(self, guild: discord.Guild, request: str) -> AgentPlan:
        config = await self.bot.db.get_ai_config(guild.id)
        if config is None:
            config = self._global_fallback()
        if config is None:
            raise RuntimeError(
                "Este servidor ainda não configurou uma IA. Use `/configia`."
            )

        api_key, base_url, model = config
        client = AIClient(AIConfig(api_key=api_key, base_url=base_url, model=model))
        user_prompt = build_prompt(self.guild_context(guild), request, guild.id)
        raw = await client.chat(SYSTEM_PROMPT, user_prompt, temperature=0.1)
        plan = parse_plan(raw, guild.id)
        validate_plan(plan)
        return plan

    async def execute(
        self, guild: discord.Guild, user_id: int, plan: AgentPlan
    ) -> list[dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        report: list[dict[str, Any]] = []

        for action in plan.actions:
            target = resolve_refs(action.target, results)
            inputs = resolve_refs(action.input, results)
            try:
                value = await execute_action(guild, action.type, target, inputs)
                results[action.id] = dict(value)
                report.append(
                    {
                        "id": action.id,
                        "type": action.type,
                        "status": "executed",
                        "result": value,
                    }
                )
                await self.bot.db.log_action(
                    guild.id,
                    user_id,
                    action.type,
                    action.risk,
                    "executed",
                    json.dumps(value, ensure_ascii=False, default=str),
                )
            except Exception as exc:
                report.append(
                    {
                        "id": action.id,
                        "type": action.type,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                await self.bot.db.log_action(
                    guild.id,
                    user_id,
                    action.type,
                    action.risk,
                    "failed",
                    str(exc),
                )
                if plan.on_error == "stop_and_report":
                    break
        return report


def action_line(action) -> str:
    flag = " ⚠️ confirmação" if action.requires_confirmation else ""
    return f"`{action.id}` · `{action.type}` · risco `{action.risk}`{flag}"


def preview_text(plan: AgentPlan) -> str:
    lines = [
        f"**Motivo:** {plan.reason}",
        f"**Modo:** `{plan.mode}` · **dry_run:** `{plan.dry_run}`",
        "**Checks:** " + (", ".join(plan.checks) if plan.checks else "nenhum informado"),
        "**Ações:**",
    ]
    lines.extend(f"{i}. {action_line(a)}" for i, a in enumerate(plan.actions, 1))
    return "\n".join(lines)
