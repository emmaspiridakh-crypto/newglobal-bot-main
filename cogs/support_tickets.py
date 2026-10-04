from __future__ import annotations

import re
import logging
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

import config
from emojis import EMOJI
from utils.storage import store, TRANSCRIPTS_DIR
from utils.transcripts import build_transcript
from cogs._raw_purchase_panel_reference import PurchasePanelView

log = logging.getLogger(__name__)

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

MAX_CHANNEL_OVERWRITES = 100

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
        return list(config.TICKET_KIND_STAFF_ROLES.get(kind, []))
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
    staff_ids = set(staff_role_ids_for_kind(kind))

    # Discord allows at most 100 permission overwrites per channel. Denying
    # *every* role in a big server blows past that limit and channel creation
    # fails with a 400 error. @everyone is always denied; on top of that we
    # only deny the roles that can actually see channels by default
    # (View Channel in their base permissions), and stop before the limit.
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }

    reserved = 2 + len(staff_ids)  # customer + bot + staff roles
    max_role_denies = MAX_CHANNEL_OVERWRITES - reserved - 1
    for role in guild.roles:
        if len(overwrites) - 1 >= max_role_denies:
            break
        if role.id == guild.id or role.id in staff_ids:
            continue
        if not role.permissions.view_channel:
            continue
        overwrites[role] = discord.PermissionOverwrite(view_channel=False)

    overwrites[customer] = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, read_message_history=True
    )
    overwrites[guild.me] = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, manage_channels=True
    )

    for role_id in staff_ids:
        role = guild.get_role(role_id)
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
    return overwrites


def audit_ticket_visibility(
    channel: discord.TextChannel,
    customer: discord.Member,
    kind: str | None,
) -> list[str]:
    """Returns who can see the freshly created ticket channel even though
    they should not (not the customer, not the bot, not a configured staff
    role). Used only for logging — it tells you exactly who is leaking and
    why instead of guessing."""
    guild = channel.guild
    staff_ids = set(staff_role_ids_for_kind(kind))
    leaks: list[str] = []
    for member in guild.members:
        if member.id in (customer.id, guild.me.id):
            continue
        if any(role.id in staff_ids for role in member.roles):
            continue
        perms = channel.permissions_for(member)
        if not perms.view_channel:
            continue
        if member.id == guild.owner_id:
            why = "server owner"
        elif perms.administrator:
            admin_roles = [r.name for r in member.roles if r.permissions.administrator]
            why = "Administrator via role: " + ", ".join(admin_roles or ["?"])
        else:
            why = "roles: " + ", ".join(r.name for r in member.roles if r.id != guild.id)
        leaks.append(f"{member} ({member.id}) — {why}")
    return leaks


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
        all_staff_ids = {r for ids in config.TICKET_KIND_STAFF_ROLES.values() for r in ids}
        all_staff_ids.update(config.staff_role_ids())
        if not isinstance(interaction.user, discord.Member) or not any(
            role.id in all_staff_ids for role in interaction.user.roles
        ):
            return await interaction.response.send_message(
                "Only staff can view transcripts.", ephemeral=True
            )
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

    channel: discord.TextChannel | None = None
    try:
        category_id = config.TICKET_CATEGORIES.get(kind, config.TICKET_CATEGORY)
        category = guild.get_channel(category_id)
        channel_name = f"{safe_name(customer.display_name)}-{kind}"

        channel = await guild.create_text_channel(
            name=channel_name,
            category=category if isinstance(category, discord.CategoryChannel) else None,
            overwrites=ticket_overwrites(guild, customer, kind),
            reason=f"Ticket opened by {customer} ({customer.id})",
        )

        # Safety net: make sure @everyone really cannot see the channel.
        if channel.overwrites_for(guild.default_role).view_channel is not False:
            await channel.set_permissions(
                guild.default_role, view_channel=False, reason="Ticket must be private"
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
    except Exception as exc:
        # Without this, any error here is swallowed and the user is stuck on
        # "Creating your ticket..." forever. Log the full traceback (visible
        # in the Render logs) and tell the user something went wrong.
        log.exception("Failed to create %s ticket for %s (%s)", kind, customer, customer.id)
        if channel is not None:
            try:
                await channel.delete(reason="Ticket creation failed")
            except discord.HTTPException:
                pass
        if isinstance(exc, discord.Forbidden):
            reason = "I'm missing permissions (Manage Channels / access to the ticket category)."
        elif isinstance(exc, discord.HTTPException):
            reason = f"Discord rejected the request ({exc.status}: {exc.text})."
        else:
            reason = f"{type(exc).__name__}: {exc}"
        await interaction.edit_original_response(
            content=f"Could not create your ticket. {reason}"
        )
        return

    await interaction.edit_original_response(
        content=f"Your ticket has been created: {channel.mention}"
    )

    try:
        leaks = audit_ticket_visibility(channel, customer, kind)
        if leaks:
            log.warning(
                "Ticket #%s is visible to %d member(s) who are not staff/customer:\n  %s",
                channel.name, len(leaks), "\n  ".join(leaks[:15]),
            )
    except Exception:
        log.exception("Visibility audit failed for channel %s", channel.id)

    try:
        await log_ticket_open(guild, channel, customer, kind, fields)
    except Exception:
        log.exception("Failed to log ticket open for channel %s", channel.id)


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

    @app_commands.command(
        name="ticket-audit",
        description="Check who can see tickets / log channels and why (admin only)",
    )
    @app_commands.describe(member="A member who can see this ticket but shouldn't - explains why")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_audit(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        lines: list[str] = []

        def everyone_can_see(ch: discord.abc.GuildChannel | None) -> str:
            if ch is None:
                return "NOT FOUND (wrong ID or bot cannot see it)"
            seen = ch.permissions_for(guild.default_role).view_channel
            return "VISIBLE TO @everyone" if seen else "private"

        lines.append("**Channels used by the ticket system**")
        checks = {
            "Purchase/Order log (CHANNEL_LOG)": config.CHANNEL_LOG,
            "Support log (SUPPORT_LOG_CHANNEL)": config.SUPPORT_LOG_CHANNEL,
            "Orders channel (CHANNEL_ORDERS)": config.CHANNEL_ORDERS,
            "Orders log (CHANNEL_ORDERS_LOG)": config.CHANNEL_ORDERS_LOG,
        }
        for label, cid in checks.items():
            ch = guild.get_channel(cid)
            lines.append(f"- {label}: {ch.mention if ch else cid} -> {everyone_can_see(ch)}")

        lines.append("\n**Ticket categories**")
        for kind, cid in config.TICKET_CATEGORIES.items():
            ch = guild.get_channel(cid)
            lines.append(f"- {kind}: {ch.name if ch else cid} -> {everyone_can_see(ch)} (tickets get their own overwrites, so this is informational)")

        ticket = await store.get(interaction.channel.id)
        if ticket is not None and isinstance(interaction.channel, discord.TextChannel):
            customer = guild.get_member(ticket["customer_id"])
            if customer is not None:
                leaks = audit_ticket_visibility(interaction.channel, customer, ticket["kind"])
                lines.append(f"\n**This ticket ({ticket['kind']})** - non-staff who can see it: {len(leaks)}")
                lines.extend(f"- {leak}" for leak in leaks[:15])
                if not leaks:
                    lines.append("- nobody besides the customer, the bot and staff")
                if guild.chunked is False:
                    lines.append("-# Member cache is incomplete, result may miss people.")
        else:
            lines.append("\n-# Run this inside an open ticket channel to also see who can view that ticket.")

        if ticket is not None and isinstance(interaction.channel, discord.TextChannel):
            staff_ids = set(staff_role_ids_for_kind(ticket["kind"]))
            holders = [m for m in guild.members if any(r.id in staff_ids for r in m.roles)]
            staff_names = [r.name for r in guild.roles if r.id in staff_ids]
            lines.append(
                f"\n**Staff roles for this ticket:** {', '.join(staff_names) or 'none found'} "
                f"-> {len(holders)} member(s) hold them (they always see it)"
            )

        if member is not None and isinstance(interaction.channel, discord.TextChannel):
            # Fetch the channel fresh from Discord so we compare with what
            # Discord really has, not with the bot's cache.
            fresh = await guild.fetch_channel(interaction.channel.id)
            lines.append(f"\n**Why {member} can see this channel**")
            lines.append(f"- Real permission calc: view_channel = {fresh.permissions_for(member).view_channel}")
            base = member.guild_permissions
            lines.append(
                f"- Server-wide: administrator={base.administrator}, "
                f"manage_channels={base.manage_channels}, manage_roles={base.manage_roles}"
            )

            def state(ow: discord.PermissionOverwrite) -> str:
                return {True: "ALLOW", False: "DENY", None: "neutral"}[ow.view_channel]

            lines.append(f"- @everyone overwrite on this channel: {state(fresh.overwrites_for(guild.default_role))}")
            for role in member.roles:
                if role.id == guild.id:
                    continue
                tag = " (staff role)" if ticket and role.id in set(staff_role_ids_for_kind(ticket["kind"])) else ""
                lines.append(
                    f"- role {role.name}{tag}: view overwrite={state(fresh.overwrites_for(role))}, "
                    f"role administrator={role.permissions.administrator}"
                )
            lines.append(f"- member overwrite: {state(fresh.overwrites_for(member))}")

        await interaction.followup.send("\n".join(lines)[:1990], ephemeral=True)

    @app_commands.command(name="send-panel", description="Post the ticket panel in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_panel(self, interaction: discord.Interaction) -> None:
        await interaction.channel.send(view=PurchasePanelView())
        await interaction.response.send_message("Panel sent.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    for item_cls in (ClaimButton, PingButton, CloseButton, TranscriptButton):
        bot.add_dynamic_items(item_cls)
    bot.add_view(PurchasePanelView())
    await bot.add_cog(Tickets(bot))
