from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class V1Admin(commands.Cog):
    """Initial V1 server administration and diagnostics."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="servidor", description="Mostra informações e recursos deste servidor.")
    async def server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Este comando só pode ser usado em um servidor.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🏠 {guild.name}", color=discord.Color.blurple())
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Membros", value=str(guild.member_count or 0), inline=True)
        embed.add_field(name="Canais", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Cargos", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Categorias", value=str(len(guild.categories)), inline=True)
        embed.add_field(name="IA", value="🟢 Configurada" if await self.bot.db.get_ai_config(guild.id) else "⚪ Não configurada", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ping", description="Verifica a latência do Aqui Jas.")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"🏓 Pong! `{round(self.bot.latency * 1000)}ms`")

    @app_commands.command(name="ajuda", description="Mostra os recursos disponíveis do Aqui Jas.")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="🤖 Aqui Jas", description="Central de comandos da V1")
        embed.add_field(name="🧠 IA", value="`/configia` · `/iastatus` · `/iaremover` · `/ia`", inline=False)
        embed.add_field(name="🏠 Servidor", value="`/servidor` · `/ping`", inline=False)
        embed.set_footer(text="Mais módulos serão adicionados nas próximas versões.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(V1Admin(bot))
