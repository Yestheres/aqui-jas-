from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

GITHUB_URL = "https://github.com/Yestheres/aqui-jas-"


class V1Admin(commands.Cog):
    """Polished, read-only server information and help commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="servidor",
        description="Abre um painel organizado com as informações do servidor.",
    )
    async def server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.",
                ephemeral=True,
            )
            return

        try:
            members = [member async for member in guild.fetch_members(limit=None)]
        except (discord.Forbidden, discord.HTTPException, discord.ClientException):
            members = list(guild.members)

        humans = sum(not member.bot for member in members)
        bots = sum(member.bot for member in members)

        categories = len(guild.categories)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        forum_channels = len(guild.forums)
        stage_channels = len(guild.stage_channels)
        visible_channels = (
            text_channels + voice_channels + forum_channels + stage_channels
        )
        roles = max(0, len(guild.roles) - 1)

        owner = guild.owner.mention if guild.owner else "Indisponível"
        created = int(guild.created_at.replace(tzinfo=timezone.utc).timestamp())

        embed = discord.Embed(
            title=f"🏠 {guild.name}",
            description=(
                "**Visão geral do servidor**\n"
                "Uma leitura rápida da comunidade e da estrutura."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        elif self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(
            name="👥 Comunidade",
            value=(
                f"👤 Pessoas **{humans}**\n"
                f"🤖 Bots **{bots}**\n"
                f"📊 Total **{humans + bots}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="💬 Canais",
            value=(
                f"📝 Texto **{text_channels}**\n"
                f"🔊 Voz **{voice_channels}**\n"
                f"💬 Fórum **{forum_channels}**\n"
                f"🎙️ Palco **{stage_channels}**\n"
                f"📚 Total **{visible_channels}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎭 Organização",
            value=(
                f"🗂️ Categorias **{categories}**\n"
                f"🎭 Cargos **{roles}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="📋 Detalhes",
            value=(
                f"👑 **Dono:** {owner}\n"
                f"📅 **Criado:** <t:{created}:D> · <t:{created}:R>\n"
                f"🆔 **ID:** `{guild.id}`"
            ),
            inline=False,
        )

        if guild.premium_tier:
            embed.add_field(
                name="🚀 Boost",
                value=(
                    f"Nível **{guild.premium_tier}** · "
                    f"{guild.premium_subscription_count or 0} boosts"
                ),
                inline=False,
            )

        embed.set_footer(text="Aqui Jas • painel do servidor")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="ajuda",
        description="Abre a central de comandos do Aqui Jas.",
    )
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="✨ Aqui Jas",
            description=(
                "**Central de comandos**\n"
                "Tudo que você precisa para conhecer o núcleo do bot."
            ),
            color=discord.Color.blurple(),
        )

        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(
            name="⚡ Geral",
            value=(
                "`/ping` — diagnóstico e latência\n"
                "`/sobre` — perfil, tecnologia e status"
            ),
            inline=False,
        )
        embed.add_field(
            name="🏠 Servidor",
            value=(
                "`/servidor` — painel completo do servidor\n"
                "`/ajuda` — esta central"
            ),
            inline=False,
        )
        embed.add_field(
            name="🧩 Projeto",
            value=(
                "Núcleo puro Discord, construído em Python e `discord.py`, "
                "com arquitetura modular para crescer sem virar uma bagunça."
            ),
            inline=False,
        )

        view = discord.ui.View(timeout=120)
        view.add_item(
            discord.ui.Button(
                label="Ver código no GitHub",
                style=discord.ButtonStyle.link,
                url=GITHUB_URL,
                emoji="💻",
            )
        )
        embed.set_footer(text="Aqui Jas • /ajuda")

        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(V1Admin(bot))
