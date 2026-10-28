"""
The live Purchase / Order ticket panel (Components V2).
Posted via /send-panel and re-registered as a persistent view on startup.
All URLs come from config.py (PURCHASE_PANEL_*).
"""

import discord
from discord import ui

import config

SMALL = discord.SeparatorSpacing.small
LARGE = discord.SeparatorSpacing.large


class PurchasePanelView(ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)

        # custom_ids are unchanged so already-posted panels keep working.
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
            emoji=discord.PartialEmoji(name="name", id=1545578583332757665),
        )
        order_btn.callback = self.on_order

        showcase_btn = ui.Button(
            style=discord.ButtonStyle.link,
            label="Showcase",
            emoji=discord.PartialEmoji(name="name", id=1545576824380067860),
            url=config.PURCHASE_PANEL_SHOWCASE_URL,
        )

        welcome = ui.TextDisplay(
                    "###  ***<:name:1565041266079698955> 〃  __Welcome to our Purchase Center!__***\n"
                    "> -  <a:name:1545552914334875800> Here, you can open a ticket to either purchase "
                    "an existing bot or place an order for a custom one suited to your needs. Before "
                    "you purchase or order anything check the "
                    f"[TOS]({config.PURCHASE_PANEL_TOS_URL}) and our "
                    f"[PRIVACY]({config.PURCHASE_PANEL_PRIVACY_URL}). "
                    "Click the button below to also check our bot showcase!"
        )

        children: list = [ui.Separator(visible=True, spacing=SMALL)]
        if config.PURCHASE_PANEL_BANNER_URL:
            children += [
                ui.MediaGallery(discord.MediaGalleryItem(config.PURCHASE_PANEL_BANNER_URL)),
                ui.Separator(visible=True, spacing=SMALL),
            ]
        children += [
            ui.TextDisplay("# <:name:1548349993830850713> ***〃 __PURCHASE CENTER__***"),
            ui.Separator(visible=True, spacing=SMALL),
        ]
        if config.PURCHASE_PANEL_LOGO_URL:
            children.append(ui.Section(welcome, accessory=ui.Thumbnail(config.PURCHASE_PANEL_LOGO_URL)))
        else:
            children.append(welcome)
        children += [
            ui.Separator(visible=True, spacing=SMALL),
            ui.ActionRow(showcase_btn),
            ui.Separator(visible=True, spacing=LARGE),
            ui.TextDisplay(
                "###  <:name:1545553195760099358> 〃 **  __Purchase An Existing Bot: __**\n"
                "> -  <a:name:1545552914334875800> Select the ready made bot that fits your "
                "requirements and open a ticket to buy it."
            ),
            ui.Separator(visible=True, spacing=SMALL),
            ui.ActionRow(purchase_btn),
            ui.Separator(visible=True, spacing=SMALL),
            ui.TextDisplay(
                "###  <:name:1545578583332757665> 〃 **  __Order A Custom Bot:  __**\n"
                "> -  <a:name:1545552914334875800> Share your thoughts and desired features with us, "
                "and let us design your dream bot."
            ),
            ui.Separator(visible=True, spacing=SMALL),
            ui.ActionRow(order_btn),
            ui.Separator(visible=True, spacing=SMALL),
        ]
        if config.PURCHASE_PANEL_FOOTER_GIF_URL:
            children += [
                ui.MediaGallery(discord.MediaGalleryItem(config.PURCHASE_PANEL_FOOTER_GIF_URL)),
                ui.Separator(visible=True, spacing=SMALL),
            ]
        children += [
            ui.TextDisplay(
                "> <a:name:1545576625574387762>  __Opening tickets without a reason may result in a warning.__"
            ),
            ui.Separator(visible=True, spacing=SMALL),
            ui.TextDisplay(
                "-# <:name:1545831836339409048> 〃 GlobalBots All Rights Reserved © "
                "<:name:1545576267904974859> Purchase System "
            ),
            ui.Separator(visible=True, spacing=SMALL),
        ]
        self.add_item(ui.Container(*children, accent_colour=0x0091FF))

    async def on_purchase(self, interaction: discord.Interaction) -> None:
        from cogs.purchase_order_flow import start_purchase_flow
        await start_purchase_flow(interaction)

    async def on_order(self, interaction: discord.Interaction) -> None:
        from cogs.purchase_order_flow import start_order_flow
        await start_order_flow(interaction)
