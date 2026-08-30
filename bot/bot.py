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

        commands_to_publish = list(self.tree.get_commands())

        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)

            # Clear global commands first.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()

            # Clear old commands registered specifically to the development guild.
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)

            # Register the current commands directly on the guild.
            for command in commands_to_publish:
                self.tree.add_command(command, guild=guild)

            synced = await self.tree.sync(guild=guild)
            log.info(
                "Published %d guild-only commands to DEV_GUILD_ID=%s",
                len(synced),
                self.settings.dev_guild_id,
            )
            return

        synced = await self.tree.sync()
        log.info("Published %d global commands", len(synced))

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
