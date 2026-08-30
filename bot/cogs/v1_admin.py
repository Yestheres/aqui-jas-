from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class V1Admin(commands.Cog):
    """Basic server diagnostics and help commands."""

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

        humans = sum(1 for member in guild.members if not member.bot)
        bots = sum(1 for member in guild.members if member.bot)

        embed = discord.Embed(
            title=f"🏠 {guild.name}",
            description="Resumo do servidor",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="👥 Pessoas", value=str(humans), inline=True)
        embed.add_field(name="🤖 Bots", value=str(bots), inline=True)
        embed.add_field(name="📊 Total", value=str(humans + bots), inline=True)
        embed.add_field(name="💬 Canais", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="🗂️ Categorias", value=str(len(guild.categories)), inline=True)
        embed.add_field(name="🎭 Cargos", value=str(len(guild.roles)), inline=True)
        embed.set_footer(text=f"ID: {guild.id}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ajuda", description="Mostra os comandos disponíveis.")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🤖 Aqui Jas",
            description="Central de comandos",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="⚙️ Geral",
            value="`/ping` · `/sobre` · `/servidor` · `/ajuda`",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(V1Admin(bot))
