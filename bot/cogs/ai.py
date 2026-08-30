from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..ai.client import AIClient, AIConfig

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5-mini"


class AIConfigModal(discord.ui.Modal, title="Configurar IA do servidor"):
    api_key = discord.ui.TextInput(
        label="API Key",
        placeholder="Cole a chave da API aqui",
        style=discord.TextStyle.short,
        required=True,
        min_length=1,
        max_length=500,
    )
    base_url = discord.ui.TextInput(
        label="URL da API (opcional)",
        placeholder="https://api.openai.com/v1",
        style=discord.TextStyle.short,
        required=False,
        max_length=300,
    )
    model = discord.ui.TextInput(
        label="Modelo (opcional)",
        placeholder="gpt-5-mini",
        style=discord.TextStyle.short,
        required=False,
        max_length=150,
    )

    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        base_url = str(self.base_url.value).strip() or DEFAULT_BASE_URL
        model = str(self.model.value).strip() or DEFAULT_MODEL
        api_key = str(self.api_key.value).strip()

        if not base_url.startswith(("http://", "https://")):
            await interaction.response.send_message(
                "❌ A URL da API precisa começar com `http://` ou `https://`.",
                ephemeral=True,
            )
            return

        await self.bot.db.set_ai_config(
            self.guild_id, api_key, base_url.rstrip("/"), model
        )
        await interaction.response.send_message(
            "✅ **IA configurada para este servidor!**\n\n"
            f"• Modelo: `{discord.utils.escape_markdown(model)}`\n"
            f"• Endpoint: `{discord.utils.escape_markdown(base_url)}`\n\n"
            "A chave foi salva na configuração deste servidor e não será exibida nas mensagens do bot.",
            ephemeral=True,
        )


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="configia", description="Configura a IA usada por este servidor.")
    @app_commands.default_permissions(manage_guild=True)
    async def configure(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return
        await interaction.response.send_modal(AIConfigModal(self.bot, interaction.guild.id))

    @app_commands.command(name="iaremover", description="Remove a IA configurada neste servidor.")
    @app_commands.default_permissions(manage_guild=True)
    async def remove_config(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return

        await self.bot.db.clear_ai_config(interaction.guild.id)
        await interaction.response.send_message(
            "🗑️ A configuração de IA deste servidor foi removida.", ephemeral=True
        )

    @app_commands.command(name="iastatus", description="Mostra se a IA está configurada neste servidor.")
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return

        config = await self.bot.db.get_ai_config(interaction.guild.id)
        if config is None:
            await interaction.response.send_message(
                "⚪ A IA ainda não foi configurada neste servidor. Use `/configia`.",
                ephemeral=True,
            )
            return

        _, base_url, model = config
        await interaction.response.send_message(
            "🟢 **IA configurada**\n"
            f"• Modelo: `{discord.utils.escape_markdown(model)}`\n"
            f"• Endpoint: `{discord.utils.escape_markdown(base_url)}`\n"
            "• Chave: `configurada`",
            ephemeral=True,
        )

    @app_commands.command(name="ia", description="Converse com a IA configurada para este servidor.")
    @app_commands.describe(pergunta="O que você quer perguntar?")
    async def ask(self, interaction: discord.Interaction, pergunta: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return

        config = await self.bot.db.get_ai_config(interaction.guild.id)
        if config is None:
            await interaction.response.send_message(
                "⚪ A IA deste servidor ainda não foi configurada. Um administrador deve usar `/configia`.",
                ephemeral=True,
            )
            return

        api_key, base_url, model = config
        client = AIClient(AIConfig(api_key=api_key, base_url=base_url, model=model))

        await interaction.response.defer(thinking=True)
        try:
            answer = await client.chat(
                "Você é o assistente do Aqui Jas. Seja útil, direto e seguro. "
                "Quando uma ação no Discord for necessária, não finja que a executou.",
                pergunta,
            )
        except Exception:
            await interaction.followup.send(
                "❌ Não consegui consultar a IA configurada neste servidor agora. "
                "Verifique a chave, o endpoint e o modelo em `/configia`."
            )
            return

        if len(answer) > 1900:
            answer = answer[:1897] + "..."
        await interaction.followup.send(answer)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AI(bot))
