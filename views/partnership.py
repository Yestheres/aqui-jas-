from __future__ import annotations

import discord

from services.ai import generate_ai_description
from services.partnership import partnership_embed_color

MAX_DESCRIPTION_LENGTH = 8000
MAX_LINK_LENGTH = 2000


class PartnershipManualModal(discord.ui.Modal, title="Descrição manual da parceria"):
    def __init__(self, guild_id: int, user_id: int, state: dict[str, str]) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.state = state
        self.description = discord.ui.TextInput(
            label="Descrição da parceria",
            style=discord.TextStyle.paragraph,
            required=True,
            placeholder="Descreva o seu servidor, proposta e o que torna a parceria interessante.",
            default=state.get("description", ""),
            min_length=20,
            max_length=MAX_DESCRIPTION_LENGTH,
        )
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.state["description"] = self.description.value.strip()
        view = PartnershipSetupView(interaction.client, self.guild_id, self.user_id, self.state)
        await interaction.response.send_message(
            "✅ Descrição manual salva. Revise a sua proposta e envie quando estiver pronta.",
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


class PartnershipLinkModal(discord.ui.Modal, title="Link do convite"):
    def __init__(self, guild_id: int, user_id: int, state: dict[str, str]) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.state = state
        self.link = discord.ui.TextInput(
            label="Convite permanente do Discord",
            required=True,
            placeholder="discord.gg/seu-servidor ou https://discord.gg/seu-servidor",
            default=state.get("link", ""),
            min_length=5,
            max_length=MAX_LINK_LENGTH,
        )
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.state["link"] = self.link.value.strip()
        view = PartnershipSetupView(interaction.client, self.guild_id, self.user_id, self.state)
        await interaction.response.send_message(
            "✅ Link salvo. Você pode revisar a proposta e enviar quando quiser.",
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


class PartnershipAIModal(discord.ui.Modal, title="Melhorar descrição com IA"):
    def __init__(self, guild_id: int, user_id: int, state: dict[str, str]) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.state = state
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
        self.state["description"] = generate_ai_description(
            self.server_name.value.strip(),
            self.summary.value.strip(),
            (self.focus.value or "comunidade").strip(),
        )
        view = PartnershipSetupView(interaction.client, self.guild_id, self.user_id, self.state)
        await interaction.response.send_message(
            "✨ Descrição aprimorada pela IA foi salva na sua solicitação.",
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


class PartnershipSetupView(discord.ui.View):
    def __init__(self, bot: discord.Client, guild_id: int, user_id: int, state: dict[str, str]) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.state = state

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Solicitação de parceria",
            description="Configure sua parceria antes de enviar para a staff.",
            color=partnership_embed_color(self.state.get("color")),
        )
        embed.add_field(
            name="Descrição",
            value=(self.state.get("description") or "Ainda não foi preenchida.")[:1024],
            inline=False,
        )
        embed.add_field(
            name="Link do servidor",
            value=(self.state.get("link") or "Ainda não foi preenchido.")[:1024],
            inline=False,
        )
        embed.add_field(
            name="Cor da embed",
            value=(self.state.get("color") or "azul").title(),
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
        self.state["color"] = (select.values[0] if select.values else "azul").lower()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Descrição manual", style=discord.ButtonStyle.primary, custom_id="partnership:manual")
    async def manual_description(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["PartnershipSetupView"],
    ) -> None:
        await interaction.response.send_modal(PartnershipManualModal(self.guild_id, self.user_id, self.state))

    @discord.ui.button(label="Melhorar com IA", style=discord.ButtonStyle.success, custom_id="partnership:ai")
    async def ai_description(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["PartnershipSetupView"],
    ) -> None:
        await interaction.response.send_modal(PartnershipAIModal(self.guild_id, self.user_id, self.state))

    @discord.ui.button(label="Link do convite", style=discord.ButtonStyle.secondary, custom_id="partnership:link")
    async def link_description(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["PartnershipSetupView"],
    ) -> None:
        await interaction.response.send_modal(PartnershipLinkModal(self.guild_id, self.user_id, self.state))
