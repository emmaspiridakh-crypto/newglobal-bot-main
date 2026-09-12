"""
The live Purchase / Order ticket panel (Components V2).
Posted via /send-panel and re-registered as a persistent view on startup.
"""

import discord
from discord import ui

BANNER_URL = "https://i.imgur.com/1kOkAt9.png"  # <-- set a real image URL here before going live


class PurchasePanelView(ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)

        purchase_btn = ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Purchase",
            custom_id="ticket:open:purchase",
            emoji=discord.PartialEmoji(name="name", id=1545553195760099358),
        )
        purchase_btn.callback = self.on_purchase

        order_btn = ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Order",
            custom_id="ticket:open:order",
            emoji=discord.PartialEmoji(name="name", id=1548349993830850713),
        )
        order_btn.callback = self.on_order

        children = []
        if BANNER_URL:
            children.append(ui.MediaGallery(discord.MediaGalleryItem(media=BANNER_URL)))

        children.extend([
            ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large),
            ui.TextDisplay("# <:name:1548349993830850713> *GlobalBots Purchase Center*"),
            ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large),
            ui.TextDisplay(
                "### **<:name:1548349993830850713>  __Welcome to our Purchase Center!__**\n\n"
                "```\n"
                " Here, you can open a ticket to either purchase an existing bot or place an "
                "order for a custom one suited to your needs.\n"
                "```"
            ),
            ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large),
            ui.Section(
                ui.TextDisplay(
                    "**<:name:1545576267904974859>__Purchase an Existing Bot: __**\n"
                    "> -# Select the ready made bot that fits your requirements and open a ticket to buy it."
                ),
                accessory=purchase_btn,
            ),
            ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large),
            ui.Section(
                ui.TextDisplay(
                    "<:name:1545576267904974859> __**Order a Custom Bot: **__\n"
                    "> -#  Share your thoughts and desired features with us, and let us design your dream bot."
                ),
                accessory=order_btn,
            ),
            ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large),
            ui.Section(
                ui.TextDisplay("###  <:name:1545576237022445658> __ **Check Our Bot Showcase!**__"),
                accessory=ui.Button(
                    style=discord.ButtonStyle.link,
                    label="Showcase",
                    url="https://discord.com/channels/1544741507049721926/1545567846887850076",
                ),
            ),
            ui.TextDisplay(
                "-# <a:name:1545576625574387762> Opening tickets without a reason may result in a warning.\n"
                "-# <:name:1545831836339409048> GlobalBots All Rights Reserved ©"
            ),
            ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        ])

        container = ui.Container(*children, accent_colour=None)
        self.add_item(container)

    async def on_purchase(self, interaction: discord.Interaction) -> None:
        from cogs.purchase_order_flow import start_purchase_flow
        await start_purchase_flow(interaction)

    async def on_order(self, interaction: discord.Interaction) -> None:
        from cogs.purchase_order_flow import start_order_flow
        await start_order_flow(interaction)
