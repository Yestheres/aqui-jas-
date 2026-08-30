from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from ..agent.service import AgentService, preview_text


class PlanView(discord.ui.View):
    def __init__(self, service: AgentService, interaction: discord.Interaction, plan) -> None:
        super().__init__(timeout=120)
        self.service = service
        self.original = interaction
        self.plan = plan

    async def _finish(self, interaction: discord.Interaction, execute: bool) -> None:
        if interaction.user.id != self.original.user.id:
            await interaction.response.send_message("Só quem criou este plano pode decidir.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        if not execute:
            await interaction.response.edit_message(content="❌ Plano rejeitado. Nenhuma alteração foi executada.", view=self)
            return
        self.plan.dry_run = False
        await interaction.response.edit_message(content="⏳ Executando o plano...", view=self)
        report = await self.service.execute(self.original.guild, self.original.user.id, self.plan)
        lines = ["✅ **Execução concluída**"]
        for item in report:
            if item["status"] == "executed":
                lines.append(f"• `{item['id']}` `{item['type']}` → ✅")
            else:
                lines.append(f"• `{item['id']}` `{item['type']}` → ❌ {item['error']}")
        await interaction.edit_original_response(content="\n".join(lines), view=self)

    @discord.ui.button(label="Executar", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._finish(interaction, True)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._finish(interaction, False)


class Agent(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = AgentService(bot)
        self._locks: dict[int, asyncio.Lock] = {}

    @app_commands.command(name="agente", description="Gera um plano seguro de alterações no servidor.")
    @app_commands.describe(pedido="O que você quer organizar, configurar ou alterar?")
    @app_commands.default_permissions(manage_guild=True)
    async def agent(self, interaction: discord.Interaction, pedido: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Este comando só funciona em servidores.", ephemeral=True)
            return
        lock = self._locks.setdefault(guild.id, asyncio.Lock())
        if lock.locked():
            await interaction.response.send_message("Já existe um plano sendo analisado neste servidor.", ephemeral=True)
            return
        async with lock:
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                plan = await self.service.generate_plan(guild, pedido)
            except Exception as exc:
                await interaction.followup.send(f"❌ Não consegui gerar um plano seguro: {exc}", ephemeral=True)
                return
            text = preview_text(plan)
            if len(text) > 3500:
                text = text[:3497] + "..."
            message = (
                "🧠 **Plano gerado — nada foi alterado ainda.**\n\n"
                + text
                + "\n\n"
                + ("⚠️ Este plano contém ações que exigem confirmação." if plan.requires_confirmation else "✅ Nenhuma ação de risco médio/alto foi detectada.")
            )
            await interaction.followup.send(
                message,
                view=PlanView(self.service, interaction, plan),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Agent(bot))
