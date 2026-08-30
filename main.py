from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não está configurado.")

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "aqui_jas.sqlite3"
GITHUB_URL = "https://github.com/Yestheres/aqui-jas-"
DISCORD_INVITE_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.gg)/([A-Za-z0-9-]+)(?:/)?$",
    re.IGNORECASE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("aqui_jas")


def db_connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    with db_connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                partnership_channel_id INTEGER,
                staff_channel_id INTEGER,
                updated_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS partnership_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                invite_url TEXT NOT NULL,
                staff_channel_id INTEGER NOT NULL,
                staff_message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                UNIQUE(guild_id, user_id, status)
            )
            """
        )
        db.commit()


def set_channel(guild_id: int, column: str, channel_id: int) -> None:
    if column not in {"partnership_channel_id", "staff_channel_id"}:
        raise ValueError("invalid settings column")
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as db:
        db.execute(
            f"""
            INSERT INTO guild_settings (guild_id, {column}, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                {column}=excluded.{column},
                updated_at=excluded.updated_at
            """,
            (guild_id, channel_id, now),
        )
        db.commit()


def get_settings(guild_id: int) -> sqlite3.Row | None:
    with db_connect() as db:
        return db.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()


def create_request(
    guild_id: int,
    user_id: int,
    description: str,
    invite_url: str,
    staff_channel_id: int,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as db:
        cursor = db.execute(
            """
            INSERT INTO partnership_requests
                (guild_id, user_id, description, invite_url, staff_channel_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, description, invite_url, staff_channel_id, now),
        )
        db.commit()
        return int(cursor.lastrowid)


def set_request_message(request_id: int, message_id: int) -> None:
    with db_connect() as db:
        db.execute(
            "UPDATE partnership_requests SET staff_message_id = ? WHERE id = ?",
            (message_id, request_id),
        )
        db.commit()


def get_pending_request(request_id: int) -> sqlite3.Row | None:
    with db_connect() as db:
        return db.execute(
            "SELECT * FROM partnership_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        ).fetchone()


def has_pending_request(guild_id: int, user_id: int) -> bool:
    with db_connect() as db:
        row = db.execute(
            """
            SELECT 1 FROM partnership_requests
            WHERE guild_id = ? AND user_id = ? AND status = 'pending'
            LIMIT 1
            """,
            (guild_id, user_id),
        ).fetchone()
        return row is not None


def finish_request(request_id: int, status: str) -> sqlite3.Row | None:
    if status not in {"approved", "rejected"}:
        raise ValueError("invalid request status")
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as db:
        row = db.execute(
            "SELECT * FROM partnership_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        ).fetchone()
        if row is None:
            return None
        db.execute(
            "UPDATE partnership_requests SET status = ?, decided_at = ? WHERE id = ?",
            (status, now, request_id),
        )
        db.commit()
        return row


async def validate_permanent_invite(bot: discord.Client, link: str) -> tuple[bool, str]:
    match = DISCORD_INVITE_RE.match(link.strip())
    if not match:
        return False, "Envie um convite do Discord, como `https://discord.gg/exemplo`."

    normalized = f"https://discord.gg/{match.group(1)}"
    try:
        try:
            invite = await bot.fetch_invite(
                normalized,
                with_counts=False,
                with_expiration=True,
            )
        except TypeError:
            invite = await bot.fetch_invite(normalized, with_counts=False)
    except discord.NotFound:
        return False, "Esse convite é inválido ou já expirou."
    except discord.HTTPException:
        return False, "Não consegui verificar esse convite agora. Tente novamente."

    max_age = getattr(invite, "max_age", None)
    if max_age is None:
        return False, "Não consegui confirmar que esse convite é permanente. Gere um convite sem expiração."
    if max_age != 0:
        return False, "O convite precisa ser permanente, sem expiração."
    if getattr(invite, "temporary", False):
        return False, "O convite temporário não pode ser usado para parceria."

    return True, normalized


class PartnershipDecisionView(discord.ui.View):
    def __init__(self, bot: "AquiJas", request_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.request_id = request_id
        self.add_item(
            discord.ui.Button(
                label="Aceitar parceria",
                style=discord.ButtonStyle.success,
                emoji="✅",
                custom_id=f"partnership:approve:{request_id}",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Recusar",
                style=discord.ButtonStyle.danger,
                emoji="❌",
                custom_id=f"partnership:reject:{request_id}",
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message("Essa ação só funciona dentro de um servidor.", ephemeral=True)
            return False
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Você precisa da permissão **Gerenciar Servidor** para decidir parcerias.",
                ephemeral=True,
            )
            return False
        return True

    async def _finish(self, interaction: discord.Interaction, approved: bool) -> None:
        status = "approved" if approved else "rejected"
        row = finish_request(self.request_id, status)
        if row is None:
            await interaction.response.send_message(
                "Essa solicitação já foi decidida.",
                ephemeral=True,
            )
            return

        if approved:
            channel = self.bot.get_channel(int(row["guild_id"] and 0))
            settings = get_settings(int(row["guild_id"]))
            partnership_channel_id = settings["partnership_channel_id"] if settings else None
            destination = None
            if partnership_channel_id:
                destination = self.bot.get_channel(int(partnership_channel_id))
                if destination is None:
                    try:
                        destination = await self.bot.fetch_channel(int(partnership_channel_id))
                    except discord.HTTPException:
                        destination = None

            if not isinstance(destination, discord.TextChannel):
                await interaction.response.send_message(
                    "Parceria aprovada, mas não consegui acessar o canal de parceria configurado.",
                    ephemeral=True,
                )
            else:
                embed = discord.Embed(
                    title="🤝 Nova parceria",
                    description=row["description"],
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="🔗 Convite", value=f"[Entrar no servidor]({row['invite_url']})", inline=False)
                embed.set_footer(text=f"Parceria enviada por ID {row['user_id']}")
                try:
                    await destination.send(embed=embed)
                    await interaction.response.send_message("✅ Parceria aprovada e publicada.", ephemeral=True)
                except discord.HTTPException:
                    await interaction.response.send_message(
                        "Parceria aprovada, mas não consegui publicar no canal configurado.",
                        ephemeral=True,
                    )
        else:
            await interaction.response.send_message("❌ Parceria recusada.", ephemeral=True)

        if interaction.message:
            current = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
            current.color = discord.Color.green() if approved else discord.Color.red()
            current.add_field(
                name="Resultado",
                value=f"{'✅ Aprovada' if approved else '❌ Recusada'} por {interaction.user.mention}",
                inline=False,
            )
            disabled_view = PartnershipDecisionView(self.bot, self.request_id)
            for child in disabled_view.children:
                child.disabled = True
            try:
                await interaction.message.edit(embed=current, view=disabled_view)
            except discord.HTTPException:
                log.exception("Failed to update partnership request message %s", self.request_id)

    @discord.ui.button(label="", style=discord.ButtonStyle.success, custom_id="unused")
    async def unused(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Botão inválido.", ephemeral=True)


class AquiJas(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    @property
    def display_name(self) -> str:
        return self.user.name if self.user else "Aqui Jas"

    async def setup_hook(self) -> None:
        init_database()
        self.tree.add_command(parceria)

        synced = await self.tree.sync()
        log.info(
            "Sincronizados %d comandos globais: %s",
            len(synced),
            ", ".join(c.name for c in synced),
        )

        with db_connect() as db:
            pending = db.execute(
                "SELECT id FROM partnership_requests WHERE status = 'pending'"
            ).fetchall()
        for row in pending:
            self.add_view(PartnershipDecisionView(self, int(row["id"])))

    async def on_ready(self) -> None:
        if self.user is None:
            return
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/ajuda • seu servidor",
            ),
        )
        log.info("Online como %s (%s)", self.user, self.user.id)
        log.info("Conectado a %d servidor(es)", len(self.guilds))

        # Remove old guild-only command registrations created by previous builds.
        for guild in self.guilds:
            try:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
            except discord.HTTPException:
                log.exception("Falha ao limpar comandos antigos da guild %s", guild.id)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        content = message.content.strip()
        if content not in {"#parceria", "#perguntar"}:
            return
        if not message.author.guild_permissions.manage_guild:
            return

        try:
            await message.delete()
        except discord.HTTPException:
            log.warning("Não consegui apagar a mensagem de configuração em #%s", message.channel)

        if content == "#parceria":
            set_channel(message.guild.id, "partnership_channel_id", message.channel.id)
            log.info("Canal de parceria definido: guild=%s channel=%s", message.guild.id, message.channel.id)
        else:
            set_channel(message.guild.id, "staff_channel_id", message.channel.id)
            log.info("Canal staff de aprovação definido: guild=%s channel=%s", message.guild.id, message.channel.id)


bot = AquiJas()


@bot.tree.command(name="ping", description="Verifica se o bot está online.")
async def ping(interaction: discord.Interaction) -> None:
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"O **{bot.display_name}** está online e respondendo.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="⚡ Latência", value=f"`{latency} ms`", inline=True)
    embed.add_field(name="🟢 Estado", value="`Online`", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="sobre", description="Mostra informações sobre o bot.")
async def sobre(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title=f"✨ {bot.display_name}",
        description="Um bot Discord leve, moderno e modular.",
        color=discord.Color.blurple(),
    )
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="🐍 Python", value=f"`{platform.python_version()}`", inline=True)
    embed.add_field(name="📦 discord.py", value=f"`{discord.__version__}`", inline=True)
    embed.add_field(name="🏠 Servidores", value=f"`{len(bot.guilds)}`", inline=True)
    embed.add_field(name="🤝 Parcerias", value="`/parceria`", inline=True)
    embed.add_field(name="🔧 Núcleo", value="Discord API + Slash Commands", inline=False)
    view = discord.ui.View(timeout=120)
    view.add_item(
        discord.ui.Button(
            label="Código no GitHub",
            style=discord.ButtonStyle.link,
            url=GITHUB_URL,
            emoji="💻",
        )
    )
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="servidor", description="Mostra informações básicas deste servidor.")
async def servidor(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "Esse comando só funciona dentro de um servidor.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=f"🏠 {guild.name}",
        description=f"Informações básicas do servidor • {bot.display_name}",
        color=discord.Color.blurple(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👥 Membros", value=f"`{guild.member_count or 'indisponível'}`", inline=True)
    embed.add_field(name="💬 Canais", value=f"`{len(guild.channels)}`", inline=True)
    embed.add_field(name="🗂️ Categorias", value=f"`{len(guild.categories)}`", inline=True)
    embed.add_field(name="🎭 Cargos", value=f"`{max(0, len(guild.roles) - 1)}`", inline=True)
    embed.add_field(name="🆔 ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="📅 Criado", value=f"<t:{int(guild.created_at.timestamp())}:D>", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ajuda", description="Mostra os comandos disponíveis.")
async def ajuda(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title=f"✨ {bot.display_name}",
        description="**Central de comandos**",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="⚡ Geral",
        value="`/ping` — verifica o bot\n`/sobre` — informações do bot",
        inline=False,
    )
    embed.add_field(
        name="🏠 Servidor",
        value="`/servidor` — informações do servidor",
        inline=False,
    )
    embed.add_field(
        name="🤝 Parcerias",
        value="`/parceria` — envia uma solicitação para análise da staff",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


@app_commands.command(
    name="parceria",
    description="Envia uma solicitação de parceria para a equipe avaliar.",
)
@app_commands.describe(
    descricao="Descrição do seu servidor/projeto.",
    link="Convite permanente do Discord (sem expiração).",
)
async def parceria(
    interaction: discord.Interaction,
    descricao: app_commands.Range[str, 10, 1000],
    link: str,
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Esse comando só pode ser usado em um servidor.",
            ephemeral=True,
        )
        return

    settings = get_settings(interaction.guild.id)
    if settings is None or not settings["partnership_channel_id"] or not settings["staff_channel_id"]:
        await interaction.response.send_message(
            "O sistema de parceria ainda não foi configurado pela staff.",
            ephemeral=True,
        )
        return

    if has_pending_request(interaction.guild.id, interaction.user.id):
        await interaction.response.send_message(
            "Você já possui uma solicitação de parceria aguardando análise.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    valid, result = await validate_permanent_invite(bot, link)
    if not valid:
        await interaction.edit_original_response(content=f"❌ {result}")
        return
    normalized_link = result

    staff_channel = bot.get_channel(int(settings["staff_channel_id"]))
    if staff_channel is None:
        try:
            staff_channel = await bot.fetch_channel(int(settings["staff_channel_id"]))
        except discord.HTTPException:
            staff_channel = None

    if not isinstance(staff_channel, discord.TextChannel):
        await interaction.edit_original_response(
            content="❌ O canal da staff configurado não está disponível."
        )
        return

    try:
        request_id = create_request(
            interaction.guild.id,
            interaction.user.id,
            descricao.strip(),
            normalized_link,
            staff_channel.id,
        )
    except sqlite3.IntegrityError:
        await interaction.edit_original_response(
            content="Você já possui uma solicitação de parceria aguardando análise."
        )
        return

    embed = discord.Embed(
        title="📨 Solicitação de parceria",
        description=descricao.strip(),
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="👤 Solicitante", value=interaction.user.mention, inline=True)
    embed.add_field(name="🆔 ID da solicitação", value=f"`{request_id}`", inline=True)
    embed.add_field(name="🔗 Convite", value=f"[Abrir convite]({normalized_link})", inline=False)
    embed.set_footer(text="Analise a solicitação antes de publicar a parceria.")

    view = PartnershipDecisionView(bot, request_id)
    try:
        staff_message = await staff_channel.send(embed=embed, view=view)
        set_request_message(request_id, staff_message.id)
        bot.add_view(view, message_id=staff_message.id)
    except discord.HTTPException:
        finish_request(request_id, "rejected")
        await interaction.edit_original_response(
            content="❌ Não consegui enviar a solicitação para o canal da staff."
        )
        return

    await interaction.edit_original_response(
        content="✅ Solicitação enviada para a equipe. Aguarde a análise da staff."
    )


async def main() -> None:
    init_database()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
