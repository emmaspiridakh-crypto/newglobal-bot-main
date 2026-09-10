from __future__ import annotations

import datetime as _dt

import discord
from discord import app_commands, ui
from discord.ext import commands

import config
from emojis import emoji
from utils import storage
from utils.components import build_base_container, add_separator, add_action_row, add_text
from utils.permissions import slash_is_staff_team

STORE_NAME = "reviews"

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


def _stars(rating: int) -> str:
    filled = emoji("reviews", "star_filled") or "⭐"
    empty = emoji("reviews", "star_empty") or "☆"
    return (filled * rating) + (empty * (5 - rating))


def _build_review_container(*, guild: discord.Guild, author: discord.abc.User, rating: int, comment: str, created_at: _dt.datetime) -> ui.Container:
    thumb = guild.icon.url if guild and guild.icon else None
    container = build_base_container(
        title=f"{emoji('reviews', 'review')} • Νέο Review",
        thumbnail_url=thumb,
    )
    add_separator(container)
    bullet = emoji("reviews", "bullet") or "»"
    add_text(container, (
        f"{emoji('reviews', 'user')} Από {author.mention}\n"
        f"{bullet} {_stars(rating)} ({rating}/5)"
    ))
    add_separator(container)
    add_text(container, f"{emoji('reviews', 'comment')} {comment}")
    add_separator(container)
    add_text(container, f"{emoji('reviews', 'date')} {_greek_date(created_at)}")
    return container


class ReviewCommentModal(ui.Modal, title="Σχόλιο Review"):
    comment = ui.TextInput(
        label="Το σχόλιό σου",
        style=discord.TextStyle.paragraph,
        placeholder="Γράψε εδώ την εμπειρία σου...",
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
        container = _build_review_container(
            guild=interaction.guild, author=interaction.user,
            rating=self.rating, comment=str(self.comment), created_at=created_at,
        )
        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        sent = await log_channel.send(view=view)

        store = storage.get_store(STORE_NAME)
        store[str(sent.id)] = {
            "author_id": interaction.user.id,
            "rating": self.rating,
            "comment": str(self.comment),
            "created_at": created_at.isoformat(),
        }
        storage.save(STORE_NAME, store)

        await interaction.response.send_message(
            f"{emoji('reviews', 'review') or '⭐'} Ευχαριστούμε για το review σου!", ephemeral=True
        )


class RatingSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=f"{i} από 5",
                value=str(i),
                emoji=emoji("reviews", "star_filled") or "⭐",
                description="Πόσο καλή ήταν η εμπειρία σου;" if i == 5 else None,
            )
            for i in range(5, 0, -1)
        ]
        super().__init__(placeholder="Επίλεξε βαθμολογία...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        rating = int(self.values[0])
        await interaction.response.send_modal(ReviewCommentModal(rating))


class RatingSelectView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(RatingSelect())


class ReviewPanelView(ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        container = build_base_container(
            title=f"{emoji('reviews', 'review')} Άφησε ένα Review",
            description="Πάτα το κουμπί από κάτω για να μοιραστείς την εμπειρία σου μαζί μας!",
            banner_url=config.REVIEWS_BANNER_URL or None,
        )
        add_separator(container)
        btn = ui.Button(
            label="Make a Review",
            style=discord.ButtonStyle.success,
            emoji=emoji("reviews", "make_review"),
            custom_id="review:open",
        )
        add_action_row(container, btn)
        self.add_item(container)


class Reviews(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(ReviewPanelView())

    @app_commands.command(name="panel-reviews", description="Στέλνει το panel για τα reviews")
    @slash_is_staff_team()
    async def panel_reviews(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(view=ReviewPanelView())
        await interaction.followup.send("Το review panel στάλθηκε.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        if interaction.data.get("custom_id") != "review:open":
            return
        await interaction.response.send_message(
            f"{emoji('reviews', 'review') or '⭐'} Επίλεξε βαθμολογία 1-5:",
            view=RatingSelectView(),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Reviews(bot))
