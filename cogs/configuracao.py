import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


def can_configure(member: discord.Member) -> bool:
    return (
        member.id == member.guild.owner_id
        or member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )


class Configuracao(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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
        # Garante resposta rápida ao Discord para evitar o limite de 3 segundos
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
            self.bot.database.set_approval_channel(interaction.guild.id, canal.id)
        except Exception:
            logger.exception("Falha ao salvar o canal da staff para o guild %s.", interaction.guild.id)
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

    @app_commands.command(
        name="canal-publicacao",
        description="Define um canal como canal padrão de publicação de parcerias.",
    )
    @app_commands.describe(canal="Canal do servidor que deve receber as publicações de parceria.")
    @app_commands.default_permissions(manage_guild=True)
    async def canal_publicacao(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
            return

        bot_member = interaction.guild.me
        if bot_member:
            permissions = canal.permissions_for(bot_member)
            if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
                await interaction.response.send_message(
                    "Eu preciso de **Ver canal**, **Enviar mensagens** e **Inserir links** nesse canal.",
                    ephemeral=True,
                )
                return

        self.bot.database.set_publication_channel(interaction.guild.id, canal.id)
        await interaction.response.send_message(
            f"✅ {canal.mention} foi definido como **canal de publicação de parcerias**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Configuracao(bot))
