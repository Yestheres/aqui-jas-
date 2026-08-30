from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..ai.client import AIClient, AIConfig

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class AIConfigModal(discord.ui.Modal, title="Configurar IA do servidor"):
    api_key = discord.ui.TextInput(
        label="API Key",
        placeholder="Cole sua chave da API aqui",
        style=discord.TextStyle.short,
        required=True,
        min_length=1,
        max_length=500,
    )
    base_url = discord.ui.TextInput(
        label="URL da API",
        placeholder=DEFAULT_BASE_URL,
        default=DEFAULT_BASE_URL,
        style=discord.TextStyle.short,
        required=False,
        max_length=300,
    )
    model = discord.ui.TextInput(
        label="Modelo",
        placeholder=DEFAULT_MODEL,
        default=DEFAULT_MODEL,
        style=discord.TextStyle.short,
        required=False,
        max_length=150,
    )

    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        api_key = str(self.api_key.value).strip()
        base_url = str(self.base_url.value).strip() or DEFAULT_BASE_URL
        model = str(self.model.value).strip() or DEFAULT_MODEL

        if api_key.startswith("gsk_") and base_url == OPENROUTER_BASE_URL:
            base_url = DEFAULT_BASE_URL
        if api_key.startswith("gsk_") and model == "openrouter/free":
            model = DEFAULT_MODEL

        if not base_url.startswith(("http://", "https://")):
            await interaction.response.send_message(
                "❌ A URL válida precisa começar com `http://` ou `https://`.",
                ephemeral=True,
            )
            return

        await self.bot.db.set_ai_config(
            self.guild_id, api_key, base_url.rstrip("/"), model
        )
        await interaction.response.send_message(
            "✅ **IA configurada para este servidor!**\n\n"
            f"• Endpoint: `{discord.utils.escape_markdown(base_url)}`\n"
            f"• Modelo: `{discord.utils.escape_markdown(model)}`\n\n"
            "`/ia` e `/agente` usarão essa configuração.",
            ephemeral=True,
        )


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _global_fallback(self) -> tuple[str, str, str] | None:
        settings = getattr(self.bot, "settings", None)
        if settings is None or not settings.ai_api_key:
            return None
        return (
            settings.ai_api_key,
            settings.ai_base_url or DEFAULT_BASE_URL,
            settings.ai_model or DEFAULT_MODEL,
        )

    async def _get_config(self, guild_id: int) -> tuple[str, str, str] | None:
        return await self.bot.db.get_ai_config(guild_id) or self._global_fallback()

    @app_commands.command(name="configia", description="Configura a IA usada por este servidor.")
    @app_commands.default_permissions(manage_guild=True)
    async def configure(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return
        await interaction.response.send_modal(AIConfigModal(self.bot, interaction.guild.id))

    @app_commands.command(name="iastatus", description="Mostra o status da IA deste servidor.")
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return

        server_config = await self.bot.db.get_ai_config(interaction.guild.id)
        config = server_config or self._global_fallback()
        if config is None:
            await interaction.response.send_message(
                "⚪ Nenhuma IA configurada. Use `/configia`.", ephemeral=True
            )
            return

        _, base_url, model = config
        source = "servidor" if server_config else "fallback global"
        await interaction.response.send_message(
            "🟢 **IA disponível**\n"
            f"• Fonte: `{source}`\n"
            f"• Endpoint: `{discord.utils.escape_markdown(base_url)}`\n"
            f"• Modelo: `{discord.utils.escape_markdown(model)}`",
            ephemeral=True,
        )

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
            "🗑️ A configuração própria deste servidor foi removida.", ephemeral=True
        )

    @app_commands.command(name="ia", description="Converse com a IA deste servidor.")
    @app_commands.describe(pergunta="O que você quer perguntar?")
    async def ask(self, interaction: discord.Interaction, pergunta: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um servidor.", ephemeral=True
            )
            return

        config = await self._get_config(interaction.guild.id)
        if config is None:
            await interaction.response.send_message(
                "⚪ Configure a IA com `/configia` ou defina o fallback global.",
                ephemeral=True,
            )
            return

        api_key, base_url, model = config
        client = AIClient(AIConfig(api_key=api_key, base_url=base_url, model=model))

        memory = await self.bot.db.get_memory(interaction.guild.id, interaction.user.id)
        messages = [
            {
                "role": "system",
                "content": (
                    "Você é o assistente do Aqui Jas. Seja útil, direto e seguro. "
                    "Não afirme ter executado ações do Discord que não foram executadas."
                ),
            },
            *({"role": role, "content": content} for role, content in memory),
            {"role": "user", "content": pergunta},
        ]

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            answer = await client.chat(messages)
        except Exception:
            await interaction.followup.send(
                "❌ Não consegui consultar a IA. Verifique a chave, endpoint e modelo.",
                ephemeral=True,
            )
            return

        await self.bot.db.add_memory(
            interaction.guild.id, interaction.user.id, "user", pergunta
        )
        await self.bot.db.add_memory(
            interaction.guild.id, interaction.user.id, "assistant", answer
        )

        await interaction.followup.send(answer[:1900], ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AI(bot))
