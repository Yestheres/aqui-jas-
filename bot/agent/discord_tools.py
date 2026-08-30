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
        "delete_message": "manage_messages",
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


def _overwrite_input(data: dict[str, Any]) -> discord.PermissionOverwrite:
    values: dict[str, bool] = {}
    for name in data.get("allow", []):
        values[str(name)] = True
    for name in data.get("deny", []):
        values[str(name)] = False
    try:
        return discord.PermissionOverwrite(**values)
    except TypeError as exc:
        raise ValueError("Permissão inválida em allow/deny.") from exc


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
            kwargs["slowmode_delay"] = max(
                0, min(21600, int(input_data["rate_limit_per_user"]))
            )

        if kwargs:
            await channel.edit(**kwargs, reason=reason)
        return {"channel_id": channel.id, "updated": bool(kwargs)}

    if action_type == "move_channel":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        category = guild.get_channel(int(input_data["parent_category_id"]))
        if channel is None or not isinstance(category, discord.CategoryChannel):
            raise ValueError("Canal ou categoria destino não encontrada.")
        if channel.category_id == category.id:
            return {
                "channel_id": channel.id,
                "parent_category_id": category.id,
                "changed": False,
            }
        await channel.edit(category=category, reason=reason)
        return {
            "channel_id": channel.id,
            "parent_category_id": category.id,
            "changed": True,
        }

    if action_type == "sync_channel_permissions":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        if channel is None:
            raise ValueError("Canal não encontrado.")
        await channel.edit(sync_permissions=True, reason=reason)
        return {"channel_id": channel.id, "synced": True}

    if action_type == "set_channel_permissions":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        if channel is None:
            raise ValueError("Canal não encontrado.")

        if "role_id" in target:
            subject = guild.get_role(int(target["role_id"]))
        else:
            member_id = _target_int(target, "member_id")
            subject = guild.get_member(member_id) or await guild.fetch_member(member_id)
        if subject is None:
            raise ValueError("Alvo de permissão não encontrado.")

        overwrite = _overwrite_input(input_data)
        await channel.set_permissions(subject, overwrite=overwrite, reason=reason)
        return {"channel_id": channel.id, "target_id": subject.id, "updated": True}

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

        color_text = str(input_data.get("color", "0")).lstrip("#")
        try:
            color = discord.Colour(int(color_text, 16)) if color_text else discord.Colour.default()
        except ValueError as exc:
            raise ValueError("input.color inválida.") from exc

        role = await guild.create_role(
            name=name,
            colour=color,
            mentionable=bool(input_data.get("mentionable", False)),
            reason=reason,
        )
        return {"role_id": role.id, "reused": False}

    if action_type == "update_role":
        role = guild.get_role(_target_int(target, "role_id"))
        if role is None:
            raise ValueError("Cargo não encontrado.")
        if role >= guild.me.top_role:
            raise RuntimeError("O cargo alvo está acima ou no mesmo nível do cargo do bot.")

        kwargs: dict[str, Any] = {}
        if "name" in input_data:
            kwargs["name"] = str(input_data["name"])
        if "mentionable" in input_data:
            kwargs["mentionable"] = bool(input_data["mentionable"])
        if "color" in input_data:
            kwargs["colour"] = discord.Colour(
                int(str(input_data["color"]).lstrip("#"), 16)
            )
        if kwargs:
            await role.edit(**kwargs, reason=reason)
        return {"role_id": role.id, "updated": bool(kwargs)}

    if action_type == "delete_role":
        role = guild.get_role(_target_int(target, "role_id"))
        if role is None:
            return {"deleted": False, "already_missing": True}
        if role >= guild.me.top_role:
            raise RuntimeError("O cargo alvo está acima ou no mesmo nível do cargo do bot.")
        await role.delete(reason=reason)
        return {"role_id": role.id, "deleted": True}

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

    if action_type == "send_message":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            raise ValueError("Canal não encontrado ou não aceita mensagens.")
        content = str(input_data.get("content", "")).strip()
        if not content:
            raise ValueError("input.content é obrigatório.")
        sent = await channel.send(content)
        return {"message_id": sent.id, "channel_id": channel.id}

    if action_type == "delete_message":
        channel = guild.get_channel(_target_int(target, "channel_id"))
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise ValueError("Canal de texto não encontrado.")
        message_id = _target_int(target, "message_id")
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return {"deleted": False, "already_missing": True, "message_id": message_id}
        await message.delete(reason=reason)
        return {"deleted": True, "message_id": message_id, "channel_id": channel.id}

    raise RuntimeError(f"Ação não implementada: {action_type}")
