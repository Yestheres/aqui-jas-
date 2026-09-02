from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from services.ai import generate_ai_description


class Geral(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="sobre", description="Mostra informações sobre o bot.")
    async def sobre(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title=f"✨ {self.bot.user.name if self.bot.user else 'Bot'}",
            description="Bot Discord leve e modular.",
            color=discord.Color.blurple(),
        )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="🏠 Servidores", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="📦 discord.py", value=f"`{discord.__version__}`", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="servidor", description="Mostra informações básicas deste servidor.")
    async def servidor(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
            return

        guild = interaction.guild
        embed = discord.Embed(title=f"🏠 {guild.name}", color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👥 Membros", value=f"`{guild.member_count or 'indisponível'}`", inline=True)
        embed.add_field(name="💬 Canais", value=f"`{len(guild.channels)}`", inline=True)
        embed.add_field(name="🎭 Cargos", value=f"`{max(0, len(guild.roles) - 1)}`", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ajuda", description="Mostra os comandos disponíveis do bot.")
    async def ajuda(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Ajuda do bot",
            description="Comandos disponíveis e como usá-los.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="/parceria",
            value="Pode ser usado em qualquer canal do servidor. Informe `descricao` e `link` para enviar uma solicitação à staff.",
            inline=False,
        )
        embed.add_field(name="/configurar", value="Configura o canal privado de aprovação (staff).", inline=False)
        embed.add_field(name="/canal-publicacao", value="Define um canal específico para publicar parcerias no servidor.", inline=False)
        embed.add_field(name="/armadilha", value="Configura o canal armadilha e marca automaticamente sinais de spam.", inline=False)
        embed.add_field(name="/desarmadilha", value="Desativa a armadilha e restaura o canal.", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="parceria-ai", description="Gera uma descrição de parceria com IA para você usar na solicitação.")
    @app_commands.describe(
        nome="Nome do seu servidor ou comunidade.",
        sobre="Resumo do que o servidor faz, temáticas e proposta.",
        foco="Foco principal da parceria, como comunidade, eventos, educação, games, etc.",
    )
    async def parceria_ai(
        self,
        interaction: discord.Interaction,
        nome: str,
        sobre: str,
        foco: str = "comunidade",
    ) -> None:
        nome = nome.strip()
        sobre = sobre.strip()
        foco = foco.strip() or "comunidade"

        if not nome or not sobre:
            await interaction.response.send_message(
                "Informe o nome do servidor e um resumo do que ele faz para gerar a descrição.",
                ephemeral=True,
            )
            return

        description = generate_ai_description(nome, sobre, foco)
        await interaction.response.send_message(
            "Descrição sugerida:\n\n" + description,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Geral(bot))
