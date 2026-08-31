import sqlite3
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "aqui_jas.sqlite3"


def init_database() -> None:
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
        conn.commit()


def set_staff_channel(guild_id: int, channel_id: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO guild_settings (guild_id, staff_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET staff_channel_id = excluded.staff_channel_id
            """,
            (guild_id, channel_id),
        )
        conn.commit()


def can_configure(member: discord.Member) -> bool:
    return (
        member.id == member.guild.owner_id
        or member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )


class Configuracao(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        init_database()

    @app_commands.command(
        name="configurar",
        description="Configura o canal privado da staff.",
    )
    @app_commands.describe(
        canal="Canal privado onde a staff receberá as solicitações."
    )
    @app_commands.default_permissions(manage_guild=True)
    async def configurar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        # Adia a resposta imediatamente para evitar que estoure o limite de 3 segundos do Discord
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "❌ Esse comando só funciona em um servidor.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.followup.send(
                "❌ Não foi possível verificar suas permissões.",
                ephemeral=True,
            )
            return

        if not can_configure(interaction.user):
            await interaction.followup.send(
                "❌ Você precisa ser dono do servidor, Administrador ou ter **Gerenciar Servidor**.",
                ephemeral=True,
            )
            return

        everyone_overwrite = canal.overwrites_for(interaction.guild.default_role)
        if everyone_overwrite.view_channel is not False:
            await interaction.followup.send(
                "❌ O canal precisa ser **privado**.\n\n"
                "O cargo `@everyone` não pode ter permissão explícita para visualizar esse canal.",
                ephemeral=True,
            )
            return

        try:
            set_staff_channel(interaction.guild.id, canal.id)
        except sqlite3.Error:
            await interaction.followup.send(
                "❌ Não consegui salvar a configuração.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Canal da staff configurado para {canal.mention}.\n\n"
            "As solicitações feitas com `/parceria` serão enviadas para esse canal.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Configuracao(bot))
