from __future__ import annotations

from datetime import timedelta
from typing import Any

import discord

from .catalog import ACTION_DESCRIPTIONS

IMPLEMENTED = set(ACTION_DESCRIPTIONS)


def _permission_for(action: str) -> str:
    return {
        "create_channel": "manage_channels",
        "update_channel": "manage_channels",
        "delete_channel": "manage_channels",
        "move_channel": "manage_channels",
        "set_channel_permissions": "manage_channels",
        "sync_channel_permissions": "manage_channels",
        "create_role": "manage_roles",
        "update_role": "manage_roles",
        "delete_role": "manage_roles",
        "assign_role": "manage_roles",
        "remove_role": "manage_roles",
        "update_nickname": "manage_nicknames",
        "timeout_member": "moderate_members",
        "kick_member": "kick_members",
        "ban_member": "ban_members",
        "unban_member": "ban_members",
        "send_message": "manage_messages",
    }.get(action, "manage_guild")


def require_permission(guild: discord.Guild, action: str) -> None:
    me = guild.me
    if me is None:
        raise RuntimeError("Não foi possível obter o membro do bot neste servidor.")
    permission = _permission_for(action)
    if not getattr(me.guild_permissions, permission, False):
        raise RuntimeError(f"O bot não possui a permissão necessária: {permission}.")


def _target_int(target: dict[str, Any], key: str) -> int:
    try:
        return int(target[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"target.{key} precisa ser um ID válido.") from exc


async def execute_action(
    guild: discord.Guild,
    action_type: str,
    target: dict[str, Any],
    input_data: dict[str, Any],
) -> dict[str, Any]:
    if action_type not in IMPLEMENTED:
        raise RuntimeError(f"Ação ainda não implementada: {action_type}")
    require_permission(guild, action_type)
    reason = str(input_data.get("reason", "Aqui Jas"))[:512]

    if action_type == "create_channel":
        name = str(input_data.get("name", "")).strip()
        kind = str(input_data.get("channel_type", "text")).lower()
        if not name:
            raise ValueError("input.name é obrigatório.")
        existing = discord.utils.find(lambda c: c.name == name, guild.channels)
        if kind == "category" and isinstance(existing, discord.CategoryChannel):
            return {"channel_id": existing.id, "reused": True}
        if kind == "text" and isinstance(existing, discord.TextChannel):
            return {"channel_id": existing.id, "reused": True}
        if kind == "voice" and isinstance(existing, discord.VoiceChannel):
            return {"channel_id": existing.id, "reused": True}
        if kind == "category":
            channel = await guild.create_category(name, reason=reason)
        elif kind == "voice":
            channel = await guild.create_voice_channel(name, reason=reason)
        else:
            channel = await guild.create_text_channel(name, reason=reason)
        return {"channel_id": channel.id, "reused": False}

    if action_type == "update_channel":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        if channel is None:
            raise ValueError("Canal não encontrado.")
        kwargs: dict[str, Any] = {}
        if "name" in input_data:
            kwargs["name"] = str(input_data["name"])
        if "topic" in input_data and isinstance(channel, discord.TextChannel):
            kwargs["topic"] = str(input_data["topic"])
        if "nsfw" in input_data and isinstance(channel, discord.TextChannel):
            kwargs["nsfw"] = bool(input_data["nsfw"])
        if "rate_limit_per_user" in input_data and isinstance(channel, discord.TextChannel):
            kwargs["slowmode_delay"] = max(0, min(21600, int(input_data["rate_limit_per_user"])))
        if kwargs:
            await channel.edit(**kwargs, reason=reason)
        return {"channel_id": channel.id, "updated": bool(kwargs)}

    if action_type == "move_channel":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        category = guild.get_channel(int(input_data["parent_category_id"]))
        if channel is None or not isinstance(category, discord.CategoryChannel):
            raise ValueError("Canal ou categoria destino não encontrada.")
        if channel.category_id == category.id:
            return {"channel_id": channel.id, "parent_category_id": category.id, "changed": False}
        await channel.edit(category=category, reason=reason)
        return {"channel_id": channel.id, "parent_category_id": category.id, "changed": True}

    if action_type == "delete_channel":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        if channel is None:
            return {"deleted": False, "already_missing": True}
        await channel.delete(reason=reason)
        return {"deleted": True, "channel_id": channel.id}

    if action_type == "create_role":
        name = str(input_data.get("name", "")).strip()
        if not name:
            raise ValueError("input.name é obrigatório.")
        existing = discord.utils.find(lambda r: r.name == name, guild.roles)
        if existing and existing != guild.default_role:
            return {"role_id": existing.id, "reused": True}
        raw_color = str(input_data.get("color", "0")).lstrip("#")
        try:
            color = discord.Colour(int(raw_color, 16)) if raw_color else discord.Colour.default()
        except ValueError as exc:
            raise ValueError("input.color precisa ser hexadecimal, como #5865F2.") from exc
        role = await guild.create_role(
            name=name,
            colour=color,
            mentionable=bool(input_data.get("mentionable", False)),
            reason=reason,
        )
        return {"role_id": role.id, "reused": False}

    if action_type in {"assign_role", "remove_role"}:
        member_id = _target_int(target, "member_id")
        role = guild.get_role(_target_int(target, "role_id"))
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
        if role is None:
            raise ValueError("Cargo não encontrado.")
        if role >= guild.me.top_role:
            raise RuntimeError("O cargo alvo está acima ou no mesmo nível do cargo do bot.")
        if action_type == "assign_role":
            await member.add_roles(role, reason=reason)
        else:
            await member.remove_roles(role, reason=reason)
        return {"member_id": member.id, "role_id": role.id}

    if action_type == "update_nickname":
        member_id = _target_int(target, "member_id")
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
        if member != guild.me and member.top_role >= guild.me.top_role:
            raise RuntimeError("Hierarquia de cargos impede alterar este membro.")
        await member.edit(nick=input_data.get("nickname"), reason=reason)
        return {"member_id": member.id, "nickname": member.nick}

    if action_type == "timeout_member":
        member_id = _target_int(target, "member_id")
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
        if member != guild.me and member.top_role >= guild.me.top_role:
            raise RuntimeError("Hierarquia de cargos impede timeout neste membro.")
        minutes = int(input_data.get("minutes", 0))
        until = None if minutes <= 0 else discord.utils.utcnow() + timedelta(minutes=min(minutes, 40320))
        await member.edit(timed_out_until=until, reason=reason)
        return {"member_id": member.id, "timed_out_until": until.isoformat() if until else None}

    if action_type == "kick_member":
        member_id = _target_int(target, "member_id")
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
        if member.top_role >= guild.me.top_role:
            raise RuntimeError("Hierarquia de cargos impede expulsar este membro.")
        await member.kick(reason=reason)
        return {"member_id": member.id, "kicked": True}

    if action_type == "ban_member":
        member_id = _target_int(target, "member_id")
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
        if member.top_role >= guild.me.top_role:
            raise RuntimeError("Hierarquia de cargos impede banir este membro.")
        await guild.ban(member, reason=reason, delete_message_seconds=0)
        return {"member_id": member.id, "banned": True}

    if action_type == "unban_member":
        user_id = _target_int(target, "user_id")
        await guild.unban(discord.Object(id=user_id), reason=reason)
        return {"user_id": user_id, "unbanned": True}

    if action_type == "send_message":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            raise ValueError("Canal não encontrado ou não aceita mensagens.")
        content = str(input_data.get("content", "")).strip()
        if not content:
            raise ValueError("input.content é obrigatório.")
        sent = await channel.send(content)
        return {"message_id": sent.id, "channel_id": channel.id}

    raise RuntimeError(f"Ação não implementada: {action_type}")
