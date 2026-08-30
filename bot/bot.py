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
        intents.members = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.settings = settings
        self._commands_synced = False

    async def setup_hook(self) -> None:
        await self.load_extension("bot.cogs.core")
        await self.load_extension("bot.cogs.v1_admin")

        # Sync globally once so commands removed from the code disappear from
        # Discord's global registry instead of lingering indefinitely.
        try:
            synced = await self.tree.sync()
            log.info("Synced %d global commands", len(synced))
        except discord.HTTPException:
            log.exception("Failed to sync global commands")

    async def _sync_guild_commands(self, guild: discord.Guild) -> None:
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("Synced %d commands to guild %s", len(synced), guild.id)

    async def on_ready(self) -> None:
        if self.user is None:
            return
        if not self._commands_synced:
            for guild in self.guilds:
                try:
                    await self._sync_guild_commands(guild)
                except discord.HTTPException:
                    log.exception("Failed to sync commands to guild %s", guild.id)
            self._commands_synced = True

        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Connected to %d guild(s)", len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        try:
            await self._sync_guild_commands(guild)
        except discord.HTTPException:
            log.exception("Failed to sync commands to new guild %s", guild.id)


def create_bot(settings: Settings) -> AquiJas:
    return AquiJas(settings)
