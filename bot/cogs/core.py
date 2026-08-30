from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class Core(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="ping",
        description="Verifica a latência do Aqui Jas.",
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latência atual: **{latency}ms**",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="sobre",
        description="Mostra informações sobre o Aqui Jas.",
    )
    async def about(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="✨ Aqui Jas",
            description=(
                "Um bot Discord modular, simples e focado em ferramentas "
                "práticas para o servidor."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="⚙️ Arquitetura", value="Modular com Cogs", inline=True)
        embed.add_field(name="🐍 Tecnologia", value="Python + discord.py", inline=True)
        embed.add_field(name="🚀 Status", value="Online", inline=True)
        embed.set_footer(text="Aqui Jas • núcleo puro Discord")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Core(bot))
