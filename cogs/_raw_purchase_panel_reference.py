"""
Literal Python (Components V2) conversion of webhook-message.json
(GlobalBots Purchase Center). No logic added — reproduces the exact same
panel structure as the uploaded JSON.

KNOWN ISSUES CARRIED OVER FROM THE JSON (see chat for details):
  1. Both category buttons (Purchase, Order) share custom_id="btn_action"
     — they cannot be told apart in a callback as-is. Fixed in the real
     implementation (cogs/purchase_order_flow.py + cogs/tickets.py), not
     here.
  2. The banner media URL is an empty string — needs a real URL before
     this is sent for real.
"""

import discord
from discord import ui

BANNER_URL = ""  # <-- was "" in the JSON, needs a real URL


def build_raw_purchase_panel() -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)

    container = ui.Container(
        ui.MediaGallery(discord.MediaGalleryItem(media=BANNER_URL)),
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
            accessory=ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Purchase",
                custom_id="btn_action",  # duplicated in the source JSON — see note above
                emoji=discord.PartialEmoji(name="name", id=1545553195760099358),
            ),
        ),
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large),
        ui.Section(
            ui.TextDisplay(
                "<:name:1545576267904974859> __**Order a Custom Bot: **__\n"
                "> -#  Share your thoughts and desired features with us, and let us design your dream bot."
            ),
            accessory=ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Order",
                custom_id="btn_action",  # duplicated in the source JSON — see note above
                emoji=discord.PartialEmoji(name="name", id=1548349993830850713),
            ),
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
            "-# <:name:1545576625574387762> Opening tickets without a reason may result in a warning.\n"
            "-# <:name:1545831836339409048> GlobalBots All Rights Reserved ©"
        ),
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        accent_colour=None,
    )
    view.add_item(container)
    return view
