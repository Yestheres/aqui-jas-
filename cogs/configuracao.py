```python
from __future__ import annotations

import sqlite3
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "aqui_jas.sqlite3"


def set_staff_channel(guild_id: int, channel_id: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                partnership_channel_id INTEGER,
                staff_channel_id INTEGER
            )
            """
        )

        conn.execute(
            """
            INSERT INTO guild_settings (
                guild_id,
                staff_channel_id
            )
            VALUES (?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET
                staff_channel_id=excluded.staff_channel_id
            """,
            (guild_id, channel_id),
        )

        conn.commit()


class Configuracao(commands.Cog):
    """Comandos de configuração do servidor."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="configurar",
        description="Configura o canal da staff para receber solicitações.",
    )
    @app_commands.describe(
        canal="Canal onde a staff receberá as solicitações de parceria."
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def configurar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:

        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Esse comando só funciona em um servidor.",
                ephemeral=True,
            )
            return

        member = interaction.user

        if not (
            member.id == interaction.guild.owner_id
            or (
                isinstance(member, discord.Member)
                and (
                    member.guild_permissions.administrator
                    or member.guild_permissions.manage_guild
                )
            )
        ):
            await interaction.response.send_message(
                "❌ Você precisa ser dono do servidor ou ter "
                "**Gerenciar Servidor**.",
                ephemeral=True,
            )
            return

        try:
            set_staff_channel(
                interaction.guild.id,
                canal.id,
            )

            await interaction.response.send_message(
                f"✅ Canal da staff configurado para {canal.mention}.\n\n"
                "As solicitações feitas com `/parceria` "
                "serão enviadas para esse canal.",
                ephemeral=True,
            )

        except Exception:
            await interaction.response.send_message(
                "❌ Ocorreu um erro ao salvar a configuração.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(
        Configuracao(bot)
    )
```
