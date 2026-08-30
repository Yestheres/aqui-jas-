from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from .agent.tools import ToolRegistry
from .ai.client import AIClient, AIConfig
from .config import Settings
from .database import Database

log = logging.getLogger(__name__)


class AquiJas(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        # Start with non-privileged intents. Privileged intents are enabled only
        # when a feature actually needs them and the Discord portal is configured.
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
        self.ai: AIClient | None = None
        if settings.ai_api_key and settings.ai_model:
            self.ai = AIClient(
                AIConfig(
                    api_key=settings.ai_api_key,
                    base_url=settings.ai_base_url,
                    model=settings.ai_model,
                )
            )

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.load_extension("bot.cogs.core")
        await self.load_extension("bot.cogs.ai")

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

    async def close(self) -> None:
        await self.db.close()
        await super().close()


def create_bot(settings: Settings) -> AquiJas:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    return AquiJas(settings)
