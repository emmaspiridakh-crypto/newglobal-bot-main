"""
GlobalBots "Informations" panel (ToS / Privacy Policy / FaQ).
Posted via /panel-info. Every button answers with an EPHEMERAL message, so
only the person who pressed it can see it. All URLs come from config.py
(INFO_PANEL_*).

Each button opens its section (ToS / Privacy / FaQ) via SECTION_BUILDERS.
"""
from __future__ import annotations

from typing import Callable

import discord
from discord import app_commands, ui
from discord.ext import commands

import config
from emojis import emoji
from utils.permissions import slash_is_ownership_only

SMALL = discord.SeparatorSpacing.small
INFO_ACCENT = 0x0091FF


def _e(key: str) -> str:
    return emoji("info", key)


def build_panel_view() -> ui.LayoutView:
    def btn(label: str, key: str, custom_id: str) -> ui.Button:
        return ui.Button(
            style=discord.ButtonStyle.secondary,
            label=label,
            emoji=_e(key) or None,
            custom_id=custom_id,
        )

    children: list = [ui.Separator(visible=True, spacing=SMALL)]
    if config.INFO_PANEL_BANNER_URL:
        children += [
            ui.MediaGallery(discord.MediaGalleryItem(config.INFO_PANEL_BANNER_URL)),
            ui.Separator(visible=True, spacing=SMALL),
        ]
    children += [
        ui.TextDisplay(f"## {_e('title')} 〃 __**GlobalBots - Informations**__"),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay(
            f"> - {_e('note')} Before making a purchase, we recommend that you carefully read our "
            "__ToS__ and our __privacy policy__. You can also check the __FAQ__ if you have any questions."
        ),
        ui.Separator(visible=True, spacing=SMALL),
    ]
    agree = ui.TextDisplay(
        f"> - {_e('note')} By reading the Terms of Service (ToS) and the Privacy Policy, "
        "you agree to these terms."
    )
    if config.INFO_PANEL_LOGO_URL:
        children.append(ui.Section(agree, accessory=ui.Thumbnail(config.INFO_PANEL_LOGO_URL)))
    else:
        children.append(agree)
    children += [
        ui.Separator(visible=True, spacing=SMALL),
        ui.ActionRow(
            btn(" 〃 ToS", "tos", "info:tos"),
            btn("〃 Privacy Policy", "privacy", "info:privacy"),
            btn("〃 FaQ", "faq", "info:faq"),
        ),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay(
            f"> -# {_e('footer')} 〃 **GlobalBots, All Rights Reserved {_e('footer_right')} Informations**"
        ),
        ui.Separator(visible=True, spacing=SMALL),
    ]

    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*children, accent_colour=INFO_ACCENT))
    return view


LARGE = discord.SeparatorSpacing.large
DOT = "<:name:1545576267904974859>"


def _intro(text: ui.TextDisplay):
    """Intro block with the GlobalBots logo as thumbnail (URL from config)."""
    if config.INFO_PANEL_LOGO_URL:
        return ui.Section(text, accessory=ui.Thumbnail(config.INFO_PANEL_LOGO_URL))
    return text


def _sep(spacing: discord.SeparatorSpacing = SMALL) -> ui.Separator:
    return ui.Separator(visible=True, spacing=spacing)


def _wrap(*children, accent: int) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*children, accent_colour=accent))
    return view


def build_tos_view() -> ui.LayoutView:
    return _wrap(
        _sep(),
        ui.TextDisplay("## <:name:1566484047943704656> 〃 __**Terms Of Service (ToS)**__"),
        _sep(),
        _intro(ui.TextDisplay(
            "<:name:1566128213858459848> __By purchasing, accessing, or using any service provided by "
            "GlobalBots, you agree to the following Terms of Service.__"
        )),
        _sep(LARGE),
        ui.TextDisplay(
            f" {DOT} ***__PURCHASES__***\n"
            "> -   All customers are responsible for reviewing a product before purchasing.\n"
            "> - By completing a purchase, you confirm that you understand what you are buying.\n"
            "> - You must provide accurate information when placing an order."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            f"{DOT} ***__PAYMENTS__***\n"
            "> - Payment must be completed before a product is delivered unless otherwise agreed.\n"
            "> -  Do not send payment to unofficial members or unauthorized accounts.\n"
            "> -  lobal Bots is not responsible for payments sent to impersonators or unauthorized individuals."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            f"{DOT} **__*PRODUCT USAGE*__**\n"
            "> -  Purchased products may only be used according to the license or permissions provided with the product.\n"
            "> - Redistributing, reselling, leaking, or sharing purchased products without permission is prohibited.\n"
            "> -  Attempting to remove protections or claim our products as your own is not permitted."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            f"{DOT} ***__REFUNDS__***\n"
            "> - Refund eligibility depends on the product and the circumstances of the purchase.\n"
            "> - Once a product has been delivered, refunds may not be available.\n"
            "> - Contact Support before making a purchase if you have questions about a product."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            f"{DOT} ***__SUPPORT__***\n"
            "> - Customers must communicate respectfully with our staff.\n"
            "> - False claims, harassment, threats, or abuse toward staff will not be tolerated.\n"
            "> - Please use the appropriate support ticket for your issue."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            f"{DOT} **__*ACCOUNT & SERVER SECURITY*__**\n"
            "> - You are responsible for keeping your Discord account and purchased products secure.\n"
            "> - Never share passwords, tokens, API keys, or other sensitive credentials with anyone."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            f"{DOT} **__*VIOLATIONS*__**\n"
            "> - GlobalBots reserves the right to refuse service, cancel orders, or restrict access to our services when these Terms are violated."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            f"{DOT} **__*CHANGES*__**\n"
            "> - GlobalBots may update these Terms of Service when necessary. Continued use of our services after changes means you accept the updated Terms."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            "<:name:1566453823189418146> 〃 ***__By purchasing from Global Bots, you acknowledge that you have "
            "read, understood, and agreed to these Terms of Service.__***"
        ),
        _sep(),
        ui.TextDisplay(f"> <:name:1566128213858459848> 〃 __Professional{DOT}Reliable{DOT}Secure__"),
        _sep(),
        ui.TextDisplay(f"<:name:1545831836339409048> 〃 **GlobalBots, All Rights Reserved** {DOT} **Terms of Service**"),
        _sep(),
        accent=0x007BFF,
    )


def build_privacy_view() -> ui.LayoutView:
    return _wrap(
        _sep(),
        ui.TextDisplay("## <:name:1566484521073905824> 〃 **__Privacy & Data Protection __**"),
        _sep(),
        _intro(ui.TextDisplay(
            "> <:name:1566128213858459848> **Your privacy matters to us.**\n"
            " \n"
            "> <:name:1566128213858459848>__ At GlobalBots, we are committed to keeping your information safe and "
            "private. We only collect or use information that is necessary to provide our services, process "
            "orders, and provide customer support.__"
        )),
        _sep(LARGE),
        ui.TextDisplay(
            "<:name:1566484521073905824> 〃 **What We Protect**\n\n"
            f"{DOT} Personal information\n"
            f"{DOT} Order and payment-related information\n"
            f"{DOT} Discord information required for support\n"
            f"{DOT} Messages and information shared through support tickets"
        ),
        _sep(LARGE),
        ui.TextDisplay(
            "<:name:1566450266469961778> 〃 **What We Don’t Do**\n\n"
            f"{DOT} We do not sell your personal information.\n"
            f"{DOT} We do not share your information with unauthorized people.\n"
            f"{DOT} We do not use your information for purposes unrelated to our services."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            " <:name:1545553071872933898> 〃 **__*Support Tickets*__**\n\n\n"
            f"> {DOT} Please avoid sharing passwords, Discord tokens, payment-card numbers, or other highly sensitive information in tickets."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            "<:name:1548349993830850713> 〃 **__*Orders*__**\n\n\n"
            f"> {DOT} Information provided during an order is used only for fulfilling and managing that order and providing necessary support."
        ),
        _sep(LARGE),
        ui.TextDisplay(
            "<:name:1566484521073905824> 〃 **__*Your Privacy = Our Responsibility*__**\n\n\n"
            f"> {DOT} ***By using our services, you agree to our Privacy Policy and understand that certain information may need to be processed to provide our services.***\n\n"
            f"{DOT} **If you have any questions regarding privacy or your data, please contact our Support Team.**\n"
        ),
        _sep(),
        ui.TextDisplay(f"<:name:1545831836339409048> 〃 **GlobalBots, All Rights Reserved {DOT} Privacy & Data Protection**"),
        _sep(),
        accent=0x006EFF,
    )


def build_faq_view() -> ui.LayoutView:
    def q(emoji_id: str, question: str, answer: str) -> list:
        return [
            ui.TextDisplay(f"{DOT} <:name:{emoji_id}> 〃 ***__{question}__***"),
            ui.TextDisplay(f"> {answer}"),
            _sep(LARGE),
        ]

    children: list = [
        ui.TextDisplay("## <:name:1548740498603122788> 〃 **__FREQUENTLY ASKED QUESTIONS (FaQ)__**"),
        _sep(),
        _intro(ui.TextDisplay("*__Welcome to GlobalBots FaQ! Here are answers to some of our most common questions.__*")),
        _sep(LARGE),
    ]
    children += q("1545576824380067860", "What do you sell?",
                  "We provide a variety of Discord bots. Check our shop or open a ticket for available products.")
    children += q("1545553195760099358", "What payment methods do you accept?",
                  "Available payment methods may vary. Please contact Support before purchasing to confirm the available options.")
    children += q("1545578583332757665", "How will I receive my product?",
                  "After your payment has been confirmed, our team will provide your purchased product or delivery instructions.")
    children += q("1545553071872933898", "How do I purchase something?",
                  "Open a Purchase Ticket and tell us which product you are interested in. A member of our team will assist you.")
    children += q("1545577232922312734", "I have an issue with my product. What should I do?",
                  "Open a Technical Support Ticket and provide details about the issue. Our team will help you troubleshoot it")
    children += q("1548741673109037116", "Can I get a refund?",
                  "Refunds depend on the product and the circumstances of the purchase. Please read our Refund Policy or contact Support before purchasing.")
    children += q("1566484521073905824", "Is my information safe?",
                  "Yes. We take privacy seriously and only use necessary information to provide our services. Please see our Privacy Policy for more information.")
    children += q("1566453777131774022", "How long does delivery take?",
                  "Delivery times depend on the product and whether it is automated or manually delivered. Support can provide an estimated timeframe.")
    children += q("1566453662937649182", "Can I request a custom bot?",
                  "If custom development is available, open an Order Ticket and explain what you need.")
    children += q("1548745357717012501", "Still have a question?",
                  "No problem! Open a Support Ticket and our team will be happy to help.")
    children += [
        ui.TextDisplay(f"**__Professional__{DOT} __Reliable__{DOT} __Secure__**"),
        ui.TextDisplay(f"<:name:1545831836339409048> 〃** GlobalBots, All Rights Reserved {DOT} FaQ**"),
        _sep(),
    ]
    return _wrap(*children, accent=0x006EFF)


# key (the part after "info:") -> function returning the ephemeral view.
SECTION_BUILDERS: dict[str, Callable[[], ui.LayoutView]] = {
    "tos": build_tos_view,
    "privacy": build_privacy_view,
    "faq": build_faq_view,
}


class InfoPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="panel-info", description="Send the Informations panel (ToS / Privacy / FaQ)")
    @slash_is_ownership_only()
    async def panel_info(self, interaction: discord.Interaction):
        # Acknowledge first (Discord gives only 3 seconds), then post the panel.
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.channel.send(view=build_panel_view())
        await interaction.followup.send("Panel sent.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("info:"):
            return

        builder = SECTION_BUILDERS.get(custom_id.split(":", 1)[1])
        if builder is None:
            await interaction.response.send_message("This section is not available yet.", ephemeral=True)
            return
        await interaction.response.send_message(view=builder(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoPanel(bot))
