from __future__ import annotations

import re
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from storage import Database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord-bot")

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN não foi encontrado. Adicione-o nos Secrets do host."
    )

MAX_DESCRIPTION_LENGTH = 1000
MAX_LINK_LENGTH = 2000
TRAP_ROLE_NAME = "Suspeito"
TRAP_TOPIC_MARKER = "[ARMADILHA] Acesso restrito ao cargo Suspeito."
SPAM_WINDOW_SECONDS = 8
SPAM_MESSAGE_LIMIT = 6
REPEAT_WINDOW_SECONDS = 30
REPEAT_MESSAGE_LIMIT = 3
INVITE_WINDOW_SECONDS = 60
INVITE_MESSAGE_LIMIT = 3
DISCORD_INVITE_PATTERN = re.compile(
    r"(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)


def discord_invite_code(link: str) -> str | None:
    parsed = urlparse(link)
    if parsed.scheme not in {"http", "https"}:
        return None

    hostname = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if hostname in {"discord.gg", "discord.me", "discord.li"}:
        return path_parts[0] if path_parts else None
    if hostname in {"discord.com", "www.discord.com", "discordapp.com", "www.discordapp.com"}:
        if len(path_parts) >= 2 and path_parts[0].lower() == "invite":
            return path_parts[1]
    return None


def is_valid_link(link: str) -> bool:
    return discord_invite_code(link) is not None


async def fetch_invite_preview(
    bot: PartnershipBot,
    link: str,
) -> tuple[str, str | None] | None:
    try:
        invite = await bot.fetch_invite(
            link,
            with_counts=False,
            with_expiration=True,
        )
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None

    if invite.expires_at is not None or invite.max_age not in {None, 0}:
        return None

    if invite.guild is None:
        return None

    icon_url = invite.guild.icon.url if invite.guild.icon else None
    return invite.guild.name, icon_url


def status_label(status: str) -> str:
    return {
        "pending": "Pendente de aprovação",
        "publishing": "Publicando",
        "approved": "Aprovada",
        "rejected": "Recusada",
        "failed": "Falha ao enviar para a staff",
    }.get(status, status.title())


def partnership_embed(request: dict[str, Any]) -> discord.Embed:
    status = request["status"]
    color = {
        "pending": discord.Color.gold(),
        "publishing": discord.Color.blurple(),
        "approved": discord.Color.green(),
        "rejected": discord.Color.red(),
    }.get(status, discord.Color.blurple())

    embed = discord.Embed(
        title="Solicitação de parceria",
        description=request["description"],
        color=color,
    )
    embed.add_field(
        name="Solicitante",
        value=f"<@{request['requester_id']}>",
        inline=True,
    )
    embed.add_field(
        name="Status",
        value=status_label(status),
        inline=True,
    )
    embed.add_field(
        name="Link",
        value=f"[Abrir link]({request['link']})",
        inline=False,
    )
    if request.get("publication_channel_id"):
        embed.add_field(
            name="Canal de publicação",
            value=f"<#{request['publication_channel_id']}>",
            inline=False,
        )
    embed.set_footer(text=f"Solicitação #{request['id']}")
    return embed


def published_partnership_embed(
    request: dict[str, Any],
    server_name: str | None,
    icon_url: str | None,
) -> discord.Embed:
    embed = discord.Embed(
        title=server_name,
        description=request["description"],
    )
    if icon_url:
        embed.set_thumbnail(url=icon_url)
    return embed


def published_partnership_view(link: str) -> discord.ui.View:
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="Entrar no servidor",
            style=discord.ButtonStyle.link,
            url=link,
        )
    )
    return view


class SuspicionTracker:
    def __init__(self) -> None:
        self._message_times: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._recent_messages: dict[
            tuple[int, int], deque[tuple[float, str]]
        ] = defaultdict(deque)
        self._recent_invites: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    def record(
        self,
        guild_id: int,
        user_id: int,
        content: str,
    ) -> str | None:
        now = time.monotonic()
        key = (guild_id, user_id)
        message_times = self._message_times[key]
        recent_messages = self._recent_messages[key]
        recent_invites = self._recent_invites[key]

        while message_times and now - message_times[0] > SPAM_WINDOW_SECONDS:
            message_times.popleft()
        while recent_messages and now - recent_messages[0][0] > REPEAT_WINDOW_SECONDS:
            recent_messages.popleft()
        while recent_invites and now - recent_invites[0] > INVITE_WINDOW_SECONDS:
            recent_invites.popleft()

        message_times.append(now)
        normalized_content = " ".join(content.lower().split())
        if normalized_content:
            recent_messages.append((now, normalized_content))
        if DISCORD_INVITE_PATTERN.search(content):
            recent_invites.append(now)

        if len(message_times) >= SPAM_MESSAGE_LIMIT:
            return f"{len(message_times)} mensagens em {SPAM_WINDOW_SECONDS}s"

        if normalized_content:
            repeated_count = sum(
                message == normalized_content for _, message in recent_messages
            )
            if repeated_count >= REPEAT_MESSAGE_LIMIT:
                return f"mensagem repetida {repeated_count} vezes"

        if len(recent_invites) >= INVITE_MESSAGE_LIMIT:
            return f"{len(recent_invites)} convites em {INVITE_WINDOW_SECONDS}s"

        if (
            ("@everyone" in content or "@here" in content)
            and len(message_times) >= 3
        ):
            return "spam com menções em massa"

        return None


class StaffView(discord.ui.View):
    def __init__(self, bot: PartnershipBot, request_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.request_id = request_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Essa ação só pode ser usada pela staff dentro do servidor.",
                ephemeral=True,
            )
            return False

        permissions = interaction.user.guild_permissions
        if not (permissions.administrator or permissions.manage_guild):
            await interaction.response.send_message(
                "Apenas a staff com permissão de gerenciar o servidor pode revisar parcerias.",
                ephemeral=True,
            )
            return False

        return True

    def disable_components(self) -> None:
        for child in self.children:
            child.disabled = True


class ApprovalView(StaffView):
    @discord.ui.button(
        label="Permitir parceria",
        style=discord.ButtonStyle.success,
        custom_id="partnership:approve",
    )
    async def approve(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[ApprovalView],
    ) -> None:
        request = self.bot.database.get_request(self.request_id)
        if not request or request["status"] != "pending":
            await interaction.response.send_message(
                "Essa solicitação já foi revisada ou está sendo publicada.",
                ephemeral=True,
            )
            return

        if not self.bot.database.set_awaiting_channel(self.request_id, True):
            await interaction.response.send_message(
                "Essa solicitação já está sendo revisada por outra pessoa.",
                ephemeral=True,
            )
            return

        default_channel_id = self.bot.database.get_publication_channel(
            interaction.guild.id if interaction.guild else 0
        )
        default_text = (
            f"O canal padrão atual é <#{default_channel_id}>. "
            "Escolha um canal abaixo para publicar esta parceria."
            if default_channel_id
            else "Escolha o canal onde a embed desta parceria será publicada."
        )
        await interaction.response.edit_message(
            content=default_text,
            embed=partnership_embed(request),
            view=PublicationChannelView(self.bot, self.request_id),
        )

    @discord.ui.button(
        label="Recusar parceria",
        style=discord.ButtonStyle.danger,
        custom_id="partnership:reject",
    )
    async def reject(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[ApprovalView],
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            return

        reviewed = self.bot.database.review_request(
            self.request_id,
            "rejected",
            interaction.user.id,
        )
        request = self.bot.database.get_request(self.request_id)

        if not reviewed or not request:
            await interaction.response.send_message(
                "Essa solicitação já foi revisada por outra pessoa.",
                ephemeral=True,
            )
            return

        self.disable_components()
        await interaction.response.edit_message(
            content="Solicitação recusada pela staff.",
            embed=partnership_embed(request),
            view=self,
        )


class PublicationChannelView(StaffView):
    def __init__(self, bot: PartnershipBot, request_id: int) -> None:
        super().__init__(bot, request_id)
        request = bot.database.get_request(request_id)
        default_channel_id = (
            bot.database.get_publication_channel(int(request["guild_id"]))
            if request
            else None
        )
        for child in self.children:
            if (
                isinstance(child, discord.ui.Button)
                and child.custom_id == "partnership:use-default"
            ):
                child.disabled = default_channel_id is None

    async def _publish_to_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.abc.GuildChannel,
    ) -> None:
        if not interaction.guild:
            return

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Selecione um canal de texto válido.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me
        if bot_member is not None:
            permissions = channel.permissions_for(bot_member)
            if not (
                permissions.view_channel
                and permissions.send_messages
                and permissions.embed_links
            ):
                await interaction.response.send_message(
                    "Eu preciso de **Ver canal**, **Enviar mensagens** e **Inserir links** no canal escolhido.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer()
        request = self.bot.database.get_request(self.request_id)
        if not request or request["status"] != "pending":
            await interaction.followup.send(
                "Essa solicitação já foi revisada ou está sendo publicada.",
                ephemeral=True,
            )
            return

        invite_preview = await fetch_invite_preview(self.bot, request["link"])
        if invite_preview is None:
            await interaction.followup.send(
                "O convite do Discord está inválido, expirado ou não é permanente. A solicitação continua pendente.",
                ephemeral=True,
            )
            return

        if not self.bot.database.start_publication(
            self.request_id,
            interaction.user.id,
            channel.id,
        ):
            await interaction.followup.send(
                "Essa solicitação já está sendo revisada por outra pessoa.",
                ephemeral=True,
            )
            return

        server_name, icon_url = invite_preview
        publishing_request = dict(request)
        publishing_request["status"] = "approved"
        publishing_request["publication_channel_id"] = str(channel.id)

        try:
            published_message = await channel.send(
                embed=published_partnership_embed(
                    publishing_request,
                    server_name,
                    icon_url,
                ),
                view=published_partnership_view(request["link"]),
            )
        except (discord.Forbidden, discord.HTTPException):
            self.bot.database.reset_publication(self.request_id)
            await interaction.followup.send(
                "Não consegui publicar a embed nesse canal. A solicitação voltou para pendente; confira as permissões e tente novamente.",
                ephemeral=True,
            )
            return

        self.bot.database.complete_publication(
            self.request_id,
            published_message.id,
        )
        self.bot.database.set_publication_channel(
            interaction.guild.id,
            channel.id,
        )

        try:
            if interaction.message:
                await interaction.message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.info(
                "Não foi possível apagar a mensagem privada da solicitação #%s.",
                self.request_id,
            )

        await interaction.followup.send(
            f"Parceria aprovada e publicada em {channel.mention}. Esse canal agora é o padrão para as próximas aprovações.",
            ephemeral=True,
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Selecione o canal para publicar a parceria",
        min_values=1,
        max_values=1,
        custom_id="partnership:publication-channel",
    )
    async def choose_channel(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect[PublicationChannelView],
    ) -> None:
        if not interaction.guild:
            return

        selected_channel = select.values[0]
        channel = selected_channel.resolve()
        if channel is None:
            try:
                channel = await selected_channel.fetch()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None

        if channel is None:
            await interaction.response.send_message(
                "Não consegui carregar o canal selecionado. Tente novamente.",
                ephemeral=True,
            )
            return

        await self._publish_to_channel(interaction, channel)

    @discord.ui.button(
        label="Usar canal padrão",
        style=discord.ButtonStyle.primary,
        custom_id="partnership:use-default",
    )
    async def use_default(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[PublicationChannelView],
    ) -> None:
        if not interaction.guild:
            return

        default_channel_id = self.bot.database.get_publication_channel(
            interaction.guild.id
        )
        if default_channel_id is None:
            await interaction.response.send_message(
                "Ainda não existe um canal padrão. Use o seletor para escolher um.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(default_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(default_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "O canal padrão não está disponível. Escolha outro canal no seletor.",
                ephemeral=True,
            )
            return

        await self._publish_to_channel(interaction, channel)

    @discord.ui.button(
        label="Voltar",
        style=discord.ButtonStyle.secondary,
        custom_id="partnership:publication-back",
    )
    async def back(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[PublicationChannelView],
    ) -> None:
        if not self.bot.database.set_awaiting_channel(self.request_id, False):
            await interaction.response.send_message(
                "Essa solicitação não está mais pendente.",
                ephemeral=True,
            )
            return

        request = self.bot.database.get_request(self.request_id)
        if not request:
            await interaction.response.send_message(
                "Não encontrei essa solicitação.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            content="Nova solicitação de parceria aguardando decisão da staff.",
            embed=partnership_embed(request),
            view=ApprovalView(self.bot, self.request_id),
        )


class PartnershipBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned_or("&", "#"), intents=intents)
        self.database = Database()
        self.suspicion_tracker = SuspicionTracker()

    async def setup_hook(self) -> None:
        self.database.initialize()
        synced_commands = await self.tree.sync()
        logger.info("Comandos slash sincronizados: %s", len(synced_commands))

        for request in self.database.list_pending_requests():
            view = (
                PublicationChannelView(self, int(request["id"]))
                if request["awaiting_channel"]
                else ApprovalView(self, int(request["id"]))
            )
            self.add_view(view, message_id=int(request["approval_message_id"]))

    async def on_ready(self) -> None:
        if self.user:
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="/parceria | /ajuda",
                ),
                status=discord.Status.online,
            )
            logger.info("Bot conectado como %s.", self.user)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.guild and isinstance(message.author, discord.Member):
            reason = self.suspicion_tracker.record(
                message.guild.id,
                message.author.id,
                message.content,
            )
            if reason:
                await self.mark_suspicious(message.author, reason)

        await self.process_commands(message)

    async def mark_suspicious(
        self,
        member: discord.Member,
        reason: str,
    ) -> None:
        trap_config = self.database.get_trap_config(member.guild.id)
        if trap_config is None:
            return

        role = member.guild.get_role(trap_config["role_id"])
        if role is None:
            logger.warning(
                "O cargo Suspeito não foi encontrado no servidor %s.",
                member.guild.id,
            )
            return
        if role in member.roles:
            return

        bot_member = member.guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_roles:
            logger.warning(
                "Não consigo atribuir o cargo Suspeito no servidor %s: falta a permissão Gerenciar cargos.",
                member.guild.id,
            )
            return
        if role >= bot_member.top_role:
            logger.warning(
                "Não consigo atribuir o cargo Suspeito no servidor %s: o cargo está acima do meu maior cargo.",
                member.guild.id,
            )
            return

        try:
            await member.add_roles(
                role,
                reason=f"Detecção automática de comportamento suspeito: {reason}",
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception(
                "Não foi possível atribuir o cargo Suspeito a %s no servidor %s.",
                member.id,
                member.guild.id,
            )
            return

        logger.info(
            "Cargo Suspeito atribuído a %s no servidor %s: %s.",
            member,
            member.guild.id,
            reason,
        )


bot = PartnershipBot()


@bot.tree.command(name="ping", description="Verifica se o bot está online.")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        f"🏓 **{bot.user.name if bot.user else 'Bot'}** está online.\n⚡ `{round(bot.latency * 1000)} ms`"
    )


@bot.tree.command(name="sobre", description="Mostra informações sobre o bot.")
async def sobre(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title=f"✨ {bot.user.name if bot.user else 'Bot'}",
        description="Bot Discord leve e modular.",
        color=discord.Color.blurple(),
    )
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
    embed.add_field(name="🎭 Cargos", value=f"`{max(0, len(guild.roles) - 1)}`", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="configurar", description="Configura o canal privado da staff.")
@app_commands.describe(canal="Canal privado onde a staff receberá as solicitações.")
@app_commands.default_permissions(manage_guild=True)
async def configurar(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
        return
    permissions = interaction.user.guild_permissions
    if interaction.user.id != interaction.guild.owner_id and not (permissions.administrator or permissions.manage_guild):
        await interaction.response.send_message("❌ Você precisa ser dono do servidor, Administrador ou ter **Gerenciar Servidor**.", ephemeral=True)
        return
    everyone = canal.overwrites_for(interaction.guild.default_role)
    if everyone.view_channel is not False:
        await interaction.response.send_message("❌ O canal precisa ser **privado**: negue **Ver canal** para @everyone.", ephemeral=True)
        return
    bot.database.set_approval_channel(interaction.guild.id, canal.id)
    await interaction.response.send_message(f"✅ Canal da staff configurado para {canal.mention}.", ephemeral=True)


@bot.command(name="parceria")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def prefix_publication_channel(context: commands.Context[PartnershipBot]) -> None:
    if not context.guild:
        return
    channel = context.channel
    if not isinstance(channel, discord.TextChannel):
        return
    bot_member = context.guild.me
    if bot_member is not None:
        permissions = channel.permissions_for(bot_member)
        if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            await context.reply("Eu preciso de **Ver canal**, **Enviar mensagens** e **Inserir links** nesse canal.")
            return
    bot.database.set_publication_channel(context.guild.id, channel.id)
    try:
        await context.message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass
    await context.send("✅ Este canal foi definido como **canal de publicação de parcerias**.", delete_after=5)


@bot.tree.command(
    name="parceria",
    description="Envia uma solicitação de parceria para a staff.",
)
@app_commands.describe(
    descricao="Descrição da parceria que você está propondo.",
    link="Link permanente de convite do servidor no Discord.",
)
async def partnership(
    interaction: discord.Interaction,
    descricao: str,
    link: str,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message(
            "Esse comando só pode ser usado dentro de um servidor.",
            ephemeral=True,
        )
        return

    description = descricao.strip()
    normalized_link = link.strip()

    if not description:
        await interaction.response.send_message(
            "A descrição da parceria não pode ficar vazia.",
            ephemeral=True,
        )
        return

    if len(description) > MAX_DESCRIPTION_LENGTH:
        await interaction.response.send_message(
            f"A descrição deve ter no máximo {MAX_DESCRIPTION_LENGTH} caracteres.",
            ephemeral=True,
        )
        return

    if len(normalized_link) > MAX_LINK_LENGTH or not is_valid_link(normalized_link):
        await interaction.response.send_message(
            "Envie um convite permanente válido do Discord, como discord.gg/servidor.",
            ephemeral=True,
        )
        return

    approval_channel_id = bot.database.get_approval_channel(interaction.guild.id)
    if approval_channel_id is None:
        await interaction.response.send_message(
            "A staff ainda não configurou o canal privado. Um administrador deve usar `&canal-parceria #canal-privado`.",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(approval_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(approval_channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            channel = None

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "O canal privado configurado não está disponível. A staff deve escolher outro canal.",
            ephemeral=True,
        )
        return

    if channel.permissions_for(interaction.guild.default_role).view_channel:
        await interaction.response.send_message(
            "O canal de aprovação precisa ser privado: o cargo @everyone não pode conseguir visualizá-lo.",
            ephemeral=True,
        )
        return

    request_id = bot.database.create_request(
        interaction.guild.id,
        interaction.user.id,
        description,
        normalized_link,
    )
    request = bot.database.get_request(request_id)
    if request is None:
        await interaction.response.send_message(
            "Não foi possível criar a solicitação. Tente novamente.",
            ephemeral=True,
        )
        return

    view = ApprovalView(bot, request_id)
    try:
        message = await channel.send(
            content="Nova solicitação de parceria aguardando decisão da staff.",
            embed=partnership_embed(request),
            view=view,
        )
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Falha ao enviar a solicitação #%s.", request_id)
        await interaction.response.send_message(
            "Não consegui enviar a solicitação ao canal privado da staff. Verifique as permissões do bot nesse canal.",
            ephemeral=True,
        )
        return

    bot.database.set_message_id(request_id, message.id)
    await interaction.response.send_message(
        "Sua solicitação foi enviada para a staff e ficará aguardando aprovação.",
        ephemeral=True,
    )


@bot.tree.command(
    name="ajuda",
    description="Mostra os comandos disponíveis do bot.",
)
async def help_command(interaction: discord.Interaction) -> None:
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
    embed.add_field(
        name="/configurar #canal-privado",
        value="Configura o canal privado onde a staff receberá as solicitações.",
        inline=False,
    )
    embed.add_field(
        name="&canal-parceria #canal-privado",
        value="Configura o canal privado onde a staff receberá as solicitações. Apenas administrador ou Gerenciar servidor.",
        inline=False,
    )
    embed.add_field(
        name="#parceria",
        value="Define o canal atual como canal padrão de publicação das parcerias aprovadas.",
        inline=False,
    )
    embed.add_field(
        name="&armadilha",
        value="Usado dentro do canal que será a armadilha. Também aceita `&armadilha #canal`. Cria o cargo `Suspeito`, restringe o canal e marca automaticamente quem apresentar sinais de spam.",
        inline=False,
    )
    embed.add_field(
        name="&desarmadilha",
        value="Desativa a armadilha configurada e torna o canal visível novamente.",
        inline=False,
    )
    embed.add_field(name="/ping", value="Verifica se o bot está online.", inline=False)
    embed.add_field(name="/sobre", value="Mostra informações do bot.", inline=False)
    embed.add_field(name="/servidor", value="Mostra informações básicas do servidor.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.command(name="armadilha")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def configure_trap(
    context: commands.Context[PartnershipBot],
    canal: discord.TextChannel = None,
) -> None:
    if not context.guild:
        return

    trap_channel = canal or context.channel
    if not isinstance(trap_channel, discord.TextChannel):
        await context.reply("Use o comando dentro de um canal de texto.")
        return

    bot_member = context.guild.me
    if bot_member is None:
        await context.reply("Não consegui verificar minhas permissões neste servidor.")
        return
    if not bot_member.guild_permissions.manage_channels:
        await context.reply("Eu preciso da permissão **Gerenciar canais** para configurar a armadilha.")
        return
    if not bot_member.guild_permissions.manage_roles:
        await context.reply("Eu preciso da permissão **Gerenciar cargos** para atribuir o cargo Suspeito.")
        return

    role = discord.utils.get(context.guild.roles, name=TRAP_ROLE_NAME)
    if role is not None and role.managed:
        await context.reply(
            f"O cargo `{TRAP_ROLE_NAME}` existente é gerenciado por uma integração e não pode ser usado."
        )
        return

    try:
        if role is None:
            role = await context.guild.create_role(
                name=TRAP_ROLE_NAME,
                mentionable=False,
                reason="Cargo usado pela armadilha anti-spam.",
            )
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Não foi possível criar o cargo Suspeito.")
        await context.reply("Não consegui criar o cargo `Suspeito`. Verifique a permissão **Gerenciar cargos**.")
        return

    if role >= bot_member.top_role:
        await context.reply("Coloque o cargo `Suspeito` abaixo do meu maior cargo na lista de cargos do servidor.")
        return

    try:
        await trap_channel.set_permissions(
            context.guild.default_role,
            view_channel=False,
            send_messages=False,
            reason="Canal configurado como armadilha.",
        )
        await trap_channel.set_permissions(
            role,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            reason="Acesso do cargo Suspeito ao canal armadilha.",
        )
        await trap_channel.set_permissions(
            bot_member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            embed_links=True,
            reason="Acesso do bot ao canal armadilha.",
        )

        current_topic = trap_channel.topic or ""
        if TRAP_TOPIC_MARKER not in current_topic:
            topic = f"{TRAP_TOPIC_MARKER}\n{current_topic}".strip()
            await trap_channel.edit(topic=topic[:1024])
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Não foi possível configurar o canal armadilha.")
        await context.reply("Não consegui configurar esse canal. Verifique se tenho **Gerenciar canais** e se meu maior cargo está acima do cargo `Suspeito`.")
        return

    bot.database.set_trap_config(context.guild.id, trap_channel.id, role.id)
    await context.reply(
        f"Armadilha configurada em {trap_channel.mention}. Quem atingir os critérios de suspeita receberá {role.mention} e poderá ver e enviar mensagens nesse canal."
    )


@bot.command(name="desarmadilha")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def disable_trap(
    context: commands.Context[PartnershipBot],
    canal: discord.TextChannel = None,
) -> None:
    if not context.guild:
        return

    trap_config = bot.database.get_trap_config(context.guild.id)
    if trap_config is None:
        await context.reply("Não há nenhuma armadilha configurada neste servidor.")
        return

    trap_channel = canal or context.guild.get_channel(trap_config["channel_id"])
    if not isinstance(trap_channel, discord.TextChannel):
        await context.reply("O canal da armadilha não está disponível. Remova a configuração manualmente ou escolha o canal correto.")
        return

    bot_member = context.guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_channels:
        await context.reply("Eu preciso da permissão **Gerenciar canais** para desativar a armadilha.")
        return

    role = context.guild.get_role(trap_config["role_id"])
    try:
        await trap_channel.set_permissions(
            context.guild.default_role,
            view_channel=True,
            send_messages=True,
            reason="Canal armadilha desativado.",
        )
        if role is not None:
            await trap_channel.set_permissions(
                role,
                overwrite=None,
                reason="Acesso específico da armadilha removido.",
            )

        current_topic = trap_channel.topic or ""
        topic = current_topic.replace(TRAP_TOPIC_MARKER, "").strip()
        await trap_channel.edit(topic=topic or None)
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Não foi possível desativar a armadilha.")
        await context.reply("Não consegui restaurar as permissões desse canal. Verifique **Gerenciar canais**.")
        return

    bot.database.clear_trap_config(context.guild.id)
    await context.reply(f"Armadilha desativada em {trap_channel.mention}.")


@bot.command(name="canal-parceria", aliases=["parceria-canal"])
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def set_partnership_channel(
    context: commands.Context[PartnershipBot],
    channel: discord.TextChannel,
) -> None:
    if not context.guild:
        return

    if context.guild.default_role in channel.overwrites:
        everyone_permissions = channel.overwrites_for(context.guild.default_role)
        if everyone_permissions.view_channel is not False:
            await context.reply("O canal precisa ser privado: negue **Ver canal** para o cargo @everyone.")
            return
    elif channel.permissions_for(context.guild.default_role).view_channel:
        await context.reply("O canal precisa ser privado: negue **Ver canal** para o cargo @everyone.")
        return

    bot_member = context.guild.me
    if bot_member is not None:
        bot_permissions = channel.permissions_for(bot_member)
        if not (
            bot_permissions.view_channel
            and bot_permissions.send_messages
            and bot_permissions.embed_links
        ):
            await context.reply("Eu preciso de **Ver canal**, **Enviar mensagens** e **Inserir links** nesse canal.")
            return

    bot.database.set_approval_channel(context.guild.id, channel.id)
    await context.reply(
        f"Canal privado de aprovação configurado: {channel.mention}. Essa configuração ficará salva mesmo depois que o bot reiniciar."
    )


@bot.event
async def on_command_error(
    context: commands.Context[PartnershipBot],
    error: commands.CommandError,
) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await context.reply("Apenas a staff com permissão de gerenciar o servidor pode configurar esse canal.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        command_name = context.command.name if context.command else ""
        if command_name == "canal-parceria":
            message = "Use assim: `&canal-parceria #canal-privado`."
        else:
            message = "Esse comando não exige argumentos. Para indicar um canal, use `#canal`."
        await context.reply(message)
        return
    if isinstance(error, commands.BadArgument):
        command_name = context.command.name if context.command else ""
        if command_name == "canal-parceria":
            example = "&canal-parceria #parcerias-staff"
        else:
            example = "&armadilha #canal"
        await context.reply(f"Não encontrei esse canal. Use, por exemplo: `{example}`.")
        return

    logger.exception("Erro no comando com prefixo.", exc_info=error)


bot.run(TOKEN)
