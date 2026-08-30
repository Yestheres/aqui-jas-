from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

from .config import Settings

log = logging.getLogger(__name__)

GITHUB_URL = "https://github.com/Yestheres/aqui-jas-"


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
                "Aqui Jas — ferramentas simples e bonitas para administrar seu servidor."
            ),
        )
        self.settings = settings
        self.started_at = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        await self.load_extension("bot.cogs.core")
        await self.load_extension("bot.cogs.v1_admin")

        current_commands = list(self.tree.get_commands())

        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)

            # Remove every old registration first. The previous AI build left
            # stale global and guild commands, which Discord then displayed twice.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)

            # Register the current command objects directly in the test guild.
            # Do NOT copy globals: that is what created the duplicate scope.
            for command in current_commands:
                self.tree.add_command(command, guild=guild, override=True)

            synced = await self.tree.sync(guild=guild)
            log.info(
                "Published %d guild-only commands to DEV_GUILD_ID=%s: %s",
                len(synced),
                self.settings.dev_guild_id,
                ", ".join(command.name for command in synced),
            )
        else:
            synced = await self.tree.sync()
            log.info(
                "Published %d global commands: %s",
                len(synced),
                ", ".join(command.name for command in synced),
            )

        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/ajuda • seu servidor",
            ),
        )

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
