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

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.load_extension("bot.cogs.core")
        await self.load_extension("bot.cogs.ai")

        # Global commands can take time to propagate. Development guilds are
        # synced immediately when DEV_GUILDS is configured in the environment.
        if self.settings.dev_guilds:
            for guild_id in self.settings.dev_guilds:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Synced commands to development guild %s", guild_id)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        if self.user is not None:
            log.info("Logged in as %s (%s)", self.user, self.user.id)
            log.info("Connected to %d guild(s)", len(self.guilds))

    async def close(self) -> None:
        await self.db.close()
        await super().close()


def create_bot(settings: Settings) -> AquiJas:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    return AquiJas(settings)
