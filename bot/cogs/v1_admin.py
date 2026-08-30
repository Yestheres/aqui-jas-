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
        # Acknowledge immediately so a slow Discord/member lookup cannot make
        # the interaction expire with "This interaction failed".
        await interaction.response.defer()

        guild = interaction.guild
        if guild is None:
            await interaction.edit_original_response(
                content="Este comando só pode ser usado em um servidor."
            )
            return

        total_members = guild.member_count or len(guild.members)
        cached_members = list(guild.members)
        humans = sum(1 for member in cached_members if not member.bot)
        bots = sum(1 for member in cached_members if member.bot)
        cached_total = humans + bots

        categories = len(guild.categories)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        forum_channels = len(guild.forums)
        stage_channels = len(guild.stage_channels)
        visible_channels = (
            text_channels + voice_channels + forum_channels + stage_channels
        )
        roles = max(0, len(guild.roles) - 1)

        if cached_total != total_members and total_members > 0:
            community = (
                f"👤 Pessoas **{humans}**\n"
                f"🤖 Bots **{bots}**\n"
                f"📊 Total **{total_members}**\n"
                "*Pessoas/bots exibidos a partir do cache disponível.*"
            )
        else:
            community = (
                f"👤 Pessoas **{humans}**\n"
                f"🤖 Bots **{bots}**\n"
                f"📊 Total **{total_members}**"
            )

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

        embed.add_field(name="👥 Comunidade", value=community, inline=True)
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
        await interaction.edit_original_response(content=None, embed=embed)

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
    # Keep every command global. Guild-specific registration caused the
    # duplicate slash-command entries seen during development.
    await bot.add_cog(V1Admin(bot))
