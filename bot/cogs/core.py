from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class Core(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Pong! `{round(self.bot.latency * 1000)}ms`"
        )

    @app_commands.command(name="sobre", description="Show the bot architecture status.")
    async def about(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "**Aqui Jas** — núcleo novo, modular e preparado para o agente IA."
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Core(bot))
