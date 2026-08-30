from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class V1Admin(commands.Cog):
    """Polished, read-only server information and help commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="servidor",
        description="Mostra um resumo organizado deste servidor.",
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
        except (discord.Forbidden, discord.HTTPException):
            members = list(guild.members)

        humans = sum(1 for member in members if not member.bot)
        bots = sum(1 for member in members if member.bot)
        categories = len(guild.categories)
        text_channels = sum(1 for c in guild.channels if isinstance(c, discord.TextChannel))
        voice_channels = sum(1 for c in guild.channels if isinstance(c, discord.VoiceChannel))
        stage_channels = sum(1 for c in guild.channels if isinstance(c, discord.StageChannel))
        forum_channels = sum(1 for c in guild.channels if isinstance(c, discord.ForumChannel))
        roles = max(0, len(guild.roles) - 1)

        embed = discord.Embed(
            title=f"🏠 {guild.name}",
            description="**Resumo do servidor** · visão geral atual",
            color=discord.Color.blurple(),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="👥 Comunidade",
            value=(
                f"**Pessoas** `{humans}`\n"
                f"**Bots** `{bots}`\n"
                f"**Membros** `{humans + bots}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="💬 Canais",
            value=(
                f"**Texto** `{text_channels}`\n"
                f"**Voz** `{voice_channels}`\n"
                f"**Fórum** `{forum_channels}`\n"
                f"**Palco** `{stage_channels}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎭 Organização",
            value=(
                f"**Categorias** `{categories}`\n"
                f"**Cargos** `{roles}`"
            ),
            inline=True,
        )

        owner = guild.owner.mention if guild.owner else "Indisponível"
        embed.add_field(
            name="📋 Detalhes",
            value=(
                f"**Dono:** {owner}\n"
                f"**Criado:** {discord.utils.format_dt(guild.created_at, 'D')}\n"
                f"**ID:** `{guild.id}`"
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

        embed.set_footer(text="Aqui Jas • informações somente leitura")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="ajuda",
        description="Abre a central de comandos do Aqui Jas.",
    )
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="✨ Aqui Jas",
            description="**Central de comandos** · tudo organizado em um só lugar.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="⚡ Geral",
            value=(
                "`/ping` — verifica a latência\n"
                "`/sobre` — mostra informações do bot"
            ),
            inline=False,
        )
        embed.add_field(
            name="🏠 Servidor",
            value=(
                "`/servidor` — resumo completo do servidor\n"
                "`/ajuda` — abre esta central"
            ),
            inline=False,
        )
        embed.add_field(
            name="🛠️ Em construção",
            value="Novos módulos serão adicionados gradualmente, sem sobrecarregar o bot.",
            inline=False,
        )
        embed.set_footer(text="Aqui Jas • núcleo puro Discord")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(V1Admin(bot))
