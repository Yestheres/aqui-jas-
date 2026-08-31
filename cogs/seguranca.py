from __future__ import annotations

import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

SUSPEITO_ROLE_NAME = "Suspeito"


class Seguranca(commands.Cog):
    """Detecta padrões rápidos de mensagens e marca o usuário como suspeito."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.history: dict[tuple[int, int], deque[tuple[float, int, bool]]] = defaultdict(deque)

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
            print(f"[SEGURANCA] Não foi possível criar @{SUSPEITO_ROLE_NAME}: {error}")
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
            print(f"[SEGURANCA] Não foi possível dar o cargo a {member}: {error}")

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
