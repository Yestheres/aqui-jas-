from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ia", description="Converse com a IA do bot.")
    @app_commands.describe(pergunta="O que você quer perguntar?")
    async def ask(self, interaction: discord.Interaction, pergunta: str) -> None:
        client = getattr(self.bot, "ai", None)
        if client is None:
            await interaction.response.send_message(
                "A IA ainda não foi configurada neste ambiente.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            answer = await client.chat(
                "Você é o assistente do Aqui Jas. Seja útil, direto e seguro. "
                "Quando uma ação no Discord for necessária, não finja que a executou.",
                pergunta,
            )
        except Exception:
            await interaction.followup.send(
                "Não consegui consultar o provedor de IA agora."
            )
            return

        if len(answer) > 1900:
            answer = answer[:1897] + "..."
        await interaction.followup.send(answer)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AI(bot))
