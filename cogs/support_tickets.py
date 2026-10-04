from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from emojis import EMOJI
from cogs.tickets import create_ticket_channel

CATEGORY_LABELS = {
    "owner": "Contact Owner",
    "general": "General Support",
    "technical": "Technical Issue",
    "billing": "Billing Issue",
}


class ProblemModal(discord.ui.Modal):
    """Shown after a category button is pressed — the customer writes their
    problem here, and 'Send' (the modal's submit button) opens the ticket."""

    description = discord.ui.TextInput(
        label="Describe your problem",
        style=discord.TextStyle.paragraph,
        placeholder="Please give as much detail as you can...",
        max_length=1000,
    )

    def __init__(self, kind: str):
        super().__init__(title=CATEGORY_LABELS[kind])
        self.kind = kind

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await create_ticket_channel(
            interaction, kind=self.kind, fields={"description": self.description.value}
        )


class SupportPanelView(discord.ui.LayoutView):
    """
    Recreation of the uploaded webhook panel (GlobaBots Support Center),
    with each category button wired to its own custom_id + a problem modal
    instead of the original's single shared "btn_action" custom_id.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

        children = []
        if config.SUPPORT_BANNER_URL:
            children.append(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=config.SUPPORT_BANNER_URL)
                )
            )

        children.append(discord.ui.Separator())

        title_text = discord.ui.TextDisplay(f"# {EMOJI['support_title']} *GlobalBots Support Center*")
        intro_text = discord.ui.TextDisplay(
            "**Welcome to our Support Center.**\n"
            "__Choose the category that best matches what you need help with.__"
        )

        if config.SUPPORT_THUMBNAIL_URL:
            children.append(title_text)
            children.append(discord.ui.Separator())
            children.append(
                discord.ui.Section(
                    intro_text,
                    accessory=discord.ui.Thumbnail(media=config.SUPPORT_THUMBNAIL_URL),
                )
            )
        else:
            children.append(title_text)
            children.append(discord.ui.Separator())
            children.append(intro_text)

        children.append(discord.ui.Separator())

        owner_btn = discord.ui.Button(
            label="Owner", style=discord.ButtonStyle.secondary,
            emoji=EMOJI["support_owner"], custom_id="support:open:owner",
        )
        owner_btn.callback = self.on_owner
        children.append(discord.ui.TextDisplay(f"- {EMOJI['support_owner']} __**Contact Owner**__"))
        children.append(
            discord.ui.Section(
                discord.ui.TextDisplay("> Direct contact with GlobalBots Administration."),
                accessory=owner_btn,
            )
        )
        children.append(discord.ui.Separator())

        support_btn = discord.ui.Button(
            label="Support", style=discord.ButtonStyle.secondary,
            emoji=EMOJI["support_general"], custom_id="support:open:general",
        )
        support_btn.callback = self.on_general
        children.append(discord.ui.TextDisplay(f"- {EMOJI['support_general']} __**General Support**__"))
        children.append(
            discord.ui.Section(
                discord.ui.TextDisplay("> General assistance, questions and support."),
                accessory=support_btn,
            )
        )
        children.append(discord.ui.Separator())

        technical_btn = discord.ui.Button(
            label="Technical Issue", style=discord.ButtonStyle.secondary,
            emoji=EMOJI["support_technical"], custom_id="support:open:technical",
        )
        technical_btn.callback = self.on_technical
        children.append(discord.ui.TextDisplay(f"- {EMOJI['support_technical']} __**Technical Issues**__"))
        children.append(
            discord.ui.Section(
                discord.ui.TextDisplay("> Problems with our bot, bugs, systems not working."),
                accessory=technical_btn,
            )
        )
        children.append(discord.ui.Separator())

        billing_btn = discord.ui.Button(
            label="Billing Issue", style=discord.ButtonStyle.secondary,
            emoji=EMOJI["support_billing"], custom_id="support:open:billing",
        )
        billing_btn.callback = self.on_billing
        children.append(discord.ui.TextDisplay(f"- {EMOJI['support_billing']} __**Billing Issue**__"))
        children.append(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    "> If you have a problem with your payment or something didn't go through."
                ),
                accessory=billing_btn,
            )
        )
        children.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))

        children.append(
            discord.ui.TextDisplay(
                f"**{EMOJI['support_process']} __TICKET PROCESS__**\n\n"
                f"{EMOJI['support_step']} Choose the category that best matches your request.\n"
                f"{EMOJI['support_step']} Please provide a proper description of your issue or request.\n"
                f"{EMOJI['support_step']} Our Team will review your ticket and assist you as soon as possible.\n\n"
                f"> -# {EMOJI['support_warning']} Opening tickets without a reason may result in a warning"
            )
        )
        children.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        children.append(discord.ui.TextDisplay("-# *GlobalBots All Rights Reserved ©*"))

        container = discord.ui.Container(*children, accent_colour=discord.Colour(0x3D91FF))
        self.add_item(container)

    async def on_owner(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ProblemModal("owner"))

    async def on_general(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ProblemModal("general"))

    async def on_technical(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ProblemModal("technical"))

    async def on_billing(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ProblemModal("billing"))


class SupportTickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="send-support-panel", description="Post the support panel in this channel"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def send_support_panel(self, interaction: discord.Interaction) -> None:
        await interaction.channel.send(view=SupportPanelView())
        await interaction.response.send_message("Support panel sent.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    # Claim / Ping / Close / View Transcript are already registered as
    # dynamic items by cogs.tickets — this panel reuses them as-is.
    bot.add_view(SupportPanelView())
    await bot.add_cog(SupportTickets(bot))
