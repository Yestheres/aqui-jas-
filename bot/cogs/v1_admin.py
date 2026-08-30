from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class V1Admin(commands.Cog):
    """Basic server diagnostics and help commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="servidor", description="Mostra informações do servidor.")
    async def server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return

        try:
            members = [member async for member in guild.fetch_members(limit=None)]
        except (discord.Forbidden, discord.HTTPException):
            # Fallback para o cache se o servidor/intents não permitirem a consulta.
            members = list(guild.members)

        humans = sum(not member.bot for member in members)
        bots = sum(member.bot for member in members)
        categories = len(guild.categories)
        channels = len(guild.channels) - categories

        embed = discord.Embed(
            title=f"🏠 {guild.name}",
            description="Informações do servidor",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="👥 Pessoas", value=f"`{humans}`", inline=True)
        embed.add_field(name="🤖 Bots", value=f"`{bots}`", inline=True)
        embed.add_field(name="📊 Membros", value=f"`{humans + bots}`", inline=True)
        embed.add_field(name="💬 Canais", value=f"`{channels}`", inline=True)
        embed.add_field(name="🗂️ Categorias", value=f"`{categories}`", inline=True)
        embed.add_field(name="🎭 Cargos", value=f"`{len(guild.roles)}`", inline=True)
        embed.set_footer(text=f"ID do servidor: {guild.id}")

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
