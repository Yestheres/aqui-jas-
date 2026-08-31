from __future__ import annotations

import time
from collections import defaultdict, deque

import discord
from discord.ext import commands


SUSPEITO_ROLE_NAME = "Suspeito"

# Regras solicitadas:
# - 5 mensagens no mesmo canal em 1 segundo
# - 2 mensagens em canais diferentes em 1,5 segundo
# - 2 mensagens em canais de call em 2 segundos


class Seguranca(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.messages: dict[tuple[int, int], deque[tuple[float, int, int]]] = defaultdict(deque)

    def _cleanup(self, history: deque[tuple[float, int, int]], now: float) -> None:
        while history and now - history[0][0] > 2.0:
            history.popleft()

    @staticmethod
    def _is_call_channel(channel: discord.abc.GuildChannel) -> bool:
        return isinstance(channel, (discord.VoiceChannel, discord.StageChannel))

    async def _get_suspeito_role(self, guild: discord.Guild) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name=SUSPEITO_ROLE_NAME)
        if role is not None:
            return role

        try:
            return await guild.create_role(
                name=SUSPEITO_ROLE_NAME,
                reason="Cargo usado pelo sistema de detecção de comportamento suspeito.",
            )
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def _mark_suspect(self, member: discord.Member, rule: str) -> None:
        role = await self._get_suspeito_role(member.guild)
        if role is None:
            print(
                f"[SEGURANCA] Não foi possível obter o cargo '{SUSPEITO_ROLE_NAME}' "
                f"em {member.guild.name} ({member.guild.id}). Regra: {rule}"
            )
            return

        if role in member.roles:
            return

        # O Discord não permite ao bot atribuir um cargo que esteja acima
        # ou no mesmo nível do maior cargo do próprio bot.
        me = member.guild.me
        if me is None or role >= me.top_role:
            print(
                f"[SEGURANCA] Cargo '{SUSPEITO_ROLE_NAME}' não pode ser atribuído "
                f"em {member.guild.name}. Mova o cargo abaixo do cargo do bot."
            )
            return

        try:
            await member.add_roles(
                role,
                reason=f"Detecção de comportamento suspeito: {rule}",
            )
            print(
                f"[SEGURANCA] {member} ({member.id}) recebeu @{role.name} "
                f"em {member.guild.name} — {rule}"
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(
                f"[SEGURANCA] Falha ao dar @{role.name} para {member} "
                f"({member.id}): {exc}"
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        if not isinstance(message.author, discord.Member):
            return

        now = time.monotonic()
        key = (message.guild.id, message.author.id)
        history = self.messages[key]
        self._cleanup(history, now)

        channel_id = message.channel.id
        history.append((now, channel_id, message.id))

        # Regra 1: 5 mensagens no mesmo canal em 1 segundo.
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

        # Regra 2: 2 mensagens em canais diferentes em 1,5 segundo.
        recent_15 = [item for item in history if now - item[0] <= 1.5]
        distinct_channels = {item[1] for item in recent_15}
        if len(recent_15) >= 2 and len(distinct_channels) >= 2:
            await self._mark_suspect(
                message.author,
                "mensagens em 2 canais diferentes em até 1,5 segundo",
            )
            return

        # Regra 3: 2 mensagens em canais de call em 2 segundos.
        # A mensagem precisa estar em um canal de voz/stage; isso aproveita
        # o chat de texto associado às calls.
        if self._is_call_channel(message.channel):
            recent_calls = [
                item for item in history
                if now - item[0] <= 2.0
                and self._is_call_channel(self.bot.get_channel(item[1]))
            ]
            if len(recent_calls) >= 2:
                await self._mark_suspect(
                    message.author,
                    "2 mensagens em canais de call em até 2 segundos",
                )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Seguranca(bot))
