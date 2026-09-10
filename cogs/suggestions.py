from __future__ import annotations

import datetime as _dt
import re

import discord
from discord import ui
from discord.ext import commands

import config
from emojis import emoji
from utils import storage
from utils.components import build_base_container, add_separator, add_action_row, add_text

STORE_NAME = "suggestions"  

LINK_RE = re.compile(r"(https?://|www\.|discord\.gg/|discord\.com/invite/)", re.IGNORECASE)

GREEK_DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
GREEK_MONTHS = [
    "", "Ιανουαρίου", "Φεβρουαρίου", "Μαρτίου", "Απριλίου", "Μαΐου", "Ιουνίου",
    "Ιουλίου", "Αυγούστου", "Σεπτεμβρίου", "Οκτωβρίου", "Νοεμβρίου", "Δεκεμβρίου",
]


def _greek_date(dt: _dt.datetime) -> str:
    day_name = GREEK_DAYS[dt.weekday()]
    hour12 = dt.hour % 12 or 12
    period = "πμ" if dt.hour < 12 else "μμ"
    return f"{day_name}, {dt.day} {GREEK_MONTHS[dt.month]} {dt.year} {hour12:02d}:{dt.minute:02d} {period}"


class Suggestions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_view(
        self, *, author: discord.Member, text: str, upvotes: int, downvotes: int,
        msg_id: int, created_at: _dt.datetime,
    ) -> ui.LayoutView:
        thumb = author.display_avatar.url if author else None
        container = build_base_container(
            title=f"{emoji('suggestions', 'suggestion')} • New Suggestion",
            thumbnail_url=thumb,
        )
        add_separator(container)
        bullet = emoji("suggestions", "bullet") or "»"
        add_text(container, (
            f"{emoji('suggestions', 'submitted')} Submitted From {author.mention if author else 'Άγνωστος'}\n"
            f"{bullet} {_greek_date(created_at)}"
        ))
        add_separator(container)
        add_text(container, text)
        add_separator(container)
        up_btn = ui.Button(label=str(upvotes), style=discord.ButtonStyle.success,
                            emoji=emoji("suggestions", "upvote"), custom_id=f"suggestion_up:{msg_id}")
        down_btn = ui.Button(label=str(downvotes), style=discord.ButtonStyle.danger,
                              emoji=emoji("suggestions", "downvote"), custom_id=f"suggestion_down:{msg_id}")
        remove_btn = ui.Button(label="Remove Vote", style=discord.ButtonStyle.secondary,
                                custom_id=f"suggestion_removevote:{msg_id}")
        add_action_row(container, up_btn, down_btn, remove_btn)

        view = ui.LayoutView(timeout=None)
        view.add_item(container)
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
            except discord.Forbidden:
                pass

            reason = "tags" if has_mentions and not has_link else "links" if has_link and not has_mentions else "tags ή links"
            try:
                warning = await message.channel.send(
                    f"{emoji('suggestions', 'suggestion') or '⚠️'} {author.mention} δεν επιτρέπονται **{reason}** μέσα στα suggestions."
                )
                await warning.delete(delay=6)
            except discord.HTTPException:
                pass
            return

        created_at = discord.utils.utcnow()

        try:
            await message.delete()
        except discord.Forbidden:
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
            await interaction.response.send_message("Δεν βρέθηκε αυτό το suggestion.", ephemeral=True)
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
