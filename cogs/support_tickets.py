from __future__ import annotations

import discord
from cogs.tickets import create_ticket_channel

CATEGORY_LABELS = {
    "owner": "Contact Owner",
    "manager": "Talk to Managemet Team",
    "general": "General Support",
    "technical": "Technical Issue",
    "billing": "Billing Issue",
    "replacement": "Replacement",
}


class ProblemModal(discord.ui.Modal):
    """Shown after a category button is pressed — the customer writes their
    problem here, and 'Send' (the modal's submit button) opens the ticket."""

    description = discord.ui.TextInput(
        label="Describe your problem",
        style=discord.TextStyle.paragraph,
        placeholder="Please give as much detail as you can...",
        max_length=1000,
    )

    def __init__(self, kind: str):
        super().__init__(title=CATEGORY_LABELS[kind])
        self.kind = kind

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await create_ticket_channel(
            interaction, kind=self.kind, fields={"description": self.description.value}
        )
