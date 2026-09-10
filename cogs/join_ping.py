from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils import storage
from utils.permissions import slash_is_ownership_only

STORE_NAME = "join_ping"


class JoinPing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setchannel", description="Ορίζει το κανάλι για το ping όταν μπαίνει μέλος")
    @app_commands.describe(
        channel="Το κανάλι όπου θα γίνεται το tag του νέου μέλους",
        ping_role="Προαιρετικό ρόλος που θα κάνει tag",
    )
    @slash_is_ownership_only()
    async def setchannel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        ping_role: discord.Role | None = None,
    ):
        store = storage.get_store(STORE_NAME)
        store[str(interaction.guild_id)] = {
            "channel_id": channel.id,
            "ping_role_id": ping_role.id if ping_role else None,
        }
        storage.save(STORE_NAME, store)

        msg = f"Το join-ping ρυθμίστηκε: κανάλι {channel.mention}"
        if ping_role:
            msg += f", με tag του ρόλου {ping_role.mention}"
        await interaction.response.send_message(msg, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        store = storage.get_store(STORE_NAME)
        info = store.get(str(member.guild.id))
        if not info:
            return

        channel = member.guild.get_channel(info["channel_id"])
        if channel is None:
            return

        content = member.mention
        role_id = info.get("ping_role_id")
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                content += f" {role.mention}"

        try:
            sent = await channel.send(content)
            await sent.delete()
        except discord.Forbidden:
            pass

    @setchannel.error
    async def setchannel_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(" Δεν έχεις δικαίωμα να χρησιμοποιήσεις αυτή την εντολή.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinPing(bot))
