from __future__ import annotations

import re
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

import config
from emojis import EMOJI
from utils.storage import store, TRANSCRIPTS_DIR
from utils.transcripts import build_transcript

# Ticket "kinds" that belong to the support-panel system (Owner / General
# Support / Technical / Billing) use their own staff roles + category,
# configured separately from the shop's Purchase/Order tickets.
SUPPORT_KINDS = {"owner", "general", "technical", "billing"}

TICKET_TITLES = {
    "purchase": f"{EMOJI['purchase']} Purchase Ticket",
    "order": f"{EMOJI['order']} Order Ticket",
    "owner": f"{EMOJI['support_owner']} Contact Owner Ticket",
    "general": f"{EMOJI['support_general']} General Support Ticket",
    "technical": f"{EMOJI['support_technical']} Technical Issue Ticket",
    "billing": f"{EMOJI['support_billing']} Billing Issue Ticket",
}

TICKET_ACCENT_COLOURS = {
    "purchase": discord.Colour.green(),
    "order": discord.Colour.blue(),
    "owner": discord.Colour.gold(),
    "general": discord.Colour.teal(),
    "technical": discord.Colour.orange(),
    "billing": discord.Colour.dark_red(),
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def staff_role_ids_for_kind(kind: str | None) -> list[int]:
    if kind in SUPPORT_KINDS:
        return config.SUPPORT_STAFF_ROLES
    return config.staff_role_ids()


def is_staff(member: discord.Member, kind: str | None = None) -> bool:
    staff_ids = set(staff_role_ids_for_kind(kind))
    return any(role.id in staff_ids for role in member.roles)


def safe_name(name: str) -> str:
    """Turns a display name into something usable in a channel name.
    Keeps letters from any script (Greek included), not just a-z."""
    cleaned = re.sub(r"[\s_]+", "-", name.strip().lower())
    cleaned = re.sub(r"[^\w\-]", "", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "customer"


async def get_log_channel(guild: discord.Guild, kind: str | None = None) -> discord.TextChannel | None:
    channel_id = config.SUPPORT_LOG_CHANNEL if kind in SUPPORT_KINDS else config.CHANNEL_LOG
    channel = guild.get_channel(channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


def ticket_overwrites(
    guild: discord.Guild, customer: discord.Member, kind: str | None = None
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        customer: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }
    for role_id in staff_role_ids_for_kind(kind):
        role = guild.get_role(role_id)
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
    return overwrites


# --------------------------------------------------------------------------
# Dynamic buttons (survive bot restarts — state is read from the JSON store
# using the channel id encoded in the custom_id)
# --------------------------------------------------------------------------

class ClaimButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ticket:claim:(?P<channel_id>[0-9]+)",
):
    def __init__(self, channel_id: int, claimed_by: int | None = None):
        self.channel_id = channel_id
        label = "Claim"
        style = discord.ButtonStyle.primary
        if claimed_by:
            label = "Claimed"
            style = discord.ButtonStyle.secondary
        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,
                emoji=EMOJI["claim"],
                custom_id=f"ticket:claim:{channel_id}",
                disabled=bool(claimed_by),
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["channel_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await store.get(self.channel_id)
        if ticket is None:
            return await interaction.response.send_message(
                "This ticket no longer exists.", ephemeral=True
            )
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user, ticket["kind"]):
            return await interaction.response.send_message(
                "Only staff can claim tickets.", ephemeral=True
            )
        if ticket.get("claimed_by"):
            return await interaction.response.send_message(
                "This ticket is already claimed.", ephemeral=True
            )

        await store.update(self.channel_id, claimed_by=interaction.user.id)
        await interaction.response.send_message(
            f"{EMOJI['claim']} Ticket claimed by {interaction.user.mention}."
        )
        await refresh_ticket_panel(interaction.channel, interaction.client)


class PingButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ticket:ping:(?P<channel_id>[0-9]+)",
):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(
            discord.ui.Button(
                label="Ping User",
                style=discord.ButtonStyle.secondary,
                emoji=EMOJI["ping"],
                custom_id=f"ticket:ping:{channel_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["channel_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await store.get(self.channel_id)
        if ticket is None:
            return await interaction.response.send_message(
                "This ticket no longer exists.", ephemeral=True
            )

        claimed_by = ticket.get("claimed_by")
        if not claimed_by or interaction.user.id != claimed_by:
            return await interaction.response.send_message(
                "Only the staff member who claimed this ticket can ping the user.",
                ephemeral=True,
            )

        guild = interaction.guild
        customer = guild.get_member(ticket["customer_id"]) if guild else None
        if customer is None:
            return await interaction.response.send_message(
                "Could not find the customer in this server.", ephemeral=True
            )

        try:
            await customer.send(
                f"{EMOJI['ping']} You have a notification in your ticket: <#{self.channel_id}>"
            )
            await interaction.response.send_message(
                f"{EMOJI['ping']} Pinged {customer.mention} via DM.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Could not DM this user — their DMs may be closed.", ephemeral=True
            )


class CloseButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ticket:close:(?P<channel_id>[0-9]+)",
):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(
            discord.ui.Button(
                label="Close",
                style=discord.ButtonStyle.danger,
                emoji=EMOJI["close"],
                custom_id=f"ticket:close:{channel_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["channel_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await store.get(self.channel_id)
        if ticket is None:
            return await interaction.response.send_message(
                "This ticket no longer exists.", ephemeral=True
            )
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user, ticket["kind"]):
            return await interaction.response.send_message(
                "Only staff can close this ticket.", ephemeral=True
            )

        await interaction.response.send_modal(CloseReasonModal(self.channel_id))


class TranscriptButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ticket:transcript:(?P<channel_id>[0-9]+)",
):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(
            discord.ui.Button(
                label="View Transcript",
                style=discord.ButtonStyle.secondary,
                emoji=EMOJI["transcript"],
                custom_id=f"ticket:transcript:{channel_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["channel_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        path = TRANSCRIPTS_DIR / f"{self.channel_id}.txt"
        if not path.exists():
            return await interaction.response.send_message(
                "Transcript file not found.", ephemeral=True
            )
        await interaction.response.send_message(
            file=discord.File(path), ephemeral=True
        )


# --------------------------------------------------------------------------
# Panels (Components V2)
# --------------------------------------------------------------------------

class TicketPanelView(discord.ui.LayoutView):
    """The panel posted once in the ticket panel channel — Purchase / Order."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

        purchase_btn = discord.ui.Button(
            label="Purchase",
            style=discord.ButtonStyle.success,
            emoji=EMOJI["purchase"],
            custom_id="ticket:open:purchase",
        )
        purchase_btn.callback = self.on_purchase

        order_btn = discord.ui.Button(
            label="Order Support",
            style=discord.ButtonStyle.primary,
            emoji=EMOJI["order"],
            custom_id="ticket:open:order",
        )
        order_btn.callback = self.on_order

        children = []
        if config.PANEL_BANNER_URL:
            children.append(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=config.PANEL_BANNER_URL)
                )
            )

        header_text = discord.ui.TextDisplay(f"{EMOJI['bot']} **Bot Shop — Ticket Center**")
        body_text = discord.ui.TextDisplay(
            "Need a bot, or have a question about an order?\n"
            "Pick an option below and we'll take care of you."
        )

        if config.PANEL_THUMBNAIL_URL:
            children.append(
                discord.ui.Section(
                    header_text,
                    body_text,
                    accessory=discord.ui.Thumbnail(media=config.PANEL_THUMBNAIL_URL),
                )
            )
        else:
            children.append(header_text)
            children.append(body_text)

        children.append(discord.ui.Separator())
        children.append(discord.ui.ActionRow(purchase_btn, order_btn))

        container = discord.ui.Container(*children, accent_colour=discord.Colour(0x3D91FF))
        self.add_item(container)

    async def on_purchase(self, interaction: discord.Interaction) -> None:
        from cogs.purchase_order_flow import start_purchase_flow
        await start_purchase_flow(interaction)

    async def on_order(self, interaction: discord.Interaction) -> None:
        from cogs.purchase_order_flow import start_order_flow
        await start_order_flow(interaction)


def format_ticket_details(kind: str, fields: dict[str, str] | None) -> str:
    if not fields:
        return "Please describe what you need below — a member of staff will be with you shortly."

    if kind == "purchase":
        return (
            f"{EMOJI['bot']} **Type of bot:** {fields.get('bot_type', '-')}\n"
            f"{EMOJI['plan']} **Plan:** {fields.get('plan', '-')}\n"
            f"{EMOJI['payment']} **Payment Method:** {fields.get('payment_method', '-')}"
        )

    if kind == "order":
        return (
            f"{EMOJI['server']} **Server:** {fields.get('server', '-')}\n"
            f"{EMOJI['budget']} **Budget:** {fields.get('budget', '-')}\n"
            f"{EMOJI['payment']} **Payment Method:** {fields.get('payment_method', '-')}\n\n"
            f"**Description:**\n{fields.get('description', '-')}"
        )

    if fields.get("description"):
        return f"**Description:**\n{fields['description']}"

    return "Please describe what you need below — a member of staff will be with you shortly."


def build_ticket_control_view(
    channel_id: int,
    kind: str,
    customer: discord.Member,
    fields: dict[str, str] | None,
    claimed_by: int | None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)

    title = TICKET_TITLES.get(kind, kind.title())

    # discord.ui.Section allows at most 3 text children, so the details are
    # grouped into a single block instead of one TextDisplay per line.
    header = discord.ui.TextDisplay(f"**{title}**\nCustomer: {customer.mention}")
    details = discord.ui.TextDisplay(format_ticket_details(kind, fields))

    texts = [header, details]
    if claimed_by:
        texts.append(discord.ui.TextDisplay(f"Claimed by: <@{claimed_by}>"))

    section = discord.ui.Section(
        *texts,
        accessory=discord.ui.Thumbnail(media=customer.display_avatar.url),
    )

    action_row = discord.ui.ActionRow(
        ClaimButton(channel_id, claimed_by),
        PingButton(channel_id),
        CloseButton(channel_id),
    )

    container = discord.ui.Container(
        section,
        discord.ui.Separator(),
        action_row,
        accent_colour=TICKET_ACCENT_COLOURS.get(kind, discord.Colour.blue()),
    )
    view.add_item(container)
    return view


async def refresh_ticket_panel(channel: discord.abc.Messageable, bot: discord.Client) -> None:
    ticket = await store.get(channel.id)
    if not ticket:
        return
    guild = channel.guild
    customer = guild.get_member(ticket["customer_id"])
    if customer is None:
        return

    panel_message_id = ticket.get("panel_message_id")
    if panel_message_id is None:
        return

    try:
        message = await channel.fetch_message(panel_message_id)
    except discord.NotFound:
        return

    view = build_ticket_control_view(
        channel.id, ticket["kind"], customer, ticket.get("fields"), ticket.get("claimed_by")
    )
    await message.edit(view=view)


# --------------------------------------------------------------------------
# Modals
# --------------------------------------------------------------------------

class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Reason for closing",
        placeholder="e.g. Order completed, Resolved, Customer inactive...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await close_ticket(
            interaction, self.channel_id, reason=self.reason.value or "No reason provided"
        )


# --------------------------------------------------------------------------
# Core actions
# --------------------------------------------------------------------------

async def create_ticket_channel(
    interaction: discord.Interaction, kind: str, fields: dict[str, str] | None
) -> None:
    guild = interaction.guild
    customer = interaction.user
    if guild is None or not isinstance(customer, discord.Member):
        return await interaction.response.send_message(
            "This can only be used inside the server.", ephemeral=True
        )

    await interaction.response.send_message(
        "Creating your ticket...", ephemeral=True
    )

    category_id = config.TICKET_CATEGORIES.get(kind, config.TICKET_CATEGORY)
    category = guild.get_channel(category_id)
    channel_name = f"{safe_name(customer.display_name)}-{kind}"

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category if isinstance(category, discord.CategoryChannel) else None,
        overwrites=ticket_overwrites(guild, customer, kind),
        reason=f"Ticket opened by {customer} ({customer.id})",
    )

    view = build_ticket_control_view(channel.id, kind, customer, fields, claimed_by=None)
    panel_message = await channel.send(view=view)

    await store.create(
        channel.id,
        customer_id=customer.id,
        kind=kind,
        fields=fields,
        claimed_by=None,
        panel_message_id=panel_message.id,
        opened_at=dt.datetime.utcnow().isoformat(),
    )

    await interaction.edit_original_response(
        content=f"Your ticket has been created: {channel.mention}"
    )

    await log_ticket_open(guild, channel, customer, kind, fields)


async def close_ticket(interaction: discord.Interaction, channel_id: int, reason: str) -> None:
    guild = interaction.guild
    ticket = await store.get(channel_id)
    channel = guild.get_channel(channel_id) if guild else None

    if ticket is None or channel is None:
        return await interaction.response.send_message(
            "This ticket no longer exists.", ephemeral=True
        )

    customer = guild.get_member(ticket["customer_id"])
    kind = ticket["kind"]

    await interaction.response.send_message(
        f"{EMOJI['close']} Closing this ticket in 5 seconds..."
    )

    transcript_file = await build_transcript(channel)
    transcript_path = TRANSCRIPTS_DIR / f"{channel_id}.txt"
    transcript_path.write_bytes(transcript_file.fp.getvalue())
    transcript_file.fp.seek(0)

    if customer is not None:
        dm_view = discord.ui.LayoutView(timeout=None)
        dm_container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay("**Your ticket has been closed**"),
                discord.ui.TextDisplay(f"**Closed by:** {interaction.user}\n**Reason:** {reason}"),
                accessory=discord.ui.Thumbnail(media=guild.icon.url if guild.icon else customer.display_avatar.url),
            ),
            accent_colour=discord.Colour.red(),
        )
        dm_view.add_item(dm_container)
        try:
            dm_file = discord.File(transcript_path, filename=transcript_path.name)
            await customer.send(view=dm_view, file=dm_file)
        except discord.Forbidden:
            pass

    await log_ticket_close(guild, channel, customer, kind, interaction.user, reason, transcript_path)

    await store.delete(channel_id)

    await discord.utils.sleep_until(
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)
    )
    await channel.delete(reason=f"Ticket closed by {interaction.user} — {reason}")


async def log_ticket_open(
    guild: discord.Guild,
    channel: discord.TextChannel,
    customer: discord.Member,
    kind: str,
    fields: dict[str, str] | None,
) -> None:
    log_channel = await get_log_channel(guild, kind)
    if log_channel is None:
        return

    view = discord.ui.LayoutView(timeout=None)

    header = discord.ui.TextDisplay(
        f"{EMOJI['log_open']} **Ticket Opened**\n"
        f"**Customer:** {customer.mention} ({customer.id})\n"
        f"**Type:** {kind.title()} — **Channel:** {channel.mention}"
    )
    texts = [header]
    details_text = format_ticket_details(kind, fields)
    if fields:
        texts.append(discord.ui.TextDisplay(details_text))
    section = discord.ui.Section(
        *texts, accessory=discord.ui.Thumbnail(media=customer.display_avatar.url)
    )
    container = discord.ui.Container(section, accent_colour=discord.Colour.green())
    view.add_item(container)
    await log_channel.send(view=view)


async def log_ticket_close(
    guild: discord.Guild,
    channel: discord.abc.GuildChannel,
    customer: discord.Member | None,
    kind: str,
    closed_by: discord.abc.User,
    reason: str,
    transcript_path,
) -> None:
    log_channel = await get_log_channel(guild, kind)
    if log_channel is None:
        return

    view = discord.ui.LayoutView(timeout=None)

    texts = [
        discord.ui.TextDisplay(
            f"{EMOJI['log_close']} **Ticket Closed**\n"
            f"**Customer:** {customer.mention if customer else 'Unknown'}\n"
            f"**Type:** {kind.title()} — **Channel:** #{channel.name}"
        ),
        discord.ui.TextDisplay(
            f"**Closed by:** {closed_by.mention}\n**Reason:** {reason}"
        ),
    ]
    thumbnail_url = (
        customer.display_avatar.url if customer else guild.icon.url if guild.icon else None
    )
    if thumbnail_url:
        content_items = [discord.ui.Section(*texts, accessory=discord.ui.Thumbnail(media=thumbnail_url))]
    else:
        content_items = texts

    action_row = discord.ui.ActionRow(TranscriptButton(channel.id))
    container = discord.ui.Container(*content_items, action_row, accent_colour=discord.Colour.red())
    view.add_item(container)
    await log_channel.send(view=view, file=discord.File(transcript_path, filename=transcript_path.name))


# --------------------------------------------------------------------------
# Cog
# --------------------------------------------------------------------------

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="send-panel", description="Post the ticket panel in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_panel(self, interaction: discord.Interaction) -> None:
        await interaction.channel.send(view=TicketPanelView())
        await interaction.response.send_message("Panel sent.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    for item_cls in (ClaimButton, PingButton, CloseButton, TranscriptButton):
        bot.add_dynamic_items(item_cls)
    bot.add_view(TicketPanelView())
    await bot.add_cog(Tickets(bot))
