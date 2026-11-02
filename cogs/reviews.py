from __future__ import annotations

import asyncio
import datetime as _dt
import logging

import discord
from discord import app_commands, ui
from discord.ext import commands

import config
from emojis import emoji
from utils import storage
from utils.components import build_base_container, add_separator, add_action_row, add_text
from utils.permissions import slash_is_staff_team

log = logging.getLogger(__name__)

LEGACY_REVIEWS_STORE = "reviews"          # old JSON stores, imported once into Turso
LEGACY_PANELS_STORE = "review_panels"

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS reviews (
        message_id INTEGER PRIMARY KEY,
        author_id INTEGER NOT NULL,
        rating INTEGER NOT NULL,
        comment TEXT NOT NULL,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_votes (
        message_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        choice TEXT NOT NULL,
        PRIMARY KEY (message_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_panels (
        message_id INTEGER PRIMARY KEY,
        channel_id INTEGER NOT NULL
    )
    """,
]


class ReviewStore:
    """Turso-backed storage for reviews, votes and review panels. Uses the
    same libsql client as the ticket store (initialised in bot.py)."""

    @property
    def _client(self):
        return storage.store._client

    async def init(self) -> None:
        for statement in _SCHEMA:
            await self._client.execute(statement)
        await self._migrate_legacy_json()

    async def _migrate_legacy_json(self) -> None:
        """One-time import of the old data/stores/*.json files."""
        reviews_path = storage._store_path(LEGACY_REVIEWS_STORE)
        if reviews_path.exists():
            legacy = storage.get_store(LEGACY_REVIEWS_STORE)
            for mid, rec in legacy.items():
                if not str(mid).isdigit() or not isinstance(rec, dict) or not rec.get("rating"):
                    continue
                await self._client.execute(
                    "INSERT OR IGNORE INTO reviews (message_id, author_id, rating, comment, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [int(mid), int(rec.get("author_id", 0)), int(rec["rating"]),
                     rec.get("comment", ""), rec.get("created_at")],
                )
                for uid, choice in (rec.get("votes") or {}).items():
                    await self._client.execute(
                        "INSERT OR IGNORE INTO review_votes (message_id, user_id, choice) VALUES (?, ?, ?)",
                        [int(mid), int(uid), choice],
                    )
            reviews_path.replace(reviews_path.with_suffix(".json.migrated"))

        panels_path = storage._store_path(LEGACY_PANELS_STORE)
        if panels_path.exists():
            for mid, cid in storage.get_store(LEGACY_PANELS_STORE).items():
                await self._client.execute(
                    "INSERT OR IGNORE INTO review_panels (message_id, channel_id) VALUES (?, ?)",
                    [int(mid), int(cid)],
                )
            panels_path.replace(panels_path.with_suffix(".json.migrated"))

    # ---- reviews ----
    async def add_review(self, message_id: int, author_id: int, rating: int, comment: str, created_at: str) -> None:
        await self._client.execute(
            "INSERT OR REPLACE INTO reviews (message_id, author_id, rating, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [message_id, author_id, rating, comment, created_at],
        )

    async def stats(self) -> tuple[int, int]:
        """(number of reviews, sum of all ratings)."""
        result = await self._client.execute("SELECT COUNT(*), COALESCE(SUM(rating), 0) FROM reviews")
        row = result.rows[0]
        return int(row[0]), int(row[1])

    async def get_review(self, message_id: int) -> dict | None:
        result = await self._client.execute(
            "SELECT author_id, rating, comment FROM reviews WHERE message_id = ?", [message_id]
        )
        if not result.rows:
            return None
        author_id, rating, comment = result.rows[0]
        votes = await self._client.execute(
            "SELECT choice, COUNT(*) FROM review_votes WHERE message_id = ? GROUP BY choice", [message_id]
        )
        counts = {row[0]: int(row[1]) for row in votes.rows}
        return {
            "author_id": author_id, "rating": rating, "comment": comment,
            "yes": counts.get("yes", 0), "no": counts.get("no", 0),
        }

    async def list_ids(self) -> list[int]:
        result = await self._client.execute("SELECT message_id FROM reviews")
        return [int(row[0]) for row in result.rows]

    async def delete_reviews(self, message_ids) -> bool:
        removed = False
        for mid in message_ids:
            result = await self._client.execute("DELETE FROM reviews WHERE message_id = ?", [int(mid)])
            if result.rows_affected:
                removed = True
                await self._client.execute("DELETE FROM review_votes WHERE message_id = ?", [int(mid)])
        return removed

    async def vote(self, message_id: int, user_id: int, choice: str) -> bool:
        """Records the vote. A user has one vote per review, but can switch
        it. Returns False if they pressed the same choice they already have."""
        result = await self._client.execute(
            "INSERT INTO review_votes (message_id, user_id, choice) VALUES (?, ?, ?) "
            "ON CONFLICT(message_id, user_id) DO UPDATE SET choice = excluded.choice "
            "WHERE review_votes.choice != excluded.choice",
            [message_id, user_id, choice],
        )
        return bool(result.rows_affected)

    # ---- panels ----
    async def add_panel(self, message_id: int, channel_id: int) -> None:
        await self._client.execute(
            "INSERT OR REPLACE INTO review_panels (message_id, channel_id) VALUES (?, ?)",
            [message_id, channel_id],
        )

    async def list_panels(self) -> list[tuple[int, int]]:
        result = await self._client.execute("SELECT message_id, channel_id FROM review_panels")
        return [(int(r[0]), int(r[1])) for r in result.rows]

    async def delete_panels(self, message_ids) -> None:
        for mid in message_ids:
            await self._client.execute("DELETE FROM review_panels WHERE message_id = ?", [int(mid)])


reviews_db = ReviewStore()


def _average(count: int, rating_sum: int) -> float:
    return rating_sum / count if count else 0.0


ENGLISH_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
ENGLISH_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _format_date(dt: _dt.datetime) -> str:
    day_name = ENGLISH_DAYS[dt.weekday()]
    hour12 = dt.hour % 12 or 12
    period = "am" if dt.hour < 12 else "pm"
    return f"{day_name}, {dt.day} {ENGLISH_MONTHS[dt.month]} {dt.year} {hour12:02d}:{dt.minute:02d} {period}"


def _stars(rating: int) -> str:
    filled = emoji("reviews", "star_filled") or "⭐"
    empty = emoji("reviews", "star_empty")
    if not any(c.isdigit() for c in empty):  # unset/invalid custom emoji -> plain star
        empty = "☆"
    return (filled * rating) + (empty * (5 - rating))


def _build_review_view(record: dict, total_reviews: int, average_rating: float) -> ui.LayoutView:
    """Builds the review message that is posted in the reviews log channel."""
    sep = lambda spacing=discord.SeparatorSpacing.small: ui.Separator(visible=True, spacing=spacing)
    rating = int(record["rating"])
    yes, no = record.get("yes", 0), record.get("no", 0)
    banner = getattr(config, "REVIEWS_LOG_BANNER_URL", None) or config.REVIEWS_BANNER_URL

    children: list[ui.Item] = [sep()]
    if banner:
        children += [ui.MediaGallery(discord.MediaGalleryItem(media=banner)), sep()]
    children += [
        ui.TextDisplay(
            f"> <:name:1566133385254928504> 〃 __**Submitted From:**__ <@{record['author_id']}>\n"
            f"> <:name:1566447157165166714> 〃 **__Rating:__** {_stars(rating)} ({rating}/5)"
        ),
        sep(discord.SeparatorSpacing.large),
        ui.TextDisplay(record["comment"]),
        sep(),
        ui.ActionRow(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"〃 Total Reviews: {total_reviews}",
                emoji=discord.PartialEmoji(name="name", id=1545579981030162432),
                custom_id="review:log_total_reviews",
                disabled=True,
            ),
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"〃 Total Rating: {average_rating:.1f}/5",
                emoji=discord.PartialEmoji(name="name", id=1566447157165166714),
                custom_id="review:log_total_rating",
                disabled=True,
            ),
        ),
        sep(),
        ui.TextDisplay("### <:name:1566128213858459848>***__Feedback__*** "),
        ui.TextDisplay("> Did you find this review useful? "),
        ui.ActionRow(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"〃 Yes: {yes}",
                emoji=discord.PartialEmoji(name="name", id=1544994894370578474),
                custom_id="review:vote_yes",
            ),
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"〃 No: {no}",
                emoji=discord.PartialEmoji(name="name", id=1544994871369273424),
                custom_id="review:vote_no",
            ),
        ),
        sep(),
        ui.TextDisplay(
            "> -# <:name:1545831836339409048> 〃 **GlobalBots, All Rights Reserved** "
            "<:name:1545576267904974859> **Review System **"
        ),
        sep(),
    ]
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*children, accent_colour=0x006AFF))
    return view


class ReviewCommentModal(ui.Modal, title="Review Commend"):
    comment = ui.TextInput(
        label="Review Commend",
        style=discord.TextStyle.paragraph,
        placeholder="Tell us your experience...",
        required=True,
        max_length=1000,
    )

    def __init__(self, rating: int):
        super().__init__()
        self.rating = rating

    async def on_submit(self, interaction: discord.Interaction):
        log_channel = interaction.guild.get_channel(config.REVIEWS_LOG_CHANNEL_ID)
        if log_channel is None:
            await interaction.response.send_message(
                "Δεν βρέθηκε το channel για τα reviews. Ενημέρωσε ένα staff μέλος.", ephemeral=True
            )
            return

        created_at = discord.utils.utcnow()
        record = {
            "author_id": interaction.user.id,
            "rating": self.rating,
            "comment": str(self.comment),
            "yes": 0,
            "no": 0,
        }

        # Totals as they will be once this review is counted.
        count, rating_sum = await reviews_db.stats()
        count, rating_sum = count + 1, rating_sum + self.rating

        sent = await log_channel.send(view=_build_review_view(record, count, _average(count, rating_sum)))
        await reviews_db.add_review(
            sent.id, interaction.user.id, self.rating, str(self.comment), created_at.isoformat()
        )

        await interaction.response.send_message(
            f"{emoji('reviews', 'review') or '⭐'} 〃 Thank you for your review!", ephemeral=True
        )

        cog = interaction.client.get_cog("Reviews")
        if cog is not None:
            cog.request_refresh()


class RatingSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=f"{i} in 5",
                value=str(i),
                emoji=emoji("reviews", "star_filled") or "⭐",
                description="Tell us about your experience with our services" if i == 5 else None,
            )
            for i in range(5, 0, -1)
        ]
        super().__init__(placeholder="Choose a rating...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        rating = int(self.values[0])
        await interaction.response.send_modal(ReviewCommentModal(rating))


class RatingSelectView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(RatingSelect())


class ReviewPanelView(ui.LayoutView):
    def __init__(self, total_reviews: int = 0, average_rating: float = 0.0):
        super().__init__(timeout=None)

        sep = lambda: ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
        children: list[ui.Item] = [sep()]
        if config.REVIEWS_BANNER_URL:
            children.append(ui.MediaGallery(discord.MediaGalleryItem(media=config.REVIEWS_BANNER_URL)))
            children.append(sep())
        children += [
            ui.TextDisplay("## <:name:1566447157165166714> 〃 __**GlobalBots - Reviews**__"),
            sep(),
            ui.TextDisplay(
                "> - <a:name:1545552914334875800> Leave a review to tell us about your "
                "experience with us and what we can improve."
            ),
            sep(),
            ui.ActionRow(
                ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="〃 Review Us",
                    emoji=discord.PartialEmoji(name="name", id=1566447157165166714),
                    custom_id="review:open",
                ),
                ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=f"〃 Total Reviews: {total_reviews}",
                    emoji=discord.PartialEmoji(name="name", id=1545579981030162432),
                    custom_id="review:total_reviews",
                    disabled=True,
                ),
                ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=f"〃 Total Rating: {average_rating:.1f}/5",
                    emoji=discord.PartialEmoji(name="name", id=1545578059820826745),
                    custom_id="review:total_rating",
                    disabled=True,
                ),
            ),
            sep(),
            ui.TextDisplay(
                "> -#  <:name:1545831836339409048> 〃 **GlobalBots, All Rights Reserved "
                "<:name:1545576267904974859> Review System**"
            ),
            sep(),
        ]
        self.add_item(ui.Container(*children, accent_colour=0x006EFF))


class Reviews(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(ReviewPanelView())
        self._refresh_pending = False
        self._refresh_task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        await reviews_db.init()

    # ---- refresh -------------------------------------------------------

    async def refresh_panels(self) -> None:
        """Re-renders every stored review panel with the current totals."""
        panels = await reviews_db.list_panels()
        if not panels:
            return
        count, rating_sum = await reviews_db.stats()
        average = _average(count, rating_sum)
        gone = []
        for message_id, channel_id in panels:
            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                message = await channel.fetch_message(message_id)
                await message.edit(view=ReviewPanelView(count, average))
            except (discord.NotFound, discord.Forbidden):
                gone.append(message_id)  # panel (or its channel) is gone
            except discord.HTTPException:
                continue
        if gone:
            await reviews_db.delete_panels(gone)

    async def refresh_reviews(self) -> None:
        """Re-renders every review message in the log channel (totals + votes)."""
        channel = self.bot.get_channel(config.REVIEWS_LOG_CHANNEL_ID)
        if channel is None:
            return
        for message_id in await reviews_db.list_ids():
            record = await reviews_db.get_review(message_id)  # fresh votes each time
            if record is None:
                continue
            count, rating_sum = await reviews_db.stats()
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(view=_build_review_view(record, count, _average(count, rating_sum)))
            except discord.NotFound:
                # Message was deleted while the bot was offline.
                await reviews_db.delete_reviews([message_id])
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.5)  # stay well under the edit rate limit

    def request_refresh(self) -> None:
        """Schedules a refresh of the panels and every review message.
        Requests made while one is running are merged into one rerun."""
        self._refresh_pending = True
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def _refresh_loop(self) -> None:
        while self._refresh_pending:
            self._refresh_pending = False
            try:
                await self.refresh_panels()
                await self.refresh_reviews()
            except Exception:
                log.exception("Failed to refresh review panels/messages")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.refresh_panels()

    # ---- keep totals in sync when a review message is deleted ----------

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        await reviews_db.delete_panels([payload.message_id])
        if await reviews_db.delete_reviews([payload.message_id]):
            self.request_refresh()

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        await reviews_db.delete_panels(payload.message_ids)
        if await reviews_db.delete_reviews(payload.message_ids):
            self.request_refresh()

    # ---- commands / interactions ---------------------------------------

    @app_commands.command(name="panel-reviews", description="Στέλνει το panel για τα reviews")
    @slash_is_staff_team()
    async def panel_reviews(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count, rating_sum = await reviews_db.stats()
        sent = await interaction.channel.send(view=ReviewPanelView(count, _average(count, rating_sum)))
        await reviews_db.add_panel(sent.id, interaction.channel.id)
        await interaction.followup.send("Το review panel στάλθηκε.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id")

        if custom_id == "review:open":
            await interaction.response.send_message(
                f"{emoji('reviews', 'review') or '⭐'} 〃 Choose a star rating between 1-5",
                view=RatingSelectView(),
                ephemeral=True,
            )
            return

        if custom_id in ("review:vote_yes", "review:vote_no"):
            await self._handle_vote(interaction, "yes" if custom_id == "review:vote_yes" else "no")

    async def _handle_vote(self, interaction: discord.Interaction, choice: str) -> None:
        message_id = interaction.message.id
        if await reviews_db.get_review(message_id) is None:
            await interaction.response.send_message("This review could not be found.", ephemeral=True)
            return

        if not await reviews_db.vote(message_id, interaction.user.id, choice):
            await interaction.response.send_message(
                f"You already voted **{choice.title()}** on this review.", ephemeral=True
            )
            return

        record = await reviews_db.get_review(message_id)
        count, rating_sum = await reviews_db.stats()
        await interaction.response.edit_message(
            view=_build_review_view(record, count, _average(count, rating_sum))
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Reviews(bot))
