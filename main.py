from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from storage import Database

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord-bot")

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não foi encontrado. Configure a variável no VS Code ou no painel da hospedagem.")

MAX_DESCRIPTION_LENGTH = 8000
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

PARTNERSHIP_STATUS_LABELS = {
    "pending": "Pendente de aprovação",
    "publishing": "Publicando",
    "approved": "Aprovada",
    "rejected": "Recusada",
    "failed": "Falha ao enviar para a staff",
}

PARTNERSHIP_STATUS_COLORS = {
    "pending": discord.Color.gold(),
    "publishing": discord.Color.blurple(),
    "approved": discord.Color.green(),
    "rejected": discord.Color.red(),
}

PARTNERSHIP_EMBED_COLORS = {
    "azul": discord.Color.blurple(),
    "roxo": discord.Color.purple(),
    "verde": discord.Color.green(),
    "amarelo": discord.Color.gold(),
    "vermelho": discord.Color.red(),
    "rosa": discord.Color.magenta(),
    "cinza": discord.Color.dark_grey(),
}

PARTNERSHIP_FORM_STATE: dict[tuple[int, int], dict[str, Any]] = {}


def normalize_text(content: str) -> str:
    return " ".join(content.lower().split())


def discord_invite_code(link: str) -> str | None:
    parsed = urlparse(link)
    if parsed.scheme not in {"http", "https"}:
        return None

    hostname = (parsed.hostname or "").lower()
    parts = [segment for segment in parsed.path.split("/") if segment]

    if hostname in {"discord.gg", "discord.me", "discord.li"}:
        return parts[0] if parts else None

    if hostname in {"discord.com", "www.discord.com", "discordapp.com", "www.discordapp.com"}:
        if len(parts) >= 2 and parts[0].lower() == "invite":
            return parts[1]

    return None


def is_valid_link(link: str) -> bool:
    return discord_invite_code(link) is not None


async def fetch_invite_preview(bot: "PartnershipBot", link: str) -> tuple[str, str | None] | None:
    invite_link = (link or "").strip()
    if not invite_link:
        return None

    if not invite_link.startswith(("http://", "https://")):
        invite_link = f"https://{invite_link}"

    try:
        invite = await bot.fetch_invite(invite_link, with_counts=False, with_expiration=True)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None

    if invite.guild is None:
        return None

    expires_at = invite.expires_at
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        return None

    if invite.max_age is not None and invite.max_age > 0:
        return None

    icon_url = invite.guild.icon.url if invite.guild.icon else None
    return invite.guild.name, icon_url


def fallback_ai_description(server_name: str, summary: str, focus: str = "comunidade") -> str:
    base_summary = summary.strip() or "focamos em criar uma comunidade ativa e acolhedora."
    return (
        f"Olá! Somos {server_name} e estamos em busca de parcerias que fortaleçam nossa comunidade e tragam valor para ambos os lados. "
        f"{base_summary} Nosso foco está em {focus}, com boa convivência, troca de experiências e crescimento mútuo. "
        "Estamos abertos a colaborações, eventos, suporte à comunidade e oportunidades de alcance junto à nossa base."
    )


def generate_ai_description(server_name: str, summary: str, focus: str = "comunidade") -> str:
    cleaned_name = (server_name or "nosso servidor").strip()
    cleaned_summary = (summary or "").strip()
    cleaned_focus = (focus or "comunidade").strip()

    if not cleaned_name and not cleaned_summary:
        return "Descrição não disponível. Informe o nome do servidor e o resumo da parceria."

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback_ai_description(cleaned_name or "nosso servidor", cleaned_summary, cleaned_focus)

    model = os.getenv("OPENAI_MODEL", "glm-4.5-flash")
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é uma IA especializada em melhorar descrições de servidores Discord. "
                    "Não invente fatos que não foram informados. Apenas embeleze a descrição, use emojis de forma natural e mantenha a proposta fiel ao que foi dito. "
                    "Responda em português, sem listas longas, sem mentir e sem mencionar que você é IA."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Melhore a descrição de parceria do servidor {cleaned_name}. "
                    f"Contexto: {cleaned_summary or 'servidor focado em comunidade, eventos e troca de conhecimento'}. "
                    f"Foco principal: {cleaned_focus}. "
                    "Deixe o texto mais bonito, acolhedor e persuasivo, mantendo a honestidade e adicionando emojis sem exagero."
                ),
            },
        ],
        "temperature": 0.7,
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload_response = json.loads(response.read().decode("utf-8"))
            content = payload_response["choices"][0]["message"]["content"].strip()
            if content:
                return content
    except (HTTPError, URLError, KeyError, ValueError, TimeoutError) as exc:
        logger.warning("Falha ao gerar descrição com IA: %s", exc)

    return fallback_ai_description(cleaned_name or "nosso servidor", cleaned_summary, cleaned_focus)


def status_label(status: str) -> str:
    return PARTNERSHIP_STATUS_LABELS.get(status, status.title())


def partnership_embed(request: dict[str, Any]) -> discord.Embed:
    custom_color = request.get("color")
    color = partnership_embed_color(custom_color) if custom_color else PARTNERSHIP_STATUS_COLORS.get(request["status"], discord.Color.blurple())
    embed = discord.Embed(
        title="Solicitação de parceria",
        description=request["description"],
        color=color,
    )
    embed.add_field(name="Solicitante", value=f"<@{request['requester_id']}>", inline=True)
    embed.add_field(name="Status", value=status_label(request["status"]), inline=True)
    embed.add_field(name="Link", value=f"[Abrir link]({request['link']})", inline=False)

    if request.get("publication_channel_id"):
        embed.add_field(
            name="Canal de publicação",
            value=f"<#{request['publication_channel_id']}>",
            inline=False,
        )

    embed.set_footer(text=f"Solicitação #{request['id']}")
    return embed


def published_partnership_embed(request: dict[str, Any], server_name: str | None, icon_url: str | None) -> discord.Embed:
    embed = discord.Embed(
        title=server_name,
        description=request["description"],
        color=partnership_embed_color(request.get("color")),
    )
    if icon_url:
        embed.set_thumbnail(url=icon_url)
    return embed


def published_partnership_view(link: str) -> discord.ui.View:
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Entrar no servidor", style=discord.ButtonStyle.link, url=link))
    return view


def get_partnership_form_state(guild_id: int, user_id: int) -> dict[str, Any]:
    key = (guild_id, user_id)
    if key not in PARTNERSHIP_FORM_STATE:
        PARTNERSHIP_FORM_STATE[key] = {
            "description": "",
            "link": "",
            "color": "azul",
        }
    return PARTNERSHIP_FORM_STATE[key]


def partnership_embed_color(color_name: str | None) -> discord.Color:
    return PARTNERSHIP_EMBED_COLORS.get((color_name or "azul").lower(), discord.Color.blurple())


class PartnershipManualModal(discord.ui.Modal, title="Descrição manual da parceria"):
    def __init__(self, guild_id: int, user_id: int) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        current = get_partnership_form_state(guild_id, user_id).get("description", "")
        self.description = discord.ui.TextInput(
            label="Descrição da parceria",
            style=discord.TextStyle.paragraph,
            required=True,
            placeholder="Descreva o seu servidor, proposta e o que torna a parceria interessante.",
            default=current,
            min_length=20,
            max_length=MAX_DESCRIPTION_LENGTH,
        )
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        state = get_partnership_form_state(self.guild_id, self.user_id)
        state["description"] = self.description.value.strip()
        view = PartnershipSetupView(interaction.client, self.guild_id, self.user_id)
        await interaction.response.send_message(
            "✅ Descrição manual salva. Revise a sua proposta e envie quando estiver pronta.",
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


class PartnershipLinkModal(discord.ui.Modal, title="Link do convite"):
    def __init__(self, guild_id: int, user_id: int) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        current = get_partnership_form_state(guild_id, user_id).get("link", "")
        self.link = discord.ui.TextInput(
            label="Convite permanente do Discord",
            required=True,
            placeholder="discord.gg/seu-servidor ou https://discord.gg/seu-servidor",
            default=current,
            min_length=5,
            max_length=MAX_LINK_LENGTH,
        )
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        state = get_partnership_form_state(self.guild_id, self.user_id)
        state["link"] = self.link.value.strip()
        view = PartnershipSetupView(interaction.client, self.guild_id, self.user_id)
        await interaction.response.send_message(
            "✅ Link salvo. Você pode revisar a proposta e enviar quando quiser.",
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


class PartnershipAIModal(discord.ui.Modal, title="Melhorar descrição com IA"):
    def __init__(self, guild_id: int, user_id: int) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.server_name = discord.ui.TextInput(
            label="Nome do servidor",
            required=True,
            placeholder="Ex.: Pixel Guild",
            max_length=120,
        )
        self.summary = discord.ui.TextInput(
            label="Resumo básico do servidor",
            style=discord.TextStyle.paragraph,
            required=True,
            placeholder="Ex.: comunidade de games, eventos, amizades, discussões e atividades semanais.",
            min_length=20,
            max_length=500,
        )
        self.focus = discord.ui.TextInput(
            label="Foco da parceria (opcional)",
            required=False,
            placeholder="Ex.: comunidade, eventos, educação, games",
            max_length=80,
        )
        self.add_item(self.server_name)
        self.add_item(self.summary)
        self.add_item(self.focus)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        state = get_partnership_form_state(self.guild_id, self.user_id)
        description = generate_ai_description(
            self.server_name.value.strip(),
            self.summary.value.strip(),
            (self.focus.value or "comunidade").strip(),
        )
        state["description"] = description
        view = PartnershipSetupView(interaction.client, self.guild_id, self.user_id)
        await interaction.response.send_message(
            "✨ Descrição aprimorada pela IA foi salva na sua solicitação.",
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


class PartnershipSetupView(discord.ui.View):
    def __init__(self, bot: "PartnershipBot", guild_id: int, user_id: int) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id

    def build_embed(self) -> discord.Embed:
        state = get_partnership_form_state(self.guild_id, self.user_id)
        embed = discord.Embed(
            title="Solicitação de parceria",
            description="Configure sua parceria antes de enviar para a staff.",
            color=partnership_embed_color(state.get("color")),
        )
        embed.add_field(
            name="Descrição",
            value=(state.get("description") or "Ainda não foi preenchida.")[:1024],
            inline=False,
        )
        embed.add_field(
            name="Link do servidor",
            value=(state.get("link") or "Ainda não foi preenchido.")[:1024],
            inline=False,
        )
        embed.add_field(
            name="Cor da embed",
            value=(state.get("color") or "azul").title(),
            inline=True,
        )
        return embed

    @discord.ui.select(
        placeholder="Escolha a cor da embed",
        options=[
            discord.SelectOption(label="Azul", value="azul", emoji="🔵", default=True),
            discord.SelectOption(label="Roxo", value="roxo", emoji="🟣"),
            discord.SelectOption(label="Verde", value="verde", emoji="🟢"),
            discord.SelectOption(label="Amarelo", value="amarelo", emoji="🟡"),
            discord.SelectOption(label="Vermelho", value="vermelho", emoji="🔴"),
            discord.SelectOption(label="Rosa", value="rosa", emoji="🩷"),
            discord.SelectOption(label="Cinza", value="cinza", emoji="⚪"),
        ],
        custom_id="partnership:color-select",
    )
    async def pick_color(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select["PartnershipSetupView"],
    ) -> None:
        state = get_partnership_form_state(self.guild_id, self.user_id)
        state["color"] = (select.values[0] if select.values else "azul").lower()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Descrição manual", style=discord.ButtonStyle.primary, custom_id="partnership:manual")
    async def manual_description(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["PartnershipSetupView"],
    ) -> None:
        await interaction.response.send_modal(PartnershipManualModal(self.guild_id, self.user_id))

    @discord.ui.button(label="Melhorar com IA", style=discord.ButtonStyle.success, custom_id="partnership:ai")
    async def ai_description(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["PartnershipSetupView"],
    ) -> None:
        await interaction.response.send_modal(PartnershipAIModal(self.guild_id, self.user_id))

    @discord.ui.button(label="Link do convite", style=discord.ButtonStyle.secondary, custom_id="partnership:link")
    async def link_description(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["PartnershipSetupView"],
    ) -> None:
        await interaction.response.send_modal(PartnershipLinkModal(self.guild_id, self.user_id))

    @discord.ui.button(label="Enviar solicitação", style=discord.ButtonStyle.blurple, custom_id="partnership:submit")
    async def submit_partnership(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["PartnershipSetupView"],
    ) -> None:
        state = get_partnership_form_state(self.guild_id, self.user_id)
        await submit_partnership_request(
            interaction,
            state.get("description", "").strip(),
            (state.get("link") or "").strip(),
            partnership_embed_color(state.get("color")),
        )


async def submit_partnership_request(
    interaction: discord.Interaction,
    description: str,
    invite_link: str,
    embed_color: discord.Color | None = None,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Esse comando só pode ser usado dentro de um servidor.", ephemeral=True)
        return

    description = description.strip()
    invite_link = invite_link.strip()

    if not description:
        await interaction.response.send_message(
            "Preencha a descrição da parceria antes de enviar. Você pode usar a opção de descrição manual ou melhorar com IA.",
            ephemeral=True,
        )
        return
    if len(description) > MAX_DESCRIPTION_LENGTH:
        await interaction.response.send_message(
            f"A descrição está muito longa. Use até {MAX_DESCRIPTION_LENGTH} caracteres para manter a solicitação mais confortável.",
            ephemeral=True,
        )
        return
    if len(invite_link) > MAX_LINK_LENGTH or not is_valid_link(invite_link):
        await interaction.response.send_message(
            "Envie um convite permanente válido do Discord, como discord.gg/servidor.",
            ephemeral=True,
        )
        return

    approval_channel_id = bot.database.get_approval_channel(interaction.guild.id)
    if approval_channel_id is None:
        await interaction.response.send_message(
            "A staff ainda não configurou o canal privado. Um administrador deve usar `/configurar` com o canal da staff.",
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

    active_request = bot.database.get_active_request(interaction.guild.id, interaction.user.id)
    if active_request and active_request["approval_message_id"]:
        try:
            await channel.fetch_message(int(active_request["approval_message_id"]))
        except discord.NotFound:
            bot.database.reset_pending_request_for_deleted_message(int(active_request["approval_message_id"]))
            logger.info(
                "Solicitação antiga resetada ao detectar mensagem de aprovação excluída: #%s.",
                active_request["approval_message_id"],
            )

    request_id = bot.database.create_request(interaction.guild.id, interaction.user.id, description, invite_link)
    if request_id is None:
        active_request = bot.database.get_active_request(interaction.guild.id, interaction.user.id)
        if active_request:
            await interaction.response.send_message(
                "⚠️ Você já possui uma solicitação de parceria pendente. Aguarde a decisão da staff.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("Não foi possível criar a solicitação. Tente novamente.", ephemeral=True)
        return

    request = bot.database.get_request(request_id)
    if request is None:
        await interaction.response.send_message("Não foi possível criar a solicitação. Tente novamente.", ephemeral=True)
        return

    request["color"] = str(embed_color or discord.Color.blurple())

    try:
        message = await channel.send(
            content="Nova solicitação de parceria aguardando decisão da staff.",
            embed=partnership_embed(request),
            view=ApprovalView(bot, request_id),
        )
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Falha ao enviar a solicitação #%s.", request_id)
        await interaction.response.send_message(
            "Não consegui enviar a solicitação ao canal privado da staff. Verifique as permissões do bot nesse canal.",
            ephemeral=True,
        )
        return

    bot.database.set_message_id(request_id, message.id)
    PARTNERSHIP_FORM_STATE.pop((interaction.guild.id, interaction.user.id), None)
    await interaction.response.send_message(
        "Sua solicitação foi enviada para a staff e ficará aguardando aprovação.",
        ephemeral=True,
    )


async def delete_message_safely(message: discord.abc.Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


class SuspicionTracker:
    def __init__(self) -> None:
        self._message_times: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._recent_messages: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(deque)
        self._recent_invites: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    def record(self, guild_id: int, user_id: int, content: str) -> str | None:
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
        normalized_content = normalize_text(content)
        if normalized_content:
            recent_messages.append((now, normalized_content))

        if DISCORD_INVITE_PATTERN.search(content):
            recent_invites.append(now)

        if len(message_times) >= SPAM_MESSAGE_LIMIT:
            return f"{len(message_times)} mensagens em {SPAM_WINDOW_SECONDS}s"

        if normalized_content:
            repeated_count = sum(1 for _, value in recent_messages if value == normalized_content)
            if repeated_count >= REPEAT_MESSAGE_LIMIT:
                return f"mensagem repetida {repeated_count} vezes"

        if len(recent_invites) >= INVITE_MESSAGE_LIMIT:
            return f"{len(recent_invites)} convites em {INVITE_WINDOW_SECONDS}s"

        if ("@everyone" in content or "@here" in content) and len(message_times) >= 3:
            return "spam com menções em massa"

        return None


class StaffView(discord.ui.View):
    def __init__(self, bot: "PartnershipBot", request_id: int) -> None:
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
        for component in self.children:
            component.disabled = True


class ApprovalView(StaffView):
    @discord.ui.button(
        label="Permitir parceria",
        style=discord.ButtonStyle.success,
        custom_id="partnership:approve",
    )
    async def approve(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button["ApprovalView"],
    ) -> None:
        await interaction.response.defer()

        request = self.bot.database.get_request(self.request_id)
        if not request or request["status"] != "pending":
            await interaction.followup.send("Essa solicitação já foi revisada ou está sendo publicada.", ephemeral=True)
            return

        if not self.bot.database.set_awaiting_channel(self.request_id, True):
            await interaction.followup.send("Essa solicitação já está sendo revisada por outra pessoa.", ephemeral=True)
            return

        publication_channel_id = self.bot.database.get_publication_channel(interaction.guild.id if interaction.guild else 0)
        if publication_channel_id:
            text = f"O canal padrão atual é <#{publication_channel_id}>. Escolha um canal abaixo para publicar esta parceria."
        else:
            text = "Escolha o canal onde a embed desta parceria será publicada."

        await interaction.edit_original_response(
            content=text,
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
        _button: discord.ui.Button["ApprovalView"],
    ) -> None:
        await interaction.response.defer()
        if not isinstance(interaction.user, discord.Member):
            return

        updated = self.bot.database.review_request(self.request_id, "rejected", interaction.user.id)
        request = self.bot.database.get_request(self.request_id)
        if not updated or not request:
            await interaction.followup.send("Essa solicitação já foi revisada por outra pessoa.", ephemeral=True)
            return

        self.disable_components()
        await interaction.edit_original_response(
            content="Solicitação recusada pela staff.",
            embed=partnership_embed(request),
            view=self,
        )


class PublicationChannelView(StaffView):
    def __init__(self, bot: "PartnershipBot", request_id: int) -> None:
        super().__init__(bot, request_id)
        request = bot.database.get_request(request_id)
        default_channel = bot.database.get_publication_channel(int(request["guild_id"])) if request else None
        for component in self.children:
            if isinstance(component, discord.ui.Button) and component.custom_id == "partnership:use-default":
                component.disabled = default_channel is None

    async def _publish_to_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel) -> None:
        if not interaction.guild:
            return

        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Selecione um canal de texto válido.", ephemeral=True)
            return

        bot_member = interaction.guild.me
        if bot_member:
            permissions = channel.permissions_for(bot_member)
            if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
                await interaction.followup.send(
                    "Eu preciso de **Ver canal**, **Enviar mensagens** e **Inserir links** no canal escolhido.",
                    ephemeral=True,
                )
                return

        request = self.bot.database.get_request(self.request_id)
        if not request or request["status"] != "pending":
            await interaction.followup.send("Essa solicitação já foi revisada ou está sendo publicada.", ephemeral=True)
            return

        preview = await fetch_invite_preview(self.bot, request["link"])
        if preview is None:
            self.disable_components()
            await interaction.edit_original_response(
                content="O convite do Discord está inválido, expirado ou não é permanente. A solicitação continua pendente.",
                embed=partnership_embed(request),
                view=self,
            )
            return

        if not self.bot.database.start_publication(self.request_id, interaction.user.id, channel.id):
            await interaction.followup.send("Essa solicitação já está sendo revisada por outra pessoa.", ephemeral=True)
            return

        name, icon_url = preview
        pub_request = dict(request)
        pub_request["status"] = "approved"
        pub_request["publication_channel_id"] = str(channel.id)

        try:
            message = await channel.send(
                embed=published_partnership_embed(pub_request, name, icon_url),
                view=published_partnership_view(request["link"]),
            )
        except (discord.Forbidden, discord.HTTPException):
            self.bot.database.reset_publication(self.request_id)
            await interaction.followup.send(
                "Não consegui publicar a embed nesse canal. A solicitação voltou para pendente; confira as permissões e tente novamente.",
                ephemeral=True,
            )
            return

        self.bot.database.complete_publication(self.request_id, message.id)
        self.bot.database.set_publication_channel(interaction.guild.id, channel.id)
        self.bot.database.clear_stale_active_requests(interaction.guild.id, int(request["requester_id"]), self.request_id)
        await delete_message_safely(interaction.message)

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
        select: discord.ui.ChannelSelect["PublicationChannelView"],
    ) -> None:
        await interaction.response.defer()
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
                await interaction.followup.send("Não consegui carregar o canal selecionado. Tente novamente.", ephemeral=True)
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
        _button: discord.ui.Button["PublicationChannelView"],
    ) -> None:
        await interaction.response.defer()
        if not interaction.guild:
            return

        default_channel_id = self.bot.database.get_publication_channel(interaction.guild.id)
        if default_channel_id is None:
            await interaction.followup.send("Ainda não existe um canal padrão. Use o seletor para escolher um.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(default_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(default_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None

            if not isinstance(channel, discord.TextChannel):
                await interaction.followup.send("O canal padrão não está disponível. Escolha outro canal no seletor.", ephemeral=True)
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
        _button: discord.ui.Button["PublicationChannelView"],
    ) -> None:
        await interaction.response.defer()
        if not self.bot.database.set_awaiting_channel(self.request_id, False):
            await interaction.followup.send("Essa solicitação não está mais pendente.", ephemeral=True)
            return

        request = self.bot.database.get_request(self.request_id)
        if not request:
            await interaction.followup.send("Não encontrei essa solicitação.", ephemeral=True)
            return

        await interaction.edit_original_response(
            content="Nova solicitação de parceria aguardando decisão da staff.",
            embed=partnership_embed(request),
            view=ApprovalView(self.bot, self.request_id),
        )


class PartnershipBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("&", "#"),
            intents=intents,
        )
        self.database = Database()
        self.suspicion_tracker = SuspicionTracker()

    async def setup_hook(self) -> None:
        self.database.initialize()
        synced = await self.tree.sync()
        logger.info("Comandos slash sincronizados: %s", len(synced))

        for request in self.database.list_pending_requests():
            view = PublicationChannelView(self, int(request["id"])) if request["awaiting_channel"] else ApprovalView(self, int(request["id"]))
            if request["approval_message_id"]:
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
            logger.info("Bot conectado como %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.guild and isinstance(message.author, discord.Member):
            reason = self.suspicion_tracker.record(message.guild.id, message.author.id, message.content)
            if reason:
                await self.mark_suspicious(message.author, reason)

        await self.process_commands(message)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if self.database.reset_pending_request_for_deleted_message(payload.message_id):
            logger.info("Solicitação pendente resetada após exclusão da mensagem de aprovação #%s.", payload.message_id)

    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        for message_id in payload.message_ids:
            if self.database.reset_pending_request_for_deleted_message(message_id):
                logger.info("Solicitação pendente resetada após exclusão em massa da mensagem de aprovação #%s.", message_id)

    async def mark_suspicious(self, member: discord.Member, reason: str) -> None:
        config = self.database.get_trap_config(member.guild.id)
        if config is None:
            return

        role = member.guild.get_role(config["role_id"])
        if role is None or role in member.roles:
            return

        bot_member = member.guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_roles or role >= bot_member.top_role:
            return

        try:
            await member.add_roles(role, reason=f"Detecção automática de comportamento suspeito: {reason}")
        except (discord.Forbidden, discord.HTTPException):
            logger.exception(
                "Não foi possível atribuir o cargo Suspeito a %s no servidor %s.",
                member.id,
                member.guild.id,
            )


bot = PartnershipBot()


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
        await interaction.response.send_message(
            "❌ Você precisa ser dono do servidor, Administrador ou ter **Gerenciar Servidor**.",
            ephemeral=True,
        )
        return

    if canal.overwrites_for(interaction.guild.default_role).view_channel is not False:
        await interaction.response.send_message(
            "❌ O canal precisa ser **privado**: negue **Ver canal** para @everyone.",
            ephemeral=True,
        )
        return

    bot.database.set_approval_channel(interaction.guild.id, canal.id)
    await interaction.response.send_message(f"✅ Canal da staff configurado para {canal.mention}.", ephemeral=True)


@bot.tree.command(name="canal-publicacao", description="Define um canal como canal padrão de publicação de parcerias.")
@app_commands.describe(canal="Canal do servidor que deve receber as publicações de parceria.")
@app_commands.default_permissions(manage_guild=True)
async def canal_publicacao(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
        return

    bot_member = interaction.guild.me
    if bot_member:
        permissions = canal.permissions_for(bot_member)
        if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            await interaction.response.send_message(
                "Eu preciso de **Ver canal**, **Enviar mensagens** e **Inserir links** nesse canal.",
                ephemeral=True,
            )
            return

    bot.database.set_publication_channel(interaction.guild.id, canal.id)
    await interaction.response.send_message(
        f"✅ {canal.mention} foi definido como **canal de publicação de parcerias**.",
        ephemeral=True,
    )


@bot.tree.command(name="parceria-ai", description="Gera uma descrição de parceria com IA para você usar na solicitação.")
@app_commands.describe(
    nome="Nome do seu servidor ou comunidade.",
    sobre="Resumo do que o servidor faz, temáticas e proposta.",
    foco="Foco principal da parceria, como comunidade, eventos, educação, games, etc.",
)
async def partnership_ai(interaction: discord.Interaction, nome: str, sobre: str, foco: str = "comunidade") -> None:
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


@bot.tree.command(name="parceria", description="Cria uma solicitação de parceria com embed customizável.")
@app_commands.describe(
    descricao="Descrição da parceria (opcional se você preferir preencher no formulário).",
    link="Link permanente do convite da sua comunidade (opcional no formulário).",
)
async def partnership(interaction: discord.Interaction, descricao: str | None = None, link: str | None = None) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Esse comando só pode ser usado dentro de um servidor.", ephemeral=True)
        return

    state = get_partnership_form_state(interaction.guild.id, interaction.user.id)
    if descricao is not None:
        state["description"] = descricao.strip()
    if link is not None:
        state["link"] = link.strip()

    if descricao is not None and link is not None:
        await submit_partnership_request(interaction, state.get("description", ""), state.get("link", ""), partnership_embed_color(state.get("color")))
        return

    view = PartnershipSetupView(bot, interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(
        embed=view.build_embed(),
        view=view,
        ephemeral=True,
    )


@bot.tree.command(name="ajuda", description="Mostra os comandos disponíveis do bot.")
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
    embed.add_field(name="/configurar", value="Configura o canal privado de aprovação (staff).", inline=False)
    embed.add_field(name="/canal-publicacao", value="Define um canal específico para publicar parcerias no servidor.", inline=False)
    embed.add_field(name="/armadilha", value="Configura o canal armadilha e marca automaticamente sinais de spam.", inline=False)
    embed.add_field(name="/desarmadilha", value="Desativa a armadilha e restaura o canal.", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="armadilha", description="Configura um canal como armadilha anti-spam.")
@app_commands.describe(canal="Canal de texto que será usado como armadilha. Se não informar, usa o canal atual.")
@app_commands.default_permissions(manage_guild=True)
async def armadilha_slash(interaction: discord.Interaction, canal: discord.TextChannel | None = None) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
        return

    guild = interaction.guild
    trap_channel = canal or interaction.channel
    if not isinstance(trap_channel, discord.TextChannel):
        await interaction.response.send_message("Use esse comando em um canal de texto ou mencione um canal válido.", ephemeral=True)
        return

    bot_member = guild.me
    if bot_member is None:
        await interaction.response.send_message("Não consegui verificar minhas permissões neste servidor.", ephemeral=True)
        return
    if not bot_member.guild_permissions.manage_channels:
        await interaction.response.send_message("Eu preciso da permissão **Gerenciar canais** para configurar a armadilha.", ephemeral=True)
        return
    if not bot_member.guild_permissions.manage_roles:
        await interaction.response.send_message("Eu preciso da permissão **Gerenciar cargos** para atribuir o cargo Suspeito.", ephemeral=True)
        return

    role = discord.utils.get(guild.roles, name=TRAP_ROLE_NAME)
    if role is not None and role.managed:
        await interaction.response.send_message("O cargo Suspeito é gerenciado por uma integração e não pode ser usado.", ephemeral=True)
        return

    try:
        if role is None:
            role = await guild.create_role(
                name=TRAP_ROLE_NAME,
                mentionable=False,
                reason="Cargo usado pela armadilha anti-spam.",
            )
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Não foi possível criar o cargo Suspeito.")
        await interaction.response.send_message("Não consegui criar o cargo Suspeito. Verifique a permissão **Gerenciar cargos**.", ephemeral=True)
        return

    if role >= bot_member.top_role:
        await interaction.response.send_message("Coloque o cargo Suspeito abaixo do meu maior cargo na lista de cargos do servidor.", ephemeral=True)
        return

    try:
        await trap_channel.set_permissions(
            guild.default_role,
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
            await trap_channel.edit(topic=f"{TRAP_TOPIC_MARKER}\n{current_topic}".strip()[:1024])
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Não foi possível configurar o canal armadilha.")
        await interaction.response.send_message("Não consegui configurar esse canal. Verifique **Gerenciar canais** e a posição do cargo Suspeito.", ephemeral=True)
        return

    bot.database.set_trap_config(guild.id, trap_channel.id, role.id)
    await interaction.response.send_message(
        f"Armadilha configurada em {trap_channel.mention}. Quem atingir os critérios de suspeita receberá {role.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="desarmadilha", description="Desativa a armadilha anti-spam de um canal.")
@app_commands.describe(canal="Canal da armadilha. Se não informar, usa o canal configurado no servidor.")
@app_commands.default_permissions(manage_guild=True)
async def desarmadilha_slash(interaction: discord.Interaction, canal: discord.TextChannel | None = None) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Esse comando só funciona em um servidor.", ephemeral=True)
        return

    guild = interaction.guild
    config = bot.database.get_trap_config(guild.id)
    if config is None:
        await interaction.response.send_message("Não há nenhuma armadilha configurada neste servidor.", ephemeral=True)
        return

    trap_channel = canal or guild.get_channel(config["channel_id"])
    if not isinstance(trap_channel, discord.TextChannel):
        await interaction.response.send_message("O canal da armadilha não está disponível.", ephemeral=True)
        return

    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_channels:
        await interaction.response.send_message("Eu preciso da permissão **Gerenciar canais** para desativar a armadilha.", ephemeral=True)
        return

    role = guild.get_role(config["role_id"])
    try:
        await trap_channel.set_permissions(
            guild.default_role,
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

        topic = (trap_channel.topic or "").replace(TRAP_TOPIC_MARKER, "").strip()
        await trap_channel.edit(topic=topic or None)
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Não foi possível desativar o canal armadilha.")
        await interaction.response.send_message("Não consegui restaurar as permissões do canal. Verifique **Gerenciar canais**.", ephemeral=True)
        return

    bot.database.clear_trap_config(guild.id)
    await interaction.response.send_message(f"Armadilha desativada em {trap_channel.mention}.", ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN)