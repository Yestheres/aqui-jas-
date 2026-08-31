import sqlite3
from pathlib import Path

import discord
from discord.ext import commands


# ============================================================
# BANCO
# ============================================================

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


def set_staff_channel(
    guild_id: int,
    channel_id: int,
) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO guild_settings (
                guild_id,
                staff_channel_id
            )
            VALUES (?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET
                staff_channel_id = excluded.staff_channel_id
            """,
            (guild_id, channel_id),
        )

        conn.commit()


# ============================================================
# PERMISSÃO
# ============================================================

def can_configure(member: discord.Member) -> bool:
    return (
        member.id == member.guild.owner_id
        or member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )


# ============================================================
# COG
# ============================================================

class Configuracao(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

        init_database()

    # ========================================================
    # &canal-parceria
    # ========================================================

    @commands.command(
        name="canal-parceria",
    )
    async def canal_parceria(
        self,
        ctx: commands.Context,
        canal: discord.TextChannel,
    ) -> None:
        if ctx.guild is None:
            return

        if not isinstance(ctx.author, discord.Member):
            return

        if not can_configure(ctx.author):
            await ctx.send(
                "❌ Você precisa ser dono do servidor, "
                "Administrador ou ter **Gerenciar Servidor**.",
                delete_after=5,
            )
            return

        # ----------------------------------------------------
        # Verifica se o canal é privado para @everyone
        # ----------------------------------------------------

        everyone_overwrite = canal.overwrites_for(
            ctx.guild.default_role
        )

        if everyone_overwrite.view_channel is not False:
            await ctx.send(
                "❌ O canal precisa ser **privado**. "
                "O @everyone não pode ter acesso a ele.",
                delete_after=5,
            )
            return

        # ----------------------------------------------------
        # Salva configuração
        # ----------------------------------------------------

        try:
            set_staff_channel(
                ctx.guild.id,
                canal.id,
            )
        except sqlite3.Error:
            await ctx.send(
                "❌ Não consegui salvar a configuração.",
                delete_after=5,
            )
            return

        # ----------------------------------------------------
        # Apaga comando usado
        # ----------------------------------------------------

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        # ----------------------------------------------------
        # Confirmação
        # ----------------------------------------------------

        await ctx.send(
            f"✅ O canal da staff foi definido como {canal.mention}.",
            delete_after=5,
        )


# ============================================================
# SETUP DO COG
# ============================================================

async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        Configuracao(bot)
    )
