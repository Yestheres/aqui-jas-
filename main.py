from __future__ import annotations

import logging
import os
import platform

import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não está configurado.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("discord_bot")


class Bot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    @property
    def display_name(self) -> str:
        return self.user.name if self.user else "Bot"

    async def setup_hook(self) -> None:
        synced = await self.tree.sync()
        log.info(
            "Sincronizados %d comandos globais: %s",
            len(synced),
            ", ".join(command.name for command in synced),
        )

    async def on_ready(self) -> None:
        if self.user is None:
            return
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/ajuda • seu servidor",
            ),
        )
        log.info("Online como %s (%s)", self.user, self.user.id)
        log.info("Conectado a %d servidor(es)", len(self.guilds))


bot = Bot()


@bot.tree.command(name="ping", description="Verifica se o bot está online.")
async def ping(interaction: discord.Interaction) -> None:
    latency = round(bot.latency * 1000)
    name = bot.display_name
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"O **{name}** está online e respondendo.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="⚡ Latência", value=f"`{latency} ms`", inline=True)
    embed.add_field(name="🟢 Estado", value="`Online`", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="sobre", description="Mostra informações sobre o bot.")
async def sobre(interaction: discord.Interaction) -> None:
    name = bot.display_name
    embed = discord.Embed(
        title=f"✨ {name}",
        description="Um bot Discord leve, moderno e modular — começando do zero.",
        color=discord.Color.blurple(),
    )
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="🐍 Python", value=f"`{platform.python_version()}`", inline=True)
    embed.add_field(name="📦 discord.py", value=f"`{discord.__version__}`", inline=True)
    embed.add_field(name="🏠 Servidores", value=f"`{len(bot.guilds)}`", inline=True)
    embed.add_field(name="🔧 Núcleo", value="Discord API + Slash Commands", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="servidor", description="Mostra informações básicas deste servidor.")
async def servidor(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "Esse comando só funciona dentro de um servidor.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=f"🏠 {guild.name}",
        description=f"Informações básicas do servidor • {bot.display_name}",
        color=discord.Color.blurple(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(name="👥 Membros", value=f"`{guild.member_count or 0}`", inline=True)
    embed.add_field(name="💬 Canais", value=f"`{len(guild.channels)}`", inline=True)
    embed.add_field(name="🗂️ Categorias", value=f"`{len(guild.categories)}`", inline=True)
    embed.add_field(name="🎭 Cargos", value=f"`{max(0, len(guild.roles) - 1)}`", inline=True)
    embed.add_field(name="🆔 ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="📅 Criado", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ajuda", description="Mostra os comandos disponíveis.")
async def ajuda(interaction: discord.Interaction) -> None:
    name = bot.display_name
    embed = discord.Embed(
        title=f"✨ {name}",
        description="**Central de comandos**",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="⚡ Geral",
        value="`/ping` — verifica o bot\n`/sobre` — informações do bot",
        inline=False,
    )
    embed.add_field(
        name="🏠 Servidor",
        value="`/servidor` — informações do servidor\n`/ajuda` — esta página",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


bot.run(TOKEN)
