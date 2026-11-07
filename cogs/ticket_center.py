"""
Unified Ticket Center panel — Support, Purchase and Issues/Replacement in ONE
panel (/send-ticket-center). Existing systems are untouched: every option
reuses the same flows as before (support modal / purchase flow / order flow
-> create_ticket_channel). The old panels keep working.

All image/link URLs come from config.py (TICKET_CENTER_*).
"""
from __future__ import annotations

import discord
from discord import app_commands, ui
from discord.ext import commands

import config
from cogs.support_tickets import ProblemModal

SMALL = discord.SeparatorSpacing.small


def _pe(emoji_id: int) -> discord.PartialEmoji:
    return discord.PartialEmoji(name="name", id=emoji_id)


async def _reset_panel(interaction: discord.Interaction) -> None:
    """Re-posts the panel's own view so the select menus go back to their
    placeholder — otherwise Discord keeps showing the last choice and picking
    the same option twice would not fire again."""
    try:
        if interaction.message is not None:
            await interaction.message.edit(view=TicketCenterView())
    except discord.HTTPException:
        pass


class TicketCenterView(ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)

        sep = lambda visible=True: ui.Separator(visible=visible, spacing=SMALL)  # noqa: E731

        # -- selects (custom_ids are unique to this panel)
        support_select = ui.Select(
            custom_id="ticketcenter:support",
            placeholder="@📞 〃 Support Center ",
            options=[
                discord.SelectOption(label="〃 Owner ", value="owner",
                                     description="Talk with the administrator ", emoji=_pe(1545576744956727306)),
                discord.SelectOption(label="〃 Management ", value="manager",
                                     description="Talk with the management team", emoji=_pe(1557694211602513950)),
                discord.SelectOption(label="〃 General Support ", value="general",
                                     description="Talk with the staff team", emoji=_pe(1545577020669427752)),
            ],
        )
        support_select.callback = self.on_support

        purchase_select = ui.Select(
            custom_id="ticketcenter:purchase",
            placeholder="@💰 〃 Purchase Center ",
            options=[
                discord.SelectOption(label="〃 Order ", value="order",
                                     description="Order a Custom Bot ", emoji=_pe(1545578583332757665)),
                discord.SelectOption(label="〃 Purchase ", value="purchase",
                                     description="Purchase an existing bot", emoji=_pe(1545553195760099358)),
            ],
        )
        purchase_select.callback = self.on_purchase

        issues_select = ui.Select(
            custom_id="ticketcenter:issues",
            placeholder="@⚙️ 〃 Issues/Replacement ",
            options=[
                discord.SelectOption(label="〃 Technical Issue ", value="technical",
                                     description="Problem with the bot", emoji=_pe(1545577232922312734)),
                discord.SelectOption(label="〃 Payment Issue ", value="billing",
                                     description="Problem with the payment ", emoji=_pe(1545553195760099358)),
                discord.SelectOption(label="〃 Replacement ", value="replacement",
                                     description="Replace a product ", emoji=_pe(1548741673109037116)),
            ],
        )
        issues_select.callback = self.on_issues

        children: list = [sep()]
        if config.TICKET_CENTER_BANNER_URL:
            children += [ui.MediaGallery(discord.MediaGalleryItem(config.TICKET_CENTER_BANNER_URL)), sep()]

        children += [
            ui.TextDisplay("# <:name:1565041266079698955> 〃 __***GlobalBots™ - Ticket Center***__"),
            sep(),
        ]
        welcome = ui.TextDisplay(
            "***__Welcome to our Ticket Center.__***\n"
            "\n"
            "> <a:name:1545552914334875800> Before you do anything we suggest to learn about our Terms of Service and our Privacy."
        )
        if config.TICKET_CENTER_THUMBNAIL_URL:
            children.append(ui.Section(welcome, accessory=ui.Thumbnail(config.TICKET_CENTER_THUMBNAIL_URL)))
        else:
            children.append(welcome)
        children += [
            sep(),
            ui.ActionRow(
                ui.Button(
                    style=discord.ButtonStyle.link,
                    label="〃 Informations",
                    emoji=_pe(1566461391878095091),
                    url=config.TICKET_CENTER_INFO_URL,
                ),
            ),
            sep(),
            sep(False),
            ui.TextDisplay("## <:name:1548745357717012501> 〃 __***Support Center***__ "),
            ui.TextDisplay(
                "*If you need any help or have any questions, choose the appropriate category*. \n"
                "> <:name:1545576267904974859> **Owner** — Talk directly with the administrator \n"
                "> <:name:1545576267904974859> **Management** — Talk with the management team\n"
                "> <:name:1545576267904974859> **General Support** — Talk with the staff team\n"
            ),
            sep(),
            ui.ActionRow(support_select),
            sep(),
            sep(False),
            ui.TextDisplay("## <:name:1548349993830850713> 〃 __***Purchase Center***__"),
            ui.TextDisplay(
                "*To purchase a custom bot or to order an existing bot.*\n"
                "> <:name:1545576267904974859> **Order** — To order a custom bot suited to your needs\n"
                "> <:name:1545576267904974859> **Purchase** — To buy an existing bot"
            ),
            sep(),
            ui.ActionRow(purchase_select),
            sep(),
            sep(False),
            ui.TextDisplay("## <:name:1545577232922312734> 〃 ***__Issues/Replacement__*** "),
            ui.TextDisplay(
                "*If you want a product replacement, something goes wrong with the bot or the payment. * \n"
                "> <:name:1545576267904974859> **Technical Issue** — Problem with the bot\n"
                "> <:name:1545576267904974859> **Payment Issue** — Problem with the payment or questions \n"
                "> <:name:1545576267904974859> **Replacement** — Replace a product "
            ),
            sep(),
            ui.ActionRow(issues_select),
            sep(),
            sep(False),
            ui.TextDisplay("### <:name:1545578059820826745> 〃 __**TICKET PROCESS**__   "),
            ui.TextDisplay(
                "> <a:name:1545552914334875800> Choose the category that best matches your request.\n"
                "> <a:name:1545552914334875800> Please provide a proper description of your issue or request.\n"
                "> <a:name:1545552914334875800> Our Team will review your ticket and assist you as soon as possible.\n"
                "> <a:name:1545552914334875800> Please don't open an owner ticket without an important reason. This action may result in a warning "
            ),
            sep(),
        ]
        if config.TICKET_CENTER_FOOTER_GIF_URL:
            children += [ui.MediaGallery(discord.MediaGalleryItem(config.TICKET_CENTER_FOOTER_GIF_URL)), sep()]
        children += [
            ui.TextDisplay(
                " <:name:1545831836339409048> 〃 **GlobalBots™, All Rights Reserved ©** "
                "<:name:1545576267904974859> **Ticket  Center** "
            ),
            sep(),
        ]
        self.add_item(ui.Container(*children, accent_colour=0x0062FF))

    # -- callbacks: same flows the old panels used --------------------------
    async def on_support(self, interaction: discord.Interaction) -> None:
        kind = interaction.data["values"][0]
        await interaction.response.send_modal(ProblemModal(kind))
        await _reset_panel(interaction)

    async def on_issues(self, interaction: discord.Interaction) -> None:
        kind = interaction.data["values"][0]
        await interaction.response.send_modal(ProblemModal(kind))
        await _reset_panel(interaction)

    async def on_purchase(self, interaction: discord.Interaction) -> None:
        from cogs.purchase_order_flow import start_order_flow, start_purchase_flow

        choice = interaction.data["values"][0]
        if choice == "order":
            await start_order_flow(interaction)
        else:
            await start_purchase_flow(interaction)
        await _reset_panel(interaction)


class TicketCenter(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="send-ticket-center",
        description="Post the unified Ticket Center panel (Support / Purchase / Issues) in this channel",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def send_ticket_center(self, interaction: discord.Interaction) -> None:
        await interaction.channel.send(view=TicketCenterView())
        await interaction.response.send_message("Ticket Center panel sent.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    bot.add_view(TicketCenterView())
    await bot.add_cog(TicketCenter(bot))
