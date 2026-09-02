from __future__ import annotations

from typing import Any

import discord


def status_label(status: str) -> str:
    labels = {
        "pending": "Pendente de aprovação",
        "publishing": "Publicando",
        "approved": "Aprovada",
        "rejected": "Recusada",
        "failed": "Falha ao enviar para a staff",
    }
    return labels.get(status, status.title())


def partnership_embed_color(color_name: str | None) -> discord.Color:
    palette = {
        "azul": discord.Color.blurple(),
        "roxo": discord.Color.purple(),
        "verde": discord.Color.green(),
        "amarelo": discord.Color.gold(),
        "vermelho": discord.Color.red(),
        "rosa": discord.Color.magenta(),
        "cinza": discord.Color.dark_grey(),
    }
    return palette.get((color_name or "azul").lower(), discord.Color.blurple())


def partnership_embed(request: dict[str, Any]) -> discord.Embed:
    custom_color = request.get("color")
    color = partnership_embed_color(custom_color) if custom_color else {
        "pending": discord.Color.gold(),
        "publishing": discord.Color.blurple(),
        "approved": discord.Color.green(),
        "rejected": discord.Color.red(),
    }.get(request["status"], discord.Color.blurple())

    embed = discord.Embed(
        title="Solicitação de parceria",
        description=request["description"],
        color=color,
    )
    embed.add_field(name="Solicitante", value=f"<@{request['requester_id']}>", inline=True)
    embed.add_field(name="Status", value=status_label(request["status"]), inline=True)
    embed.add_field(name="Link", value=f"[Abrir link]({request['link']})", inline=False)

    if request.get("publication_channel_id"):
        embed.add_field(
            name="Canal de publicação",
            value=f"<#{request['publication_channel_id']}>",
            inline=False,
        )

    embed.set_footer(text=f"Solicitação #{request['id']}")
    return embed


def published_partnership_embed(request: dict[str, Any], server_name: str | None, icon_url: str | None) -> discord.Embed:
    embed = discord.Embed(
        title=server_name,
        description=request["description"],
        color=partnership_embed_color(request.get("color")),
    )
    if icon_url:
        embed.set_thumbnail(url=icon_url)
    return embed


def published_partnership_view(link: str) -> discord.ui.View:
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Entrar no servidor", style=discord.ButtonStyle.link, url=link))
    return view
