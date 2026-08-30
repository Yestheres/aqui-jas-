from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não está configurado.")

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "aqui_jas.sqlite3"
GITHUB_URL = "https://github.com/Yestheres/aqui-jas-"
INVITE_RE = re.compile(
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


def get_settings(guild_id: int) -> sqlite3.Row | None:
    with db_connect() as db:
        return db.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()


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


def has_pending_request(guild_id: int, user_id: int) -> bool:
    with db_connect() as db:
        return (
            db.execute(
                """
                SELECT 1 FROM partnership_requests
                WHERE guild_id = ? AND user_id = ? AND status = 'pending'
                LIMIT 1
                """,
                (guild_id, user_id),
            ).fetchone()
            is not None
        )


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


def decide_request(request_id: int, status: str) -> sqlite3.Row | None:
    if status not in {"approved", "rejected"}:
        raise ValueError("invalid status")
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
    match = INVITE_RE.match(link.strip())
    if not match:
        return False, "Use um convite do Discord, como `https://discord.gg/exemplo`."

    normalized = f"https://discord.gg/{match.group(1)}"
    try:
        invite = await bot.fetch_invite(normalized, with_counts=False)
    except discord.NotFound:
        return False, "Esse convite é inválido ou já expirou."
    except discord.HTTPException:
        return False, "Não consegui verificar esse convite agora. Tente novamente."

    max_age = getattr(invite, "max_age", None)
    if max_age is None:
        return False, "Não consegui confirmar se o convite é permanente. Gere um convite sem expiração."
    if max_age != 0:
        return False, "O convite precisa ser permanente, sem expiração."
    if getattr(invite, "temporary", False):
        return False, "Convites temporários não podem ser usados em parcerias."

    return True, normalized


class PartnershipDecisionView(discord.ui.View):
    """Persistent approval buttons attached to a partnership request."""

    def __init__(self, bot: "AquiJas", request_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.request_id = request_id

        approve = discord.ui.Button(
            label="Aceitar parceria",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"partnership:approve:{request_id}",
        )
        reject = discord.ui.Button(
            label="Recusar",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"partnership:reject:{request_id}",
        )
        approve.callback = self.approve_callback
        reject.callback = self.reject_callback
        self.add_item(approve)
        self.add_item(reject)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Essa ação só funciona dentro de um servidor.", ephemeral=True
            )
            return False
        member = interaction.user
        if not (
            member.id == interaction.guild.owner_id
            or member.guild_permissions.administrator
            or member.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "Você precisa ser dono do servidor ou ter **Gerenciar Servidor** para decidir parcerias.",
                ephemeral=True,
            )
            return False
        return True

    async def approve_callback(self, interaction: discord.Interaction) -> None:
        await self._finish(interaction, approved=True)

    async def reject_callback(self, interaction: discord.Interaction) -> None:
        await self._finish(interaction, approved=False)

    async def _finish(self, interaction: discord.Interaction, approved: bool) -> None:
        row = decide_request(self.request_id, "approved" if approved else "rejected")
        if row is None:
            await interaction.response.send_message(
                "Essa solicitação já foi decidida.", ephemeral=True
            )
            return

        if approved:
            settings = get_settings(int(row["guild_id"]))
            channel_id = settings["partnership_channel_id"] if settings else None
            destination: discord.abc.Messageable | None = None

            if channel_id:
                destination = self.bot.get_channel(int(channel_id))
                if destination is None:
                    try:
                        channel = await self.bot.fetch_channel(int(channel_id))
                        if isinstance(channel, discord.abc.Messageable):
                            destination = channel
                    except discord.HTTPException:
                        destination = None

            if destination is None:
                await interaction.response.send_message(
                    "Parceria aprovada, mas o canal de parceria não está disponível.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="🤝 Nova parceria",
                description=str(row["description"]),
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(
                name="🔗 Convite",
                value=f"[Entrar no servidor]({row['invite_url']})",
                inline=False,
            )
            embed.set_footer(text=f"Parceria • solicitação #{row['id']}")

            try:
                await destination.send(embed=embed)
            except discord.HTTPException:
                await interaction.response.send_message(
                    "A solicitação foi aprovada, mas não consegui publicar a parceria.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                "✅ Parceria aprovada e publicada.", ephemeral=True
            )

            try:
                user = self.bot.get_user(int(row["user_id"])) or await self.bot.fetch_user(
                    int(row["user_id"])
                )
                await user.send(
                    f"✅ Sua solicitação de parceria no servidor **{interaction.guild.name}** foi aprovada."
                )
            except discord.HTTPException:
                pass
        else:
            await interaction.response.send_message(
                "❌ Parceria recusada.", ephemeral=True
            )
            try:
                user = self.bot.get_user(int(row["user_id"])) or await self.bot.fetch_user(
                    int(row["user_id"])
                )
                await user.send(
                    f"❌ Sua solicitação de parceria no servidor **{interaction.guild.name}** foi recusada."
                )
            except discord.HTTPException:
                pass

        if interaction.message:
            current = (
                interaction.message.embeds[0].copy()
                if interaction.message.embeds
                else discord.Embed(title="Solicitação de parceria")
            )
            current.color = discord.Color.green() if approved else discord.Color.red()
            current.add_field(
                name="Resultado",
                value=(
                    f"✅ Aprovada por {interaction.user.mention}"
                    if approved
                    else f"❌ Recusada por {interaction.user.mention}"
                ),
                inline=False,
            )
            try:
                await interaction.message.edit(embed=current, view=None)
            except discord.HTTPException:
                log.exception("Falha ao atualizar solicitação #%s", self.request_id)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        log.exception("Erro no botão da solicitação #%s", self.request_id, exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Ocorreu um erro ao processar essa solicitação.", ephemeral=True
            )


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
            ", ".join(command.name for command in synced),
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
        log.info("Message Content Intent solicitado: %s", self.intents.message_content)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        content = message.content.strip().casefold()
        if content not in {"#parceria", "#perguntar"}:
            return

        log.info(
            "Comando de configuração recebido: %s | guild=%s | channel=%s | user=%s",
            content,
            message.guild.id,
            message.channel.id,
            message.author.id,
        )

        member = message.author
        allowed = (
            member.id == message.guild.owner_id
            or member.guild_permissions.administrator
            or member.guild_permissions.manage_guild
        )
        if not allowed:
            try:
                await message.reply(
                    "❌ Você precisa ser dono do servidor ou ter **Gerenciar Servidor** para usar este comando.",
                    delete_after=5,
                )
            except discord.HTTPException:
                pass
            return

        column = (
            "partnership_channel_id"
            if content == "#parceria"
            else "staff_channel_id"
        )
        label = "parcerias" if content == "#parceria" else "staff"

        set_channel(message.guild.id, column, message.channel.id)

        try:
            await message.delete()
        except discord.Forbidden:
            log.warning(
                "Sem permissão para apagar mensagem de configuração em channel=%s",
                message.channel.id,
            )
        except discord.HTTPException:
            log.exception("Erro ao apagar mensagem de configuração")

        try:
            confirmation = await message.channel.send(
                f"✅ Este canal foi definido como canal de **{label}**.",
                delete_after=5,
            )
        except discord.HTTPException:
            log.exception("Não consegui enviar confirmação da configuração")
            return

        log.info(
            "Configuração concluída: %s -> channel=%s (message=%s)",
            label,
            message.channel.id,
            confirmation.id,
        )


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
            "Esse comando só funciona dentro de um servidor.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"🏠 {guild.name}",
        description=f"Informações básicas do servidor • {bot.display_name}",
        color=discord.Color.blurple(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(
        name="👥 Membros",
        value=f"`{guild.member_count or 'indisponível'}`",
        inline=True,
    )
    embed.add_field(name="💬 Canais", value=f"`{len(guild.channels)}`", inline=True)
    embed.add_field(name="🗂️ Categorias", value=f"`{len(guild.categories)}`", inline=True)
    embed.add_field(name="🎭 Cargos", value=f"`{max(0, len(guild.roles) - 1)}`", inline=True)
    embed.add_field(name="🆔 ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(
        name="📅 Criado",
        value=f"<t:{int(guild.created_at.timestamp())}:D>",
        inline=True,
    )
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
            "Esse comando só pode ser usado em um servidor.", ephemeral=True
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
            result,
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
    embed.add_field(name="🆔 Solicitação", value=f"`#{request_id}`", inline=True)
    embed.add_field(
        name="🔗 Convite",
        value=f"[Abrir convite]({result})",
        inline=False,
    )
    embed.set_footer(text="A staff deve aprovar antes da publicação.")

    view = PartnershipDecisionView(bot, request_id)
    try:
        staff_message = await staff_channel.send(embed=embed, view=view)
        set_request_message(request_id, staff_message.id)
    except discord.HTTPException:
        decide_request(request_id, "rejected")
        await interaction.edit_original_response(
            content="❌ Não consegui enviar a solicitação para o canal da staff."
        )
        return

    await interaction.edit_original_response(
        content="✅ Solicitação enviada para a staff. Aguarde a análise."
    )


async def main() -> None:
    init_database()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
