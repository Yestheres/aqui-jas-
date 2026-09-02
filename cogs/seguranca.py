from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
SUSPEITO_ROLE_NAME = "Suspeito"
TRAP_ROLE_NAME = "Suspeito"
TRAP_TOPIC_MARKER = "[ARMADILHA] Acesso restrito ao cargo Suspeito."


class Seguranca(commands.Cog):
    """Detecta padrões rápidos de mensagens e marca o usuário como suspeito."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.history: dict[tuple[int, int], deque[tuple[float, int, bool]]] = defaultdict(deque)

    @app_commands.command(name="armadilha", description="Configura um canal como armadilha anti-spam.")
    @app_commands.describe(canal="Canal de texto que será usado como armadilha. Se não informar, usa o canal atual.")
    @app_commands.default_permissions(manage_guild=True)
    async def armadilha(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
            return

        guild = interaction.guild
        trap_channel = canal or interaction.channel
        if not isinstance(trap_channel, discord.TextChannel):
            await interaction.response.send_message("Use esse comando em um canal de texto ou mencione um canal válido.", ephemeral=True)
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message("Não consegui verificar minhas permissões neste servidor.", ephemeral=True)
            return
        if not bot_member.guild_permissions.manage_channels:
            await interaction.response.send_message("Eu preciso da permissão **Gerenciar canais** para configurar a armadilha.", ephemeral=True)
            return
        if not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message("Eu preciso da permissão **Gerenciar cargos** para atribuir o cargo Suspeito.", ephemeral=True)
            return

        role = discord.utils.get(guild.roles, name=TRAP_ROLE_NAME)
        if role is not None and role.managed:
            await interaction.response.send_message("O cargo Suspeito é gerenciado por uma integração e não pode ser usado.", ephemeral=True)
            return

        try:
            if role is None:
                role = await guild.create_role(
                    name=TRAP_ROLE_NAME,
                    mentionable=False,
                    reason="Cargo usado pela armadilha anti-spam.",
                )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Não foi possível criar o cargo Suspeito.")
            await interaction.response.send_message("Não consegui criar o cargo Suspeito. Verifique a permissão **Gerenciar cargos**.", ephemeral=True)
            return

        if role >= bot_member.top_role:
            await interaction.response.send_message("Coloque o cargo Suspeito abaixo do meu maior cargo na lista de cargos do servidor.", ephemeral=True)
            return

        try:
            await trap_channel.set_permissions(
                guild.default_role,
                view_channel=False,
                send_messages=False,
                reason="Canal configurado como armadilha.",
            )
            await trap_channel.set_permissions(
                role,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                reason="Acesso do cargo Suspeito ao canal armadilha.",
            )
            await trap_channel.set_permissions(
                bot_member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                embed_links=True,
                reason="Acesso do bot ao canal armadilha.",
            )

            current_topic = trap_channel.topic or ""
            if TRAP_TOPIC_MARKER not in current_topic:
                await trap_channel.edit(topic=f"{TRAP_TOPIC_MARKER}\n{current_topic}".strip()[:1024])
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Não foi possível configurar o canal armadilha.")
            await interaction.response.send_message("Não consegui configurar esse canal. Verifique **Gerenciar canais** e a posição do cargo Suspeito.", ephemeral=True)
            return

        self.bot.database.set_trap_config(guild.id, trap_channel.id, role.id)
        await interaction.response.send_message(
            f"Armadilha configurada em {trap_channel.mention}. Quem atingir os critérios de suspeita receberá {role.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="desarmadilha", description="Desativa a armadilha anti-spam de um canal.")
    @app_commands.describe(canal="Canal da armadilha. Se não informar, usa o canal configurado no servidor.")
    @app_commands.default_permissions(manage_guild=True)
    async def desarmadilha(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
            return

        guild = interaction.guild
        config = self.bot.database.get_trap_config(guild.id)
        if config is None:
            await interaction.response.send_message("Não há nenhuma armadilha configurada neste servidor.", ephemeral=True)
            return

        trap_channel = canal or guild.get_channel(config["channel_id"])
        if not isinstance(trap_channel, discord.TextChannel):
            await interaction.response.send_message("O canal da armadilha não está disponível.", ephemeral=True)
            return

        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_channels:
            await interaction.response.send_message("Eu preciso da permissão **Gerenciar canais** para desativar a armadilha.", ephemeral=True)
            return

        role = guild.get_role(config["role_id"])
        try:
            await trap_channel.set_permissions(
                guild.default_role,
                view_channel=True,
                send_messages=True,
                reason="Canal armadilha desativado.",
            )
            if role is not None:
                await trap_channel.set_permissions(
                    role,
                    overwrite=None,
                    reason="Acesso específico da armadilha removido.",
                )

            topic = (trap_channel.topic or "").replace(TRAP_TOPIC_MARKER, "").strip()
            await trap_channel.edit(topic=topic or None)
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Não foi possível desativar o canal armadilha.")
            await interaction.response.send_message("Não consegui restaurar as permissões do canal. Verifique **Gerenciar canais**.", ephemeral=True)
            return

        self.bot.database.clear_trap_config(guild.id)
        await interaction.response.send_message(f"Armadilha desativada em {trap_channel.mention}.", ephemeral=True)

    @staticmethod
    def _cleanup(history: deque[tuple[float, int, bool]], now: float) -> None:
        while history and now - history[0][0] > 2.0:
            history.popleft()

    @staticmethod
    def _is_call_chat(channel: discord.abc.GuildChannel | discord.Thread) -> bool:
        """Identifica canais de voz/stage e chats de texto associados a uma call."""
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return True

        if isinstance(channel, discord.TextChannel):
            category = channel.category
            if category is not None:
                return any(voice.name == channel.name for voice in category.voice_channels)

        return False

    async def _get_suspeito_role(self, guild: discord.Guild) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name=SUSPEITO_ROLE_NAME)
        if role is not None:
            return role

        try:
            role = await guild.create_role(
                name=SUSPEITO_ROLE_NAME,
                reason="Sistema de segurança: comportamento suspeito detectado.",
            )
            return role
        except (discord.Forbidden, discord.HTTPException) as error:
            logger.warning("Não foi possível criar o cargo %s no guild %s: %s", SUSPEITO_ROLE_NAME, guild.id, error)
            return None

    async def _mark_suspect(self, member: discord.Member, reason: str) -> None:
        guild = member.guild
        role = await self._get_suspeito_role(guild)
        if role is None or role in member.roles:
            return

        bot_member = guild.me
        if bot_member is None or role >= bot_member.top_role:
            return

        try:
            await member.add_roles(
                role,
                reason=f"Comportamento suspeito detectado: {reason}",
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            logger.warning("Não foi possível atribuir o cargo %s ao membro %s (%s): %s", SUSPEITO_ROLE_NAME, member.id, guild.id, error)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        now = time.monotonic()
        key = (message.guild.id, message.author.id)
        history = self.history[key]
        self._cleanup(history, now)

        channel_id = message.channel.id
        is_call = self._is_call_chat(message.channel)
        history.append((now, channel_id, is_call))

        # 5 mensagens no mesmo canal em até 1 segundo
        same_channel = [
            item for item in history
            if item[1] == channel_id and now - item[0] <= 1.0
        ]
        if len(same_channel) >= 5:
            await self._mark_suspect(
                message.author,
                "5 mensagens no mesmo canal em até 1 segundo",
            )
            return

        # 2 mensagens em canais diferentes em até 1,5 segundo
        recent_15 = [item for item in history if now - item[0] <= 1.5]
        different_channels = {item[1] for item in recent_15}
        if len(recent_15) >= 2 and len(different_channels) >= 2:
            await self._mark_suspect(
                message.author,
                "2 mensagens em canais diferentes em até 1,5 segundo",
            )
            return

        # 2 mensagens em chats de call em até 2 segundos
        recent_call = [
            item for item in history
            if item[2] and now - item[0] <= 2.0
        ]
        if len(recent_call) >= 2:
            await self._mark_suspect(
                message.author,
                "2 mensagens em chats de call em até 2 segundos",
            )
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Seguranca(bot))
