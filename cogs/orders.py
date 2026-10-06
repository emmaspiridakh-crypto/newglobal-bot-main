from __future__ import annotations

import re
import logging
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.storage import store, order_store
from cogs.tickets import is_staff, EMOJI, format_ticket_details as format_order_details


log = logging.getLogger(__name__)

# Discord select menus hold at most 25 options.
MAX_SELECT_OPTIONS = 25


def result_view(text: str, colour: discord.Colour = discord.Colour(0x3D91FF)) -> discord.ui.LayoutView:
    """A Components V2 message can never carry `content=` — and the ephemeral
    /place-order messages are V2 messages. Editing them with
    `edit_message(content=..., view=None)` is rejected by Discord, which made
    the whole interaction fail. Results are shown as a panel instead."""
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(text), accent_colour=colour))
    return view


# --------------------------------------------------------------------------
# Logging — same panel-style system as cogs.tickets, own channel
# --------------------------------------------------------------------------

ORDER_LOG_STYLE = {
    "placed": (EMOJI["place_order"], "Order Placed", discord.Colour.gold()),
    "accepted": (EMOJI["order_accept"], "Order Accepted", discord.Colour.blue()),
    "completed": (EMOJI["order_done"], "Order Completed", discord.Colour.green()),
    "cancelled": (EMOJI["order_cancel"], "Order Cancelled", discord.Colour.red()),
}


async def get_orders_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel = guild.get_channel(config.CHANNEL_ORDERS_LOG)
    return channel if isinstance(channel, discord.TextChannel) else None


async def log_order_event(
    guild: discord.Guild, order: dict, event: str, actor: discord.abc.User
) -> None:
    log_channel = await get_orders_log_channel(guild)
    if log_channel is None:
        return

    emoji, label, colour = ORDER_LOG_STYLE[event]
    member = guild.get_member(order["customer_id"])
    ticket_channel = guild.get_channel(order["ticket_channel_id"])

    header = discord.ui.TextDisplay(
        f"{emoji} **{label}**\n"
        f"**Customer:** {member.mention if member else 'Unknown'} "
        f"({order['customer_id']})\n"
        f"**Type:** {order['kind'].title()} — "
        f"**Ticket:** {ticket_channel.mention if ticket_channel else '#unknown'}\n"
        f"**By:** {actor.mention}"
    )
    details = discord.ui.TextDisplay(format_order_details(order["kind"], order.get("fields")))

    thumbnail_url = (
        member.display_avatar.url if member else guild.icon.url if guild.icon else None
    )
    if thumbnail_url:
        content_items = [
            discord.ui.Section(header, details, accessory=discord.ui.Thumbnail(media=thumbnail_url))
        ]
    else:
        content_items = [header, details]

    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(*content_items, accent_colour=colour)
    view.add_item(container)
    await log_channel.send(view=view)


# --------------------------------------------------------------------------
# Step 1: ticket picker (ephemeral, right after /place-order)
# --------------------------------------------------------------------------

class TicketPickerView(discord.ui.LayoutView):
    def __init__(self, tickets: list[dict], guild: discord.Guild):
        super().__init__(timeout=180)
        self.guild = guild

        options = []
        for ticket in tickets:
            if len(options) >= MAX_SELECT_OPTIONS:
                break
            channel = guild.get_channel(ticket["channel_id"])
            if channel is None:
                continue
            member = guild.get_member(ticket["customer_id"])
            options.append(
                discord.SelectOption(
                    label=f"#{channel.name}",
                    value=str(ticket["channel_id"]),
                    description=f"{ticket['kind'].title()} — {member.display_name if member else 'Unknown'}"[:100],
                    emoji=EMOJI["purchase"] if ticket["kind"] == "purchase" else EMOJI["order"],
                )
            )

        select = discord.ui.Select(
            placeholder="Choose a ticket..." if options else "No open tickets available",
            options=options or [discord.SelectOption(label="none", value="none")],
            disabled=not options,
            custom_id="place_order:pick",
        )
        select.callback = self.on_select

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"{EMOJI['place_order']} **Place Order — choose a ticket**"),
            discord.ui.ActionRow(select),
            accent_colour=discord.Colour(0x3D91FF),
        )
        self.add_item(container)

    async def on_select(self, interaction: discord.Interaction) -> None:
        channel_id = int(interaction.data["values"][0])
        ticket = await store.get(channel_id)
        if ticket is None:
            return await interaction.response.edit_message(
                view=result_view("That ticket no longer exists.", discord.Colour.red())
            )
        await interaction.response.edit_message(
            view=OrderConfirmView(channel_id, ticket, self.guild)
        )


# --------------------------------------------------------------------------
# Step 2: confirmation panel (still ephemeral)
# --------------------------------------------------------------------------

class OrderConfirmView(discord.ui.LayoutView):
    def __init__(self, channel_id: int, ticket: dict, guild: discord.Guild):
        super().__init__(timeout=180)
        self.channel_id = channel_id
        self.ticket = ticket
        self.guild = guild

        channel = guild.get_channel(channel_id)
        member = guild.get_member(ticket["customer_id"])

        confirm_btn = discord.ui.Button(
            label="Confirm",
            style=discord.ButtonStyle.success,
            emoji=EMOJI["order_accept"],
        )
        confirm_btn.callback = self.on_confirm

        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji=EMOJI["order_cancel"],
        )
        cancel_btn.callback = self.on_cancel

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"{EMOJI['place_order']} **Confirm order**\n"
                f"Customer: {member.mention if member else 'Unknown'}\n"
                f"Ticket: {channel.mention if channel else '#unknown'} ({ticket['kind'].title()})"
            ),
            discord.ui.TextDisplay(format_order_details(ticket["kind"], ticket.get("fields"))),
            discord.ui.ActionRow(confirm_btn, cancel_btn),
            accent_colour=discord.Colour(0x3D91FF),
        )
        self.add_item(container)

    async def on_confirm(self, interaction: discord.Interaction) -> None:
        await send_order_panel(interaction, self.channel_id, self.ticket, self.guild)

    async def on_cancel(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=result_view(f"{EMOJI['order_cancel']} Cancelled.", discord.Colour.red())
        )


# --------------------------------------------------------------------------
# Step 3: the persistent panel in the orders channel
# --------------------------------------------------------------------------

STATUS_TEXT = {
    "pending": f"{EMOJI['order_pending']} **Pending**",
    "accepted": f"{EMOJI['order_accept']} **Accepted**",
    "completed": f"{EMOJI['order_done']} **Completed**",
    "cancelled": f"{EMOJI['order_cancel']} **Cancelled**",
}


class AcceptButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"order:accept:(?P<order_id>[0-9]+)",
):
    def __init__(self, order_id: int):
        self.order_id = order_id
        super().__init__(
            discord.ui.Button(
                label="Accept",
                style=discord.ButtonStyle.success,
                emoji=EMOJI["order_accept"],
                custom_id=f"order:accept:{order_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["order_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await handle_accept(interaction, self.order_id)


class DoneButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"order:done:(?P<order_id>[0-9]+)",
):
    def __init__(self, order_id: int):
        self.order_id = order_id
        super().__init__(
            discord.ui.Button(
                label="Done",
                style=discord.ButtonStyle.primary,
                emoji=EMOJI["order_done"],
                custom_id=f"order:done:{order_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["order_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await handle_done(interaction, self.order_id)


class OrderCancelButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"order:cancel:(?P<order_id>[0-9]+)",
):
    def __init__(self, order_id: int):
        self.order_id = order_id
        super().__init__(
            discord.ui.Button(
                label="Cancel",
                style=discord.ButtonStyle.danger,
                emoji=EMOJI["order_cancel"],
                custom_id=f"order:cancel:{order_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["order_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await handle_cancel(interaction, self.order_id)


def build_order_panel_view(order: dict, guild: discord.Guild) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    member = guild.get_member(order["customer_id"])
    channel = guild.get_channel(order["ticket_channel_id"])
    status = order["status"]

    header = discord.ui.TextDisplay(
        f"{EMOJI['place_order']} **Order** — {STATUS_TEXT.get(status, status)}\n"
        f"Customer: {member.mention if member else 'Unknown'}\n"
        f"Ticket: {channel.mention if channel else '#unknown'} ({order['kind'].title()})"
    )
    details = discord.ui.TextDisplay(format_order_details(order["kind"], order.get("fields")))

    section = discord.ui.Section(
        header,
        details,
        accessory=discord.ui.Thumbnail(
            media=member.display_avatar.url if member else guild.icon.url if guild.icon else "https://cdn.discordapp.com/embed/avatars/0.png"
        ),
    )

    buttons = []
    if status == "pending":
        buttons = [AcceptButton(order["order_id"]), OrderCancelButton(order["order_id"])]
    elif status == "accepted":
        buttons = [DoneButton(order["order_id"]), OrderCancelButton(order["order_id"])]
    # "completed" and "cancelled" -> no buttons, panel is final

    accent = {
        "pending": discord.Colour.gold(),
        "accepted": discord.Colour.blue(),
        "completed": discord.Colour.green(),
        "cancelled": discord.Colour.red(),
    }.get(status, discord.Colour.greyple())

    children = [section]
    if buttons:
        children.append(discord.ui.ActionRow(*buttons))

    container = discord.ui.Container(*children, accent_colour=accent)
    view.add_item(container)
    return view


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

async def send_order_panel(
    interaction: discord.Interaction, channel_id: int, ticket: dict, guild: discord.Guild
) -> None:
    # Database + channel sends take longer than Discord's 3 second window,
    # so acknowledge first and edit the ephemeral message at the end.
    await interaction.response.defer()

    orders_channel = guild.get_channel(config.CHANNEL_ORDERS)
    if not isinstance(orders_channel, discord.TextChannel):
        return await interaction.edit_original_response(
            view=result_view("Orders channel is not configured correctly.", discord.Colour.red())
        )

    existing = await order_store.get_active_for_ticket(channel_id)
    if existing is not None:
        return await interaction.edit_original_response(
            view=result_view(
                f"This ticket already has an active order (#{existing['order_id']}, "
                f"{existing['status']}). Finish or cancel it first.",
                discord.Colour.red(),
            )
        )

    order_id = await order_store.create(
        ticket_channel_id=channel_id,
        customer_id=ticket["customer_id"],
        kind=ticket["kind"],
        fields=ticket.get("fields"),
        status="pending",
        created_by=interaction.user.id,
        created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    order = await order_store.get(order_id)

    try:
        message = await orders_channel.send(view=build_order_panel_view(order, guild))
    except discord.HTTPException:
        # Don't leave an order in the database that nobody can see.
        log.exception("Could not post order %s in the orders channel", order_id)
        await order_store.delete(order_id)
        return await interaction.edit_original_response(
            view=result_view(
                "I couldn't post in the orders channel (check my permissions there).",
                discord.Colour.red(),
            )
        )
    await order_store.update(order_id, orders_message_id=message.id)
    order["orders_message_id"] = message.id

    try:
        await log_order_event(guild, order, "placed", interaction.user)
    except discord.HTTPException:
        log.exception("Could not log order %s", order_id)

    await interaction.edit_original_response(
        view=result_view(
            f"{EMOJI['order_accept']} Order sent to {orders_channel.mention}.",
            discord.Colour.green(),
        )
    )


async def refresh_order_panel(order: dict, guild: discord.Guild) -> None:
    orders_channel = guild.get_channel(config.CHANNEL_ORDERS)
    if not isinstance(orders_channel, discord.TextChannel) or not order.get("orders_message_id"):
        return
    try:
        message = await orders_channel.fetch_message(order["orders_message_id"])
        await message.edit(view=build_order_panel_view(order, guild))
    except discord.NotFound:
        return
    except discord.HTTPException:
        log.exception("Could not refresh the panel of order %s", order["order_id"])


async def send_order_dm(
    guild: discord.Guild, order: dict, message: str, colour: discord.Colour
) -> None:
    """DMs the customer a panel about their order, mentioning the ticket channel."""
    member = guild.get_member(order["customer_id"])
    if member is None:
        return
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(f"{message}\nTicket: <#{order['ticket_channel_id']}>"),
            accent_colour=colour,
        )
    )
    try:
        await member.send(view=view)
    except discord.HTTPException:
        pass  # DMs closed or Discord refused — the order itself already went through


TICKET_STATUS_STYLE = {
    "accepted": (f"{EMOJI['order_pending']} **Your order has been accepted and is pending.**", discord.Colour.blue()),
    "completed": (f"{EMOJI['order_done']} **Your order has been completed.**", discord.Colour.green()),
    "cancelled": (f"{EMOJI['order_cancel']} **Your order has been cancelled.**", discord.Colour.red()),
}


async def update_ticket_status_message(guild: discord.Guild, order: dict) -> None:
    """Keeps ONE order-status message inside the ticket: it is posted on
    accept and then edited on done / cancelled (instead of posting a new
    message each time). Its id is stored in orders.ticket_panel_message_id."""
    ticket_channel = guild.get_channel(order["ticket_channel_id"])
    style = TICKET_STATUS_STYLE.get(order["status"])
    if not isinstance(ticket_channel, discord.TextChannel) or style is None:
        return
    text, colour = style
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(text), accent_colour=colour))

    try:
        message_id = order.get("ticket_panel_message_id")
        if message_id:
            try:
                message = await ticket_channel.fetch_message(message_id)
                await message.edit(view=view)
                return
            except discord.NotFound:
                pass  # the message was deleted — post a fresh one below
        message = await ticket_channel.send(view=view)
        await order_store.update(order["order_id"], ticket_panel_message_id=message.id)
        order["ticket_panel_message_id"] = message.id
    except discord.HTTPException:
        log.exception("Could not update the order status message in ticket %s", ticket_channel.id)


async def _guard_staff(interaction: discord.Interaction, text: str) -> bool:
    """True if the user is staff and the click happened inside the server."""
    if (
        interaction.guild is None
        or not isinstance(interaction.user, discord.Member)
        or not is_staff(interaction.user)
    ):
        await interaction.response.send_message(text, ephemeral=True)
        return False
    return True


async def handle_accept(interaction: discord.Interaction, order_id: int) -> None:
    if not await _guard_staff(interaction, "Only staff can accept orders."):
        return

    # Several database / channel calls follow — defer so the click never
    # shows "This interaction failed" when Turso is a bit slow.
    await interaction.response.defer(ephemeral=True, thinking=True)

    order = await order_store.get(order_id)
    if order is None or order["status"] != "pending":
        return await interaction.followup.send("This order can't be accepted right now.", ephemeral=True)

    await order_store.update(order_id, status="accepted")
    order["status"] = "accepted"
    guild = interaction.guild

    await refresh_order_panel(order, guild)
    try:
        await log_order_event(guild, order, "accepted", interaction.user)
    except discord.HTTPException:
        log.exception("Could not log acceptance of order %s", order_id)

    await update_ticket_status_message(guild, order)

    await send_order_dm(
        guild, order,
        f"{EMOJI['order_accept']} **Your order has been accepted and is pending.**",
        discord.Colour.blue(),
    )
    await interaction.followup.send(f"{EMOJI['order_accept']} Order accepted.", ephemeral=True)


async def handle_done(interaction: discord.Interaction, order_id: int) -> None:
    if not await _guard_staff(interaction, "Only staff can complete orders."):
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    order = await order_store.get(order_id)
    if order is None or order["status"] != "accepted":
        return await interaction.followup.send("This order can't be marked done right now.", ephemeral=True)

    await order_store.update(order_id, status="completed")
    order["status"] = "completed"
    guild = interaction.guild

    await refresh_order_panel(order, guild)
    try:
        await log_order_event(guild, order, "completed", interaction.user)
    except discord.HTTPException:
        log.exception("Could not log completion of order %s", order_id)

    await update_ticket_status_message(guild, order)

    await send_order_dm(
        guild, order,
        f"{EMOJI['order_done']} **Your order has been completed.**",
        discord.Colour.green(),
    )
    await interaction.followup.send(f"{EMOJI['order_done']} Order marked as completed.", ephemeral=True)


async def handle_cancel(interaction: discord.Interaction, order_id: int) -> None:
    if not await _guard_staff(interaction, "Only staff can cancel orders."):
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    order = await order_store.get(order_id)
    if order is None or order["status"] in ("completed", "cancelled"):
        return await interaction.followup.send("This order can't be cancelled.", ephemeral=True)

    await order_store.update(order_id, status="cancelled")
    order["status"] = "cancelled"
    guild = interaction.guild

    await refresh_order_panel(order, guild)
    try:
        await log_order_event(guild, order, "cancelled", interaction.user)
    except discord.HTTPException:
        log.exception("Could not log cancellation of order %s", order_id)

    await update_ticket_status_message(guild, order)

    await send_order_dm(
        guild, order,
        f"{EMOJI['order_cancel']} **Your order has been cancelled.**",
        discord.Colour.red(),
    )
    await interaction.followup.send(f"{EMOJI['order_cancel']} Order cancelled.", ephemeral=True)


# --------------------------------------------------------------------------
# Cog
# --------------------------------------------------------------------------

class Orders(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="place-order", description="Start an order for an open ticket")
    async def place_order(self, interaction: discord.Interaction) -> None:
        if (
            interaction.guild is None
            or not isinstance(interaction.user, discord.Member)
            or not is_staff(interaction.user)
        ):
            return await interaction.response.send_message(
                "Only Developer, CEO or Co-CEO can use this.", ephemeral=True
            )

        tickets = [t for t in await store.list_all() if t["kind"] in ("order", "purchase")]
        await interaction.response.send_message(
            view=TicketPickerView(tickets, interaction.guild), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    for item_cls in (AcceptButton, DoneButton, OrderCancelButton):
        bot.add_dynamic_items(item_cls)
    await bot.add_cog(Orders(bot))
