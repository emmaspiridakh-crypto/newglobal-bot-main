from __future__ import annotations

import re
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.storage import store, order_store
from cogs.tickets import is_staff, EMOJI, format_ticket_details as format_order_details


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
                content="That ticket no longer exists.", view=None
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
        await interaction.response.edit_message(content="Cancelled.", view=None)


# --------------------------------------------------------------------------
# Step 3: the persistent panel in the orders channel
# --------------------------------------------------------------------------

STATUS_TEXT = {
    "pending": "⏳ **Pending**",
    "accepted": "✅ **Accepted**",
    "completed": "✔️ **Completed**",
    "cancelled": "🚫 **Cancelled**",
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
    orders_channel = guild.get_channel(config.CHANNEL_ORDERS)
    if not isinstance(orders_channel, discord.TextChannel):
        return await interaction.response.edit_message(
            content="Orders channel is not configured correctly.", view=None
        )

    order_id = await order_store.create(
        ticket_channel_id=channel_id,
        customer_id=ticket["customer_id"],
        kind=ticket["kind"],
        fields=ticket.get("fields"),
        status="pending",
        created_by=interaction.user.id,
        created_at=dt.datetime.utcnow().isoformat(),
    )

    order = await order_store.get(order_id)
    view = build_order_panel_view(order, guild)
    message = await orders_channel.send(view=view)
    await order_store.update(order_id, orders_message_id=message.id)

    await log_order_event(guild, order, "placed", interaction.user)

    await interaction.response.edit_message(
        content=f"Order sent to {orders_channel.mention}.", view=None
    )


async def refresh_order_panel(order: dict, guild: discord.Guild) -> None:
    orders_channel = guild.get_channel(config.CHANNEL_ORDERS)
    if not isinstance(orders_channel, discord.TextChannel) or not order.get("orders_message_id"):
        return
    try:
        message = await orders_channel.fetch_message(order["orders_message_id"])
    except discord.NotFound:
        return
    await message.edit(view=build_order_panel_view(order, guild))


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
    except discord.Forbidden:
        pass


async def handle_accept(interaction: discord.Interaction, order_id: int) -> None:
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        return await interaction.response.send_message("Only staff can accept orders.", ephemeral=True)

    order = await order_store.get(order_id)
    if order is None or order["status"] != "pending":
        return await interaction.response.send_message("This order can't be accepted right now.", ephemeral=True)

    await order_store.update(order_id, status="accepted")
    order = await order_store.get(order_id)
    guild = interaction.guild

    await interaction.response.send_message(f"{EMOJI['order_accept']} Order accepted.", ephemeral=True)
    await refresh_order_panel(order, guild)
    await log_order_event(guild, order, "accepted", interaction.user)

    ticket_channel = guild.get_channel(order["ticket_channel_id"])
    if isinstance(ticket_channel, discord.TextChannel):
        notice = discord.ui.LayoutView(timeout=None)
        notice.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"{EMOJI['order_pending']} **Your order has been accepted and is pending.**"
                ),
                accent_colour=discord.Colour.blue(),
            )
        )
        await ticket_channel.send(view=notice)

    member = guild.get_member(order["customer_id"])
    if member is not None:
        await send_order_dm(
            guild, order,
            f"{EMOJI['order_accept']} **Your order has been accepted and is pending.**",
            discord.Colour.blue(),
        )


async def handle_done(interaction: discord.Interaction, order_id: int) -> None:
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        return await interaction.response.send_message("Only staff can complete orders.", ephemeral=True)

    order = await order_store.get(order_id)
    if order is None or order["status"] != "accepted":
        return await interaction.response.send_message("This order can't be marked done right now.", ephemeral=True)

    await order_store.update(order_id, status="completed")
    order = await order_store.get(order_id)
    guild = interaction.guild

    await interaction.response.send_message(f"{EMOJI['order_done']} Order marked as completed.", ephemeral=True)
    await refresh_order_panel(order, guild)
    await log_order_event(guild, order, "completed", interaction.user)

    member = guild.get_member(order["customer_id"])
    if member is not None:
        await send_order_dm(
            guild, order,
            f"{EMOJI['order_done']} **Your order has been completed.**",
            discord.Colour.green(),
        )


async def handle_cancel(interaction: discord.Interaction, order_id: int) -> None:
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        return await interaction.response.send_message("Only staff can cancel orders.", ephemeral=True)

    order = await order_store.get(order_id)
    if order is None or order["status"] in ("completed", "cancelled"):
        return await interaction.response.send_message("This order can't be cancelled.", ephemeral=True)

    await order_store.update(order_id, status="cancelled")
    order = await order_store.get(order_id)

    await interaction.response.send_message(f"{EMOJI['order_cancel']} Order cancelled.", ephemeral=True)
    await refresh_order_panel(order, interaction.guild)
    await log_order_event(interaction.guild, order, "cancelled", interaction.user)
    await send_order_dm(
        interaction.guild, order,
        f"{EMOJI['order_cancel']} **Your order has been cancelled.**",
        discord.Colour.red(),
    )


# --------------------------------------------------------------------------
# Cog
# --------------------------------------------------------------------------

class Orders(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="place-order", description="Start an order for an open ticket")
    async def place_order(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            return await interaction.response.send_message(
                "Only Developer, CEO or Co-CEO can use this.", ephemeral=True
            )

        tickets = [t for t in await store.list_all() if t["kind"] == "order"]
        await interaction.response.send_message(
            view=TicketPickerView(tickets, interaction.guild), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    for item_cls in (AcceptButton, DoneButton, OrderCancelButton):
        bot.add_dynamic_items(item_cls)
    await bot.add_cog(Orders(bot))
