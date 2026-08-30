from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class V1Admin(commands.Cog):
    """Base server diagnostics and help commands for the pure bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="servidor", description="Mostra informações deste servidor.")
    async def server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🏠 {guild.name}",
            description="Resumo atual do servidor.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Membros", value=str(guild.member_count or 0), inline=True)
        embed.add_field(name="Canais", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Cargos", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Categorias", value=str(len(guild.categories)), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ajuda", description="Mostra os recursos disponíveis do Aqui Jas.")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🤖 Aqui Jas",
            description="Bot Discord modular, sem dependência de IA.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="🏠 Servidor",
            value="`/servidor` · resumo do servidor",
            inline=False,
        )
        embed.add_field(
            name="⚙️ Núcleo",
            value="`/ping` · `/sobre`",
            inline=False,
        )
        embed.set_footer(text="Mais módulos podem ser adicionados sem depender de IA.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(V1Admin(bot))
