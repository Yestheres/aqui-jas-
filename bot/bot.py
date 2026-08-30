from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from .agent.tools import ToolRegistry
from .config import Settings
from .database import Database

log = logging.getLogger(__name__)


class AquiJas(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.settings = settings
        self.db = Database(settings.database_path)
        self.tools = ToolRegistry()
        self._commands_synced = False

    async def setup_hook(self) -> None:
        await self.db.connect()
        for extension in (
            "bot.cogs.core",
            "bot.cogs.ai",
            "bot.cogs.v1_admin",
            "bot.cogs.agent",
        ):
            await self.load_extension(extension)

        # If DEV_GUILD_ID is set in Shard Cloud, sync there during startup.
        # Guild commands propagate immediately and do not depend on global sync.
        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Synced commands to DEV_GUILD_ID=%s", self.settings.dev_guild_id)

    async def on_ready(self) -> None:
        if self.user is None:
            return

        if not self._commands_synced:
            for guild in self.guilds:
                self.tree.copy_global_to(guild=guild)
                try:
                    await self.tree.sync(guild=guild)
                except discord.HTTPException:
                    log.exception("Failed to sync commands to guild %s", guild.id)
            self._commands_synced = True

        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Connected to %d guild(s)", len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        self.tree.copy_global_to(guild=guild)
        try:
            await self.tree.sync(guild=guild)
        except discord.HTTPException:
            log.exception("Failed to sync commands to new guild %s", guild.id)

    async def close(self) -> None:
        await self.db.close()
        await super().close()


def create_bot(settings: Settings) -> AquiJas:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    return AquiJas(settings)
