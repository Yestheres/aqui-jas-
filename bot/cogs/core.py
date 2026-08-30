from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import platform

import discord
from discord import app_commands
from discord.ext import commands

GITHUB_URL = "https://github.com/Yestheres/aqui-jas-"


def discord_py_version() -> str:
    try:
        return version("discord.py")
    except PackageNotFoundError:
        return "desconhecida"


class Core(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="ping",
        description="Verifica a latência e o estado do Aqui Jas.",
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description="O Aqui Jas está respondendo normalmente.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="⚡ Latência", value=f"`{latency} ms`", inline=True)
        embed.add_field(name="🟢 Estado", value="`Online`", inline=True)
        embed.add_field(name="🛰️ Servidores", value=f"`{len(self.bot.guilds)}`", inline=True)
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Aqui Jas • diagnóstico")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="sobre",
        description="Mostra informações e tecnologia usada pelo Aqui Jas.",
    )
    async def about(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="✨ Aqui Jas",
            description=(
                "Um bot Discord modular focado em administração, comunidade e ferramentas práticas.\n\n"
                "Projeto construído para crescer por módulos, sem depender de IA."
            ),
            color=discord.Color.blurple(),
        )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="🐍 Python", value=f"`{platform.python_version()}`", inline=True)
        embed.add_field(name="📦 discord.py", value=f"`{discord_py_version()}`", inline=True)
        embed.add_field(name="🏠 Servidores", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="🧩 Comandos", value=f"`{len(self.bot.tree.get_commands())}`", inline=True)
        embed.add_field(name="⚙️ Arquitetura", value="Cogs + eventos assíncronos", inline=True)
        embed.add_field(name="🚀 Status", value="Operacional", inline=True)
        embed.add_field(
            name="🛠️ Biblioteca padrão",
            value="asyncio · logging · datetime · pathlib · importlib.metadata",
            inline=False,
        )
        embed.set_footer(text="Aqui Jas • núcleo puro Discord")

        view = discord.ui.View(timeout=120)
        view.add_item(
            discord.ui.Button(
                label="Código no GitHub",
                style=discord.ButtonStyle.link,
                url=GITHUB_URL,
                emoji="💻",
            )
        )
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Core(bot))
