from __future__ import annotations

from .catalog import tool_catalog_text

SYSTEM_PROMPT = """Você é o planejador de ações do Aqui Jas.
Nunca execute ações. Sua única saída é um JSON válido, sem markdown e sem texto adicional.
Regras: version=1; mode=plan; guild_id exato; IDs como alvo principal; category via create_channel+channel_type=category; slowmode via rate_limit_per_user; referências $action_X.result.campo; ações perigosas risk=high e requires_confirmation=true; criação idempotente; checks de resolução/permissão/hierarquia/conflito/preview quando pertinentes; somente catálogo; execution.on_error=stop_and_report e dry_run=true por padrão.
Catálogo disponível:
""" + tool_catalog_text()


def build_prompt(guild_context: str, request: str, guild_id: int) -> str:
    return (
        f"CONTEXTO DO SERVIDOR (somente leitura):\n{guild_context}\n\n"
        f"GUILD_ID: {guild_id}\n"
        f"PEDIDO DO USUÁRIO: {request}\n\n"
        "Retorne somente um objeto JSON com version, mode, guild_id, reason, checks, actions e execution."
    )
