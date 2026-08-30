from __future__ import annotations

import logging
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
        )
        self.settings = settings

    async def setup_hook(self) -> None:
        await self.load_extension("bot.cogs.core")
        await self.load_extension("bot.cogs.v1_admin")

        if self.settings.dev_guild_id:
            # Publish the current command set only to the development guild.
            # Do this before clearing the global tree so the guild receives
            # the fresh commands immediately.
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)

            # Remove any old global registrations. Keeping both global and
            # guild versions is what causes Discord to show duplicates.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()

            log.info(
                "Synced %d guild-only commands to DEV_GUILD_ID=%s; cleared global commands",
                len(synced),
                self.settings.dev_guild_id,
            )
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global commands", len(synced))

    async def on_ready(self) -> None:
        if self.user is None:
            return
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Connected to %d guild(s)", len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if self.settings.dev_guild_id:
            return
        synced = await self.tree.sync(guild=guild)
        log.info("Synced %d commands to new guild %s", len(synced), guild.id)


def create_bot(settings: Settings) -> AquiJas:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    return AquiJas(settings)
