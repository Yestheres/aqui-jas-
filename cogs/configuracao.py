from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


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
    @app_commands.default_permissions(manage_guild=True)
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
                "❌ Você precisa ser dono do servidor ou ter **Gerenciar Servidor**.",
                ephemeral=True,
            )
            return

        # Importado aqui para evitar acoplamento circular com o main.py.
        from main import set_channel

        set_channel(
            interaction.guild.id,
            "staff_channel_id",
            canal.id,
        )

        await interaction.response.send_message(
            f"✅ Canal da staff configurado para {canal.mention}.\n\n"
            "As solicitações feitas com `/parceria` serão enviadas para esse canal.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Configuracao(bot))
