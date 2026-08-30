from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from ..agent.service import AgentService, preview_text


class PlanView(discord.ui.View):
    def __init__(self, service: AgentService, original: discord.Interaction, plan) -> None:
        super().__init__(timeout=180)
        self.service = service
        self.original = original
        self.plan = plan
        self.finished = False

    async def _owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original.user.id:
            await interaction.response.send_message(
                "Só quem criou este plano pode decidir.", ephemeral=True
            )
            return False
        if self.finished:
            await interaction.response.send_message(
                "Este plano já foi finalizado.", ephemeral=True
            )
            return False
        return True

    async def _disable(self) -> None:
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Executar", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._owner(interaction):
            return
        self.finished = True
        await self._disable()
        await interaction.response.edit_message(
            content="⏳ **Executando o plano aprovado...**",
            view=self,
        )

        try:
            report = await self.service.execute(
                self.original.guild,
                self.original.user.id,
                self.plan,
            )
        except Exception as exc:
            await interaction.edit_original_response(
                content=f"❌ **Falha na execução:** `{exc}`",
                view=self,
            )
            return

        lines = ["✅ **Relatório de execução**"]
        for item in report:
            if item["status"] == "executed":
                reused = " · reutilizado" if item.get("result", {}).get("reused") else ""
                lines.append(f"• `{item['id']}` `{item['type']}` → ✅{reused}")
            else:
                lines.append(
                    f"• `{item['id']}` `{item['type']}` → ❌ {item.get('error', 'erro desconhecido')}"
                )
        await interaction.edit_original_response(
            content="\n".join(lines),
            view=self,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._owner(interaction):
            return
        self.finished = True
        await self._disable()
        await interaction.response.edit_message(
            content="❌ **Plano cancelado. Nenhuma alteração foi executada.**",
            view=self,
        )


class Agent(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = AgentService(bot)
        self._locks: dict[int, asyncio.Lock] = {}

    @app_commands.command(
        name="agente",
        description="Analisa um pedido, mostra um plano e aguarda sua aprovação.",
    )
    @app_commands.describe(pedido="O que você quer que o Aqui Jas faça?")
    @app_commands.default_permissions(manage_guild=True)
    async def agent(self, interaction: discord.Interaction, pedido: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Este comando só funciona em servidores.", ephemeral=True
            )
            return

        pedido = pedido.strip()
        if not pedido:
            await interaction.response.send_message(
                "Escreva o que você quer alterar.", ephemeral=True
            )
            return
        if len(pedido) > 1500:
            await interaction.response.send_message(
                "O pedido deve ter no máximo 1500 caracteres.", ephemeral=True
            )
            return

        lock = self._locks.setdefault(guild.id, asyncio.Lock())
        if lock.locked():
            await interaction.response.send_message(
                "⏳ Já existe um plano sendo analisado neste servidor.",
                ephemeral=True,
            )
            return

        async with lock:
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                plan = await self.service.generate_plan(guild, pedido)
            except Exception as exc:
                await interaction.followup.send(
                    f"❌ Não consegui gerar um plano seguro: `{exc}`",
                    ephemeral=True,
                )
                return

            preview = preview_text(plan)
            if len(preview) > 3500:
                preview = preview[:3497] + "..."

            confirmation = (
                "⚠️ **Este plano contém ações que exigem confirmação.**"
                if plan.requires_confirmation
                else "🟢 **Prévia pronta.** A execução só acontece quando você clicar em Executar."
            )

            await interaction.followup.send(
                "🧠 **Plano gerado — nada foi alterado ainda.**\n\n"
                + preview
                + "\n\n"
                + confirmation,
                view=PlanView(self.service, interaction, plan),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Agent(bot))
