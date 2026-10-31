from __future__ import annotations

import datetime as _dt
import os
import re

import discord
from discord import ui
from discord.ext import commands

import config
from emojis import emoji
from utils import storage

STORE_NAME = "suggestions"

# Banner image link comes from config.SUGGESTIONS_BANNER_URL (empty = no banner).
BANNER_URL = getattr(config, "https://i.imgur.com/dU42Vu3.jpeg")

ACCENT_COLOUR = 0x0088FF

LINK_RE = re.compile(r"(https?://|www\.|discord\.gg/|discord\.com/invite/)", re.IGNORECASE)

ENGLISH_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
ENGLISH_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _greek_date(dt: _dt.datetime) -> str:
    day_name = ENGLISH_DAYS[dt.weekday()]
    hour12 = dt.hour % 12 or 12
    period = "am" if dt.hour < 12 else "pm"
    return f"{day_name}, {dt.day} {ENGLISH_MONTHS[dt.month]} {dt.year} {hour12:02d}:{dt.minute:02d} {period}"


class Suggestions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_view(
        self, *, author: discord.Member, text: str, upvotes: int, downvotes: int,
        msg_id: int, created_at: _dt.datetime,
    ) -> ui.LayoutView:
        small = discord.SeparatorSpacing.small
        large = discord.SeparatorSpacing.large
        author_text = author.mention if author else "Unknown"

        children: list[ui.Item] = [ui.Separator(visible=True, spacing=small)]
        if BANNER_URL:
            children.append(ui.MediaGallery(discord.MediaGalleryItem(BANNER_URL)))
            children.append(ui.Separator(visible=True, spacing=small))

        children += [
            ui.TextDisplay(
                f"> {emoji('suggestions', 'submitted')}〃 __**Submitted From:**__ {author_text}\n"
                f"> {emoji('suggestions', 'time')} 〃 __**Time:**__ {_greek_date(created_at)}"
            ),
            ui.Separator(visible=True, spacing=large),
            ui.TextDisplay(text),
            ui.Separator(visible=True, spacing=small),
            ui.ActionRow(
                ui.Button(label=f"〃 {upvotes}", style=discord.ButtonStyle.secondary,
                          emoji=emoji("suggestions", "upvote") or None,
                          custom_id=f"suggestion_up:{msg_id}"),
                ui.Button(label=f"〃 {downvotes}", style=discord.ButtonStyle.secondary,
                          emoji=emoji("suggestions", "downvote") or None,
                          custom_id=f"suggestion_down:{msg_id}"),
                ui.Button(label="〃 Remove Vote", style=discord.ButtonStyle.secondary,
                          emoji=emoji("suggestions", "remove") or None,
                          custom_id=f"suggestion_removevote:{msg_id}"),
                ui.Button(label="〃 Total Suggestions", style=discord.ButtonStyle.secondary,
                          emoji=emoji("suggestions", "total") or None,
                          custom_id=f"suggestion_total:{msg_id}"),
            ),
            ui.Separator(visible=True, spacing=small),
            ui.TextDisplay(
                f"> -#  **{emoji('suggestions', 'footer_left')} 〃 GlobalBots, All Rights Reserved "
                f"{emoji('suggestions', 'bullet')} Suggestion System** "
            ),
            ui.Separator(visible=True, spacing=small),
        ]

        view = ui.LayoutView(timeout=None)
        view.add_item(ui.Container(*children, accent_colour=ACCENT_COLOUR))
        return view

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != config.SUGGESTIONS_CHANNEL_ID:
            return

        content = message.content.strip()
        author = message.author

        has_mentions = bool(message.mentions) or bool(message.role_mentions) or message.mention_everyone
        has_link = bool(LINK_RE.search(content))

        if has_mentions or has_link:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

            reason = "tags" if has_mentions and not has_link else "links" if has_link and not has_mentions else "tags ή links"
            try:
                warning = await message.channel.send(
                    f"{emoji('suggestions', 'suggestion') or '⚠️'} {author.mention} No links or tags **{reason}** inside the suggestions."
                )
                await warning.delete(delay=6)
            except discord.HTTPException:
                pass
            return

        created_at = discord.utils.utcnow()

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        temp_view = self._build_view(author=author, text=content, upvotes=0, downvotes=0, msg_id=0, created_at=created_at)
        sent = await message.channel.send(view=temp_view)

        store = storage.get_store(STORE_NAME)
        store[str(sent.id)] = {
            "author_id": author.id, "text": content, "upvotes": [], "downvotes": [],
            "created_at": created_at.isoformat(),
        }
        storage.save(STORE_NAME, store)

        real_view = self._build_view(author=author, text=content, upvotes=0, downvotes=0, msg_id=sent.id, created_at=created_at)
        await sent.edit(view=real_view)

    async def _handle_vote(self, interaction: discord.Interaction, msg_id: int, upvote: bool | None):
        """upvote=True -> upvote toggle, False -> downvote toggle, None -> remove vote entirely."""
        store = storage.get_store(STORE_NAME)
        info = store.get(str(msg_id))
        if not info:
            await interaction.response.send_message("Can't find this suggestion.", ephemeral=True)
            return

        uid = interaction.user.id
        ups, downs = set(info["upvotes"]), set(info["downvotes"])

        if upvote is None:
            ups.discard(uid)
            downs.discard(uid)
        elif upvote:
            if uid in ups:
                ups.discard(uid)
            else:
                ups.add(uid)
                downs.discard(uid)
        else:
            if uid in downs:
                downs.discard(uid)
            else:
                downs.add(uid)
                ups.discard(uid)

        info["upvotes"], info["downvotes"] = list(ups), list(downs)
        store[str(msg_id)] = info
        storage.save(STORE_NAME, store)

        author = interaction.guild.get_member(info["author_id"])
        created_at = _dt.datetime.fromisoformat(info["created_at"]) if isinstance(info.get("created_at"), str) else discord.utils.utcnow()
        new_view = self._build_view(
            author=author or interaction.user, text=info["text"],
            upvotes=len(ups), downvotes=len(downs), msg_id=msg_id, created_at=created_at,
        )
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=new_view)
            else:
                await interaction.response.edit_message(view=new_view)
        except discord.HTTPException:
            pass

    def _forget(self, message_ids) -> None:
        store = storage.get_store(STORE_NAME)
        removed = False
        for mid in message_ids:
            if store.pop(str(mid), None) is not None:
                removed = True
        if removed:
            storage.save(STORE_NAME, store)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.channel_id == config.SUGGESTIONS_CHANNEL_ID:
            self._forget([payload.message_id])

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if payload.channel_id == config.SUGGESTIONS_CHANNEL_ID:
            self._forget(payload.message_ids)

    async def _handle_total(self, interaction: discord.Interaction):
        total = len(storage.get_store(STORE_NAME))
        await interaction.response.send_message(
            f"{emoji('suggestions', 'total')} Total **{total}** suggestions.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("suggestion_up:"):
            await self._handle_vote(interaction, int(custom_id.split(":")[1]), upvote=True)
        elif custom_id.startswith("suggestion_down:"):
            await self._handle_vote(interaction, int(custom_id.split(":")[1]), upvote=False)
        elif custom_id.startswith("suggestion_removevote:"):
            await self._handle_vote(interaction, int(custom_id.split(":")[1]), upvote=None)
        elif custom_id.startswith("suggestion_total:"):
            await self._handle_total(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
