from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

GITHUB_URL = "https://github.com/Yestheres/aqui-jas-"


class V1Admin(commands.Cog):
    """Read-only server information and help commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="servidor",
        description="Abre um painel organizado com as informações do servidor.",
    )
    async def server(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        try:
            guild = interaction.guild
            if guild is None:
                await interaction.edit_original_response(
                    content="Este comando só pode ser usado em um servidor."
                )
                return

            # The member cache can be empty without the privileged members
            # intent. Fetch the guild with counts to obtain an approximate
            # member total without requesting that privileged intent.
            try:
                guild_info = await self.bot.fetch_guild(guild.id, with_counts=True)
                total_members = (
                    guild_info.approximate_member_count
                    or guild.member_count
                    or len(guild.members)
                    or 0
                )
            except discord.HTTPException:
                total_members = guild.member_count or len(guild.members)

            # Count bots that are actually known to the cache. For a small
            # server this normally includes the bot itself. Human count is
            # derived from the authoritative/approximate total, avoiding a
            # misleading 0 when the full member cache is unavailable.
            cached_bots = sum(1 for member in guild.members if member.bot)
            bots = cached_bots
            humans = max(0, total_members - bots)

            categories = len(guild.categories)
            text_channels = len(guild.text_channels)
            voice_channels = len(guild.voice_channels)
            forum_channels = len(guild.forums)
            stage_channels = len(guild.stage_channels)
            visible_channels = (
                text_channels + voice_channels + forum_channels + stage_channels
            )
            roles = max(0, len(guild.roles) - 1)

            owner = f"<@{guild.owner_id}>" if guild.owner_id else "Indisponível"
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
                    f"🤖 Bots conhecidos **{bots}**\n"
                    f"📊 Membros **{total_members}**"
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
            await interaction.edit_original_response(content=None, embed=embed)
        except Exception:
            await interaction.edit_original_response(
                content="❌ Não consegui montar as informações do servidor agora."
            )

    @app_commands.command(
        name="ajuda",
        description="Abre a central de comandos do Aqui Jas.",
    )
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="✨ Aqui Jas",
            description="**Central de comandos**\nTudo organizado em um só lugar.",
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
            value="Núcleo puro Discord, modular e sem IA.",
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
