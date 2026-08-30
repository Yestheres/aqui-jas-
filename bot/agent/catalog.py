from __future__ import annotations

DANGEROUS_ACTIONS = {
    "delete_channel", "delete_role", "set_channel_permissions",
    "update_role_permissions", "update_guild", "ban_member", "kick_member",
    "timeout_member", "delete_message", "create_webhook",
    "create_automod_rule", "update_automod_rule", "delete_automod_rule",
}

IDEMPOTENT_ACTIONS = {
    "create_channel", "create_role", "assign_role", "remove_role",
    "move_channel", "update_channel", "set_channel_permissions",
    "sync_channel_permissions",
}

ACTION_DESCRIPTIONS: dict[str, str] = {
    "create_channel": "Cria canal ou categoria (channel_type: category/text/voice).",
    "update_channel": "Atualiza nome, tópico, slowmode ou NSFW.",
    "delete_channel": "Exclui um canal ou categoria.",
    "move_channel": "Move um canal para uma categoria.",
    "reorder_channels": "Reordena canais por posição.",
    "set_channel_permissions": "Altera permissões de um canal para um alvo.",
    "sync_channel_permissions": "Sincroniza permissões com a categoria.",
    "create_role": "Cria um cargo.",
    "update_role": "Atualiza nome, cor ou menção de um cargo.",
    "delete_role": "Exclui um cargo.",
    "reorder_roles": "Reordena cargos.",
    "assign_role": "Atribui um cargo a um membro.",
    "remove_role": "Remove um cargo de um membro.",
    "update_role_permissions": "Altera permissões de um cargo.",
    "update_nickname": "Altera o apelido de um membro.",
    "timeout_member": "Aplica ou remove timeout.",
    "kick_member": "Expulsa um membro.",
    "ban_member": "Bane um membro.",
    "unban_member": "Remove um banimento.",
    "send_message": "Envia mensagem em um canal.",
    "delete_message": "Apaga uma mensagem específica.",
}


def required_risk(action_type: str) -> str:
    return "high" if action_type in DANGEROUS_ACTIONS else "low"


def tool_catalog_text() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in ACTION_DESCRIPTIONS.items())
