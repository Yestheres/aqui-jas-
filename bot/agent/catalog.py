from __future__ import annotations

# V1 deliberately excludes member moderation from the AI tool catalog.
# Direct moderation commands can be introduced in V3 with their own policy layer.
DANGEROUS_ACTIONS = {
    "delete_channel",
    "delete_role",
    "set_channel_permissions",
    "update_role_permissions",
    "update_guild",
    "delete_message",
}

IDEMPOTENT_ACTIONS = {
    "create_channel",
    "create_role",
    "assign_role",
    "remove_role",
    "move_channel",
    "update_channel",
    "set_channel_permissions",
    "sync_channel_permissions",
}

ACTION_DESCRIPTIONS: dict[str, str] = {
    "create_channel": "Cria canal ou categoria (channel_type: category/text/voice).",
    "update_channel": "Atualiza nome, tópico, slowmode ou NSFW de um canal.",
    "delete_channel": "Exclui um canal ou categoria.",
    "move_channel": "Move um canal para outra categoria.",
    "reorder_channels": "Reordena canais por posição.",
    "set_channel_permissions": "Altera permissões de um canal para um alvo.",
    "sync_channel_permissions": "Sincroniza permissões de um canal com a categoria.",
    "create_role": "Cria um cargo.",
    "update_role": "Atualiza nome, cor ou menção de um cargo.",
    "delete_role": "Exclui um cargo.",
    "reorder_roles": "Reordena um cargo.",
    "assign_role": "Atribui um cargo a um membro.",
    "remove_role": "Remove um cargo de um membro.",
    "update_role_permissions": "Altera permissões de um cargo.",
    "send_message": "Envia uma mensagem em um canal.",
    "delete_message": "Apaga uma mensagem específica por ID.",
}


def required_risk(action_type: str) -> str:
    return "high" if action_type in DANGEROUS_ACTIONS else "low"


def tool_catalog_text() -> str:
    return "\n".join(
        f"- {name}: {description}" for name, description in ACTION_DESCRIPTIONS.items()
    )
