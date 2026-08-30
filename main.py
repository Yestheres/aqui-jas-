from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não está configurado.")

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "aqui_jas.sqlite3"
INVITE_RE = re.compile(r"^(?:https?://)?(?:www\\.)?(?:discord(?:app)?\\.com/invite|discord\\.gg)/([A-Za-z0-9-]+)(?:/)?$", re.I)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("aqui_jas")


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS guild_settings (guild_id INTEGER PRIMARY KEY, partnership_channel_id INTEGER, staff_channel_id INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS partnership_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, description TEXT NOT NULL, invite_url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, decided_at TEXT)")
        conn.commit()


def set_channel(guild_id: int, field: str, channel_id: int) -> None:
    if field not in {"partnership_channel_id", "staff_channel_id"}:
        raise ValueError("Campo inválido")
    with db() as conn:
        conn.execute(f"INSERT INTO guild_settings (guild_id, {field}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {field}=excluded.{field}", (guild_id, channel_id))
        conn.commit()


def get_settings(guild_id: int) -> sqlite3.Row | None:
    with db() as conn:
        return conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)).fetchone()


def has_pending(guild_id: int, user_id: int) -> bool:
    with db() as conn:
        return conn.execute("SELECT 1 FROM partnership_requests WHERE guild_id=? AND user_id=? AND status='pending' LIMIT 1", (guild_id, user_id)).fetchone() is not None


def create_request(guild_id: int, user_id: int, description: str, invite_url: str) -> int:
    with db() as conn:
        cur = conn.execute("INSERT INTO partnership_requests (guild_id,user_id,description,invite_url,created_at) VALUES (?,?,?,?,?)", (guild_id, user_id, description, invite_url, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return int(cur.lastrowid)


def decide_request(request_id: int, status: str) -> sqlite3.Row | None:
    if status not in {"approved", "rejected"}:
        raise ValueError("status inválido")
    with db() as conn:
        row = conn.execute("SELECT * FROM partnership_requests WHERE id=? AND status='pending'", (request_id,)).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE partnership_requests SET status=?, decided_at=? WHERE id=?", (status, datetime.now(timezone.utc).isoformat(), request_id))
        conn.commit()
        return row


async def validate_invite(link: str) -> tuple[bool, str]:
    match = INVITE_RE.fullmatch(link.strip())
    if not match:
        return False, "Use um convite do Discord, como `https://discord.gg/exemplo`."
    normalized = f"https://discord.gg/{match.group(1)}"
    try:
        invite = await bot.fetch_invite(normalized, with_counts=False)
    except discord.NotFound:
        return False, "Esse convite é inválido ou não existe."
    except discord.HTTPException:
        return False, "Não consegui verificar o convite agora."
    if getattr(invite, "max_age", None) != 0:
        return False, "O convite precisa ser permanente, sem expiração."
    if getattr(invite, "temporary", False):
        return False, "O convite temporário não pode ser usado."
    return True, normalized


def can_manage(guild: discord.Guild, member: discord.Member | discord.User) -> bool:
    return member.id == guild.owner_id or (isinstance(member, discord.Member) and (member.guild_permissions.administrator or member.guild_permissions.manage_guild))


class DecisionView(discord.ui.View):
    def __init__(self, request_id: int) -> None:
        super().__init__(timeout=None)
        self.request_id = request_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not can_manage(interaction.guild, interaction.user):
            await interaction.response.send_message("❌ Você precisa ser dono do servidor ou ter **Gerenciar Servidor**.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Aceitar parceria", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.finish(interaction, True)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.finish(interaction, False)

    async def finish(self, interaction: discord.Interaction, approved: bool) -> None:
        row = decide_request(self.request_id, "approved" if approved else "rejected")
        if row is None:
            await interaction.response.send_message("Essa solicitação já foi decidida.", ephemeral=True)
            return
        if not approved:
            await interaction.response.send_message("❌ Parceria recusada.", ephemeral=True)
        else:
            settings = get_settings(int(row["guild_id"]))
            channel_id = settings["partnership_channel_id"] if settings else None
            destination = bot.get_channel(int(channel_id)) if channel_id else None
            if destination is None and channel_id:
                try:
                    destination = await bot.fetch_channel(int(channel_id))
                except discord.HTTPException:
                    destination = None
            if not isinstance(destination, discord.TextChannel):
                await interaction.response.send_message("❌ Canal de parceria não está disponível.", ephemeral=True)
                return
            embed = discord.Embed(title="🤝 Nova parceria", description=str(row["description"]), color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
            embed.add_field(name="🔗 Convite", value=f"[Entrar no servidor]({row['invite_url']})", inline=False)
            embed.set_footer(text=f"Solicitação #{row['id']}")
            try:
                await destination.send(embed=embed)
            except discord.HTTPException:
                await interaction.response.send_message("❌ Não consegui publicar a parceria.", ephemeral=True)
                return
            await interaction.response.send_message("✅ Parceria aprovada e publicada.", ephemeral=True)
        if interaction.message:
            embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed(title="Solicitação de parceria")
            embed.color = discord.Color.green() if approved else discord.Color.red()
            embed.add_field(name="Resultado", value=f"{'✅ Aprovada' if approved else '❌ Recusada'} por {interaction.user.mention}", inline=False)
            try:
                await interaction.message.edit(embed=embed, view=None)
            except discord.HTTPException:
                log.exception("Falha ao atualizar solicitação #%s", self.request_id)


class AquiJas(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.message_content = True
        super().__init__(command_prefix="#", intents=intents, help_command=None, case_insensitive=True)

    @property
    def display_name(self) -> str:
        return self.user.name if self.user else "Bot"

    async def setup_hook(self) -> None:
        init_db()
        synced = await self.tree.sync()
        log.info("Sincronizados %d comandos globais: %s", len(synced), ", ".join(c.name for c in synced))
        with db() as conn:
            pending = conn.execute("SELECT id FROM partnership_requests WHERE status='pending'").fetchall()
        for row in pending:
            self.add_view(DecisionView(int(row["id"])))

    async def on_ready(self) -> None:
        if self.user is None:
            return
        await self.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="/ajuda • seu servidor"))
        log.info("Online como %s (%s)", self.user, self.user.id)
        log.info("Conectado a %d servidor(es)", len(self.guilds))
        log.info("Message Content Intent: %s", self.intents.message_content)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if not isinstance(error, commands.CommandNotFound):
            log.exception("Erro no comando prefixado #%s", ctx.invoked_with, exc_info=error)


bot = AquiJas()


@bot.command(name="parceria")
async def prefix_parceria(ctx: commands.Context) -> None:
    if ctx.guild is None or not can_manage(ctx.guild, ctx.author):
        return
    set_channel(ctx.guild.id, "partnership_channel_id", ctx.channel.id)
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    await ctx.send("✅ Este canal foi definido como **canal de parcerias**.", delete_after=5)
    log.info("Canal de parceria definido: guild=%s channel=%s", ctx.guild.id, ctx.channel.id)


@bot.command(name="perguntar")
async def prefix_perguntar(ctx: commands.Context) -> None:
    if ctx.guild is None or not can_manage(ctx.guild, ctx.author):
        return
    set_channel(ctx.guild.id, "staff_channel_id", ctx.channel.id)
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    await ctx.send("✅ Este canal foi definido como **canal da staff**.", delete_after=5)
    log.info("Canal staff definido: guild=%s channel=%s", ctx.guild.id, ctx.channel.id)


@bot.tree.command(name="ping", description="Verifica se o bot está online.")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(f"🏓 **{bot.display_name}** está online.\n⚡ `{round(bot.latency * 1000)} ms`")


@bot.tree.command(name="sobre", description="Mostra informações sobre o bot.")
async def sobre(interaction: discord.Interaction) -> None:
    embed = discord.Embed(title=f"✨ {bot.display_name}", description="Bot Discord leve e modular.", color=discord.Color.blurple())
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="🏠 Servidores", value=f"`{len(bot.guilds)}`", inline=True)
    embed.add_field(name="📦 discord.py", value=f"`{discord.__version__}`", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="servidor", description="Mostra informações básicas deste servidor.")
async def servidor(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
        return
    guild = interaction.guild
    embed = discord.Embed(title=f"🏠 {guild.name}", color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👥 Membros", value=f"`{guild.member_count or 'indisponível'}`", inline=True)
    embed.add_field(name="💬 Canais", value=f"`{len(guild.channels)}`", inline=True)
    embed.add_field(name="🗂️ Categorias", value=f"`{len(guild.categories)}`", inline=True)
    embed.add_field(name="🎭 Cargos", value=f"`{max(0, len(guild.roles) - 1)}`", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ajuda", description="Mostra os comandos disponíveis.")
async def ajuda(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(f"✨ **{bot.display_name}**\n\n`/ping` — verifica o bot\n`/sobre` — informações do bot\n`/servidor` — informações do servidor\n`/parceria` — solicita uma parceria\n\n**Configuração:** `#parceria` e `#perguntar`")


@bot.tree.command(name="parceria", description="Envia uma solicitação de parceria.")
@app_commands.describe(descricao="Descrição do seu servidor/projeto.", link="Convite permanente do Discord, sem expiração.")
async def slash_parceria(interaction: discord.Interaction, descricao: app_commands.Range[str, 10, 1000], link: str) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    if settings is None or not settings["partnership_channel_id"] or not settings["staff_channel_id"]:
        await interaction.response.send_message("❌ O sistema de parceria ainda não foi configurado.", ephemeral=True)
        return
    if has_pending(interaction.guild.id, interaction.user.id):
        await interaction.response.send_message("❌ Você já possui uma solicitação aguardando análise.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    valid, result = await validate_invite(link)
    if not valid:
        await interaction.edit_original_response(content=f"❌ {result}")
        return
    staff_channel = bot.get_channel(int(settings["staff_channel_id"]))
    if staff_channel is None:
        try:
            staff_channel = await bot.fetch_channel(int(settings["staff_channel_id"]))
        except discord.HTTPException:
            staff_channel = None
    if not isinstance(staff_channel, discord.TextChannel):
        await interaction.edit_original_response(content="❌ O canal da staff configurado não está disponível.")
        return
    request_id = create_request(interaction.guild.id, interaction.user.id, descricao.strip(), result)
    embed = discord.Embed(title="📨 Solicitação de parceria", description=descricao.strip(), color=discord.Color.orange(), timestamp=datetime.now(timezone.utc))
    embed.add_field(name="👤 Solicitante", value=interaction.user.mention, inline=True)
    embed.add_field(name="🆔 Solicitação", value=f"`#{request_id}`", inline=True)
    embed.add_field(name="🔗 Convite", value=f"[Abrir convite]({result})", inline=False)
    embed.set_footer(text="A staff deve aprovar antes da publicação.")
    try:
        await staff_channel.send(embed=embed, view=DecisionView(request_id))
    except discord.HTTPException:
        decide_request(request_id, "rejected")
        await interaction.edit_original_response(content="❌ Não consegui enviar a solicitação para a staff.")
        return
    await interaction.edit_original_response(content="✅ Solicitação enviada para a staff. Aguarde a análise.")


async def main() -> None:
    init_db()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
