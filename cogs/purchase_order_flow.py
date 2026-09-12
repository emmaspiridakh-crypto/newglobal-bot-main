from __future__ import annotations

import discord

from emojis import EMOJI


# --------------------------------------------------------------------------
# Purchase flow: What bot? -> Lifetime/Monthly -> PayPal/Paysafe -> Check/Cancel
# --------------------------------------------------------------------------

class WhatBotModal(discord.ui.Modal, title="What bot do you want?"):
    bot_type = discord.ui.TextInput(
        label="Which bot are you interested in?",
        placeholder="e.g. Moderation bot, Roleplay bot, Security bot...",
        max_length=200,
    )

    def __init__(self, parent_view: "PurchaseSelectionView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        new_view = PurchaseSelectionView(
            self.bot_type.value, self.parent_view.plan, self.parent_view.payment
        )
        await interaction.response.edit_message(view=new_view)


class PurchaseSelectionView(discord.ui.LayoutView):
    def __init__(
        self,
        bot_type: str | None = None,
        plan: str | None = None,
        payment: str | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.bot_type = bot_type
        self.plan = plan
        self.payment = payment
        self._build()

    def _build(self) -> None:
        what_bot_btn = discord.ui.Button(
            label="Edit bot" if self.bot_type else "What bot?",
            style=discord.ButtonStyle.primary,
            emoji=EMOJI.get("bot", "🤖"),
        )
        what_bot_btn.callback = self.on_what_bot

        lifetime_btn = discord.ui.Button(
            label="Lifetime",
            style=discord.ButtonStyle.success if self.plan == "Lifetime" else discord.ButtonStyle.secondary,
            disabled=(self.plan == "Monthly"),
        )
        lifetime_btn.callback = self._plan_callback("Lifetime")

        monthly_btn = discord.ui.Button(
            label="Monthly",
            style=discord.ButtonStyle.success if self.plan == "Monthly" else discord.ButtonStyle.secondary,
            disabled=(self.plan == "Lifetime"),
        )
        monthly_btn.callback = self._plan_callback("Monthly")

        paypal_btn = discord.ui.Button(
            label="PayPal",
            style=discord.ButtonStyle.success if self.payment == "PayPal" else discord.ButtonStyle.secondary,
            disabled=(self.payment == "Paysafe"),
        )
        paypal_btn.callback = self._payment_callback("PayPal")

        paysafe_btn = discord.ui.Button(
            label="Paysafe",
            style=discord.ButtonStyle.success if self.payment == "Paysafe" else discord.ButtonStyle.secondary,
            disabled=(self.payment == "PayPal"),
        )
        paysafe_btn.callback = self._payment_callback("Paysafe")

        ready = bool(self.bot_type and self.plan and self.payment)
        check_btn = discord.ui.Button(
            label="Check", style=discord.ButtonStyle.success, emoji="✅", disabled=not ready
        )
        check_btn.callback = self.on_check

        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, emoji="🚫")
        cancel_btn.callback = self.on_cancel

        summary = (
            f"**Bot:** {self.bot_type or '*not set*'}\n"
            f"**Plan:** {self.plan or '*not set*'}\n"
            f"**Payment:** {self.payment or '*not set*'}"
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay("🛒 **Purchase a Bot**"),
            discord.ui.TextDisplay(summary),
            discord.ui.Separator(),
            discord.ui.ActionRow(what_bot_btn),
            discord.ui.ActionRow(lifetime_btn, monthly_btn),
            discord.ui.ActionRow(paypal_btn, paysafe_btn),
            discord.ui.ActionRow(check_btn, cancel_btn),
            accent_colour=discord.Colour.green(),
        )
        self.add_item(container)

    def _plan_callback(self, plan: str):
        async def callback(interaction: discord.Interaction) -> None:
            new_plan = None if self.plan == plan else plan
            await interaction.response.edit_message(
                view=PurchaseSelectionView(self.bot_type, new_plan, self.payment)
            )
        return callback

    def _payment_callback(self, payment: str):
        async def callback(interaction: discord.Interaction) -> None:
            new_payment = None if self.payment == payment else payment
            await interaction.response.edit_message(
                view=PurchaseSelectionView(self.bot_type, self.plan, new_payment)
            )
        return callback

    async def on_what_bot(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(WhatBotModal(self))

    async def on_check(self, interaction: discord.Interaction) -> None:
        from cogs.tickets import create_ticket_channel

        fields = {"bot_type": self.bot_type, "plan": self.plan, "payment_method": self.payment}
        await create_ticket_channel(interaction, kind="purchase", fields=fields)

    async def on_cancel(self, interaction: discord.Interaction) -> None:
        cancelled_view = discord.ui.LayoutView(timeout=None)
        cancelled_view.add_item(
            discord.ui.Container(discord.ui.TextDisplay("🚫 Cancelled."), accent_colour=discord.Colour.red())
        )
        await interaction.response.edit_message(view=cancelled_view)


# --------------------------------------------------------------------------
# Order flow: modal (server/description/budget) -> PayPal/Paysafe -> Send/Cancel
# --------------------------------------------------------------------------

class OrderInfoModal(discord.ui.Modal, title="Order a Custom Bot"):
    server = discord.ui.TextInput(
        label="Which server is this bot for?",
        placeholder="Server name and/or invite link",
        max_length=200,
    )
    description = discord.ui.TextInput(
        label="Describe what you want",
        style=discord.TextStyle.paragraph,
        placeholder="Features, style, anything specific you'd like...",
        max_length=1000,
    )
    budget = discord.ui.TextInput(
        label="What's your budget?",
        placeholder="e.g. $100",
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            view=OrderPaymentView(self.server.value, self.description.value, self.budget.value),
            ephemeral=True,
        )


class OrderPaymentView(discord.ui.LayoutView):
    def __init__(
        self, server: str, description: str, budget: str, payment: str | None = None
    ) -> None:
        super().__init__(timeout=300)
        self.server = server
        self.description = description
        self.budget = budget
        self.payment = payment
        self._build()

    def _build(self) -> None:
        paypal_btn = discord.ui.Button(
            label="PayPal",
            style=discord.ButtonStyle.success if self.payment == "PayPal" else discord.ButtonStyle.secondary,
            disabled=(self.payment == "Paysafe"),
        )
        paypal_btn.callback = self._payment_callback("PayPal")

        paysafe_btn = discord.ui.Button(
            label="Paysafe",
            style=discord.ButtonStyle.success if self.payment == "Paysafe" else discord.ButtonStyle.secondary,
            disabled=(self.payment == "PayPal"),
        )
        paysafe_btn.callback = self._payment_callback("Paysafe")

        ready = bool(self.payment)
        send_btn = discord.ui.Button(
            label="Send", style=discord.ButtonStyle.success, emoji="📨", disabled=not ready
        )
        send_btn.callback = self.on_send

        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, emoji="🚫")
        cancel_btn.callback = self.on_cancel

        summary = (
            f"**Server:** {self.server}\n"
            f"**Budget:** {self.budget}\n"
            f"**Payment:** {self.payment or '*not set*'}"
        )

        container = discord.ui.Container(
            discord.ui.TextDisplay("🎧 **Order a Custom Bot**"),
            discord.ui.TextDisplay(summary),
            discord.ui.TextDisplay(f"**Description:**\n{self.description}"),
            discord.ui.Separator(),
            discord.ui.ActionRow(paypal_btn, paysafe_btn),
            discord.ui.ActionRow(send_btn, cancel_btn),
            accent_colour=discord.Colour.blue(),
        )
        self.add_item(container)

    def _payment_callback(self, payment: str):
        async def callback(interaction: discord.Interaction) -> None:
            new_payment = None if self.payment == payment else payment
            await interaction.response.edit_message(
                view=OrderPaymentView(self.server, self.description, self.budget, new_payment)
            )
        return callback

    async def on_send(self, interaction: discord.Interaction) -> None:
        from cogs.tickets import create_ticket_channel

        fields = {
            "server": self.server,
            "description": self.description,
            "budget": self.budget,
            "payment_method": self.payment,
        }
        await create_ticket_channel(interaction, kind="order", fields=fields)

    async def on_cancel(self, interaction: discord.Interaction) -> None:
        cancelled_view = discord.ui.LayoutView(timeout=None)
        cancelled_view.add_item(
            discord.ui.Container(discord.ui.TextDisplay("🚫 Cancelled."), accent_colour=discord.Colour.red())
        )
        await interaction.response.edit_message(view=cancelled_view)


# --------------------------------------------------------------------------
# Entrypoints — called from the main ticket panel's Purchase / Order buttons
# --------------------------------------------------------------------------

async def start_purchase_flow(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(view=PurchaseSelectionView(), ephemeral=True)


async def start_order_flow(interaction: discord.Interaction) -> None:
    await interaction.response.send_modal(OrderInfoModal())
