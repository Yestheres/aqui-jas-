from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from .config import Settings

log = logging.getLogger(__name__)


class AquiJas(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        # Only request the non-privileged GUILDS intent. This keeps the bot
        # deployable without any privileged-intent switch in the Developer Portal.
        intents = discord.Intents.none()
        intents.guilds = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            description="Aqui Jas — ferramentas bonitas, simples e úteis para seu servidor.",
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/ajuda • seu servidor",
            ),
        )
        self.settings = settings
        self.started_at = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        # Keep one command scope only: global. Do not sync on every on_ready,
        # otherwise reconnects can cause unnecessary API traffic and rate limits.
        await self.load_extension("bot.cogs.core")
        await self.load_extension("bot.cogs.v1_admin")

        synced = await self.tree.sync()
        log.info(
            "Published %d global commands: %s",
            len(synced),
            ", ".join(command.name for command in synced),
        )

    async def on_ready(self) -> None:
        if self.user is None:
            return

        guild_count = len(self.guilds)
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"/ajuda • {guild_count} servidor{'es' if guild_count != 1 else ''}",
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Connected to %d guild(s)", guild_count)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("Joined guild %s (%s); commands are global", guild.name, guild.id)


def create_bot(settings: Settings) -> AquiJas:
    return AquiJas(settings)
