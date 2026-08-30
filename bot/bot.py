from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

from .config import Settings

log = logging.getLogger(__name__)


class AquiJas(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            description=(
                "Aqui Jas — ferramentas bonitas, simples e úteis para administrar seu servidor."
            ),
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/ajuda • seu servidor",
            ),
        )
        self.settings = settings
        self.started_at = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        # The bot now uses ONE application-command scope: global.
        # Older versions created both guild and global commands, which made
        # Discord display duplicates. Remove the legacy guild registrations
        # and then publish the current tree globally.
        if self.settings.dev_guild_id:
            legacy_guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.clear_commands(guild=legacy_guild)
            try:
                await self.tree.sync(guild=legacy_guild)
                log.info("Cleared legacy guild commands for %s", legacy_guild.id)
            except discord.HTTPException:
                log.exception("Failed clearing legacy guild commands for %s", legacy_guild.id)

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
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Connected to %d guild(s)", len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("Joined guild %s (%s); commands are global", guild.name, guild.id)


def create_bot(settings: Settings) -> AquiJas:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    return AquiJas(settings)
