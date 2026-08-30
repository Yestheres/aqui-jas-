from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import Settings

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

    async def setup_hook(self) -> None:
        await self.load_extension("bot.cogs.core")
        await self.load_extension("bot.cogs.v1_admin")

    async def on_ready(self) -> None:
        if self.user is None:
            return
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            try:
                synced = await self.tree.sync(guild=guild)
                log.info("Synced %d commands to guild %s", len(synced), guild.id)
            except discord.HTTPException:
                log.exception("Failed to sync commands to guild %s", guild.id)
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Connected to %d guild(s)", len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        self.tree.copy_global_to(guild=guild)
        try:
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to new guild %s", len(synced), guild.id)
        except discord.HTTPException:
            log.exception("Failed to sync commands to new guild %s", guild.id)


def create_bot(settings: Settings) -> AquiJas:
    return AquiJas(settings)
