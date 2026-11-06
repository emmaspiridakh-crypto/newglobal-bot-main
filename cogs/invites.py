"""
GlobalBots invite tracking + panel.

* Tracks who invited every new member (by diffing invite use-counts).
* Counts how many of those members later left.
* /panel-invites posts a panel with two buttons:
    - My Invites   -> your Joins / Left / Remaining (ephemeral)
    - Leaderboard  -> top 10 by TOTAL joins (ephemeral)
* /invites [member] shows the same stats card for you or another member.

Data lives in Turso (same client as tickets/orders) so it survives Render
redeploys. The bot needs the "Manage Server" permission to read invites.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import discord
from discord import app_commands, ui
from discord.ext import commands

import config
from emojis import emoji
from utils.permissions import slash_is_ownership_only
from utils.storage import store

SMALL = discord.SeparatorSpacing.small
INVITES_ACCENT = 0x0091FF


def _e(key: str, fallback: str = "") -> str:
    """Custom emoji from emojis.py (INVITES), unicode fallback if unset."""
    return emoji("invites", key) or fallback


def _medal(rank: int) -> str:
    return {1: _e("first", "🥇"), 2: _e("second", "🥈"), 3: _e("third", "🥉")}.get(rank, f"`#{rank}`")

_CREATE_STATS = """
CREATE TABLE IF NOT EXISTS invite_stats (
    guild_id INTEGER NOT NULL,
    inviter_id INTEGER NOT NULL,
    joins INTEGER NOT NULL DEFAULT 0,
    left INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, inviter_id)
);
"""

_CREATE_MEMBERS = """
CREATE TABLE IF NOT EXISTS invite_members (
    guild_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    inviter_id INTEGER NOT NULL,
    left INTEGER NOT NULL DEFAULT 0,
    joined_at TEXT,
    PRIMARY KEY (guild_id, member_id)
);
"""


# ---------------------------------------------------------------- database
async def _db():
    return store._client


async def record_join(guild_id: int, member_id: int, inviter_id: int) -> None:
    """inviter_id 0 = unknown (vanity URL / invite already deleted)."""
    db = await _db()
    await db.execute(
        """
        INSERT INTO invite_members (guild_id, member_id, inviter_id, left, joined_at)
        VALUES (?, ?, ?, 0, ?)
        ON CONFLICT(guild_id, member_id)
        DO UPDATE SET inviter_id = excluded.inviter_id, left = 0, joined_at = excluded.joined_at
        """,
        [guild_id, member_id, inviter_id, dt.datetime.now(dt.timezone.utc).isoformat()],
    )
    if inviter_id:
        await db.execute(
            """
            INSERT INTO invite_stats (guild_id, inviter_id, joins, left)
            VALUES (?, ?, 1, 0)
            ON CONFLICT(guild_id, inviter_id) DO UPDATE SET joins = joins + 1
            """,
            [guild_id, inviter_id],
        )


async def record_leave(guild_id: int, member_id: int) -> int | None:
    """Returns the inviter id (0 = unknown) if this leave was tracked, else None."""
    db = await _db()
    result = await db.execute(
        "SELECT inviter_id, left FROM invite_members WHERE guild_id = ? AND member_id = ?",
        [guild_id, member_id],
    )
    if not result.rows:
        return None
    inviter_id, already_left = int(result.rows[0][0]), result.rows[0][1]
    if already_left:
        return None
    await db.execute(
        "UPDATE invite_members SET left = 1 WHERE guild_id = ? AND member_id = ?",
        [guild_id, member_id],
    )
    if inviter_id:
        await db.execute(
            "UPDATE invite_stats SET left = left + 1 WHERE guild_id = ? AND inviter_id = ?",
            [guild_id, inviter_id],
        )
    return inviter_id


async def get_stats(guild_id: int, user_id: int) -> tuple[int, int]:
    db = await _db()
    result = await db.execute(
        "SELECT joins, left FROM invite_stats WHERE guild_id = ? AND inviter_id = ?",
        [guild_id, user_id],
    )
    if not result.rows:
        return 0, 0
    return int(result.rows[0][0]), int(result.rows[0][1])


async def get_rank(guild_id: int, user_id: int, joins: int) -> int | None:
    if joins <= 0:
        return None
    db = await _db()
    result = await db.execute(
        "SELECT COUNT(*) FROM invite_stats WHERE guild_id = ? AND joins > ?",
        [guild_id, joins],
    )
    return int(result.rows[0][0]) + 1


async def get_top(guild_id: int, limit: int = 10) -> list[tuple[int, int, int]]:
    db = await _db()
    result = await db.execute(
        "SELECT inviter_id, joins, left FROM invite_stats "
        "WHERE guild_id = ? AND joins > 0 ORDER BY joins DESC, left ASC LIMIT ?",
        [guild_id, limit],
    )
    return [(int(r[0]), int(r[1]), int(r[2])) for r in result.rows]


# ------------------------------------------------------------------- views
def _banner_children() -> list:
    banner = getattr(config, "INVITES_BANNER_URL", None)
    if not banner:
        return []
    return [ui.MediaGallery(discord.MediaGalleryItem(banner)), ui.Separator(visible=True, spacing=SMALL)]


def build_panel_view() -> ui.LayoutView:
    children: list = [ui.Separator(visible=True, spacing=SMALL), *_banner_children()]
    children += [
        ui.TextDisplay(f"## {_e('title', '📨')} 〃 __**GlobalBots - Invites**__"),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay(
            f"> - {_e('panel_info', 'ℹ️')} Invite your friends to **GlobalBots** and climb the leaderboard!\n"
            f"> - {_e('panel_info', 'ℹ️')} Press **My Invites** to see how many people you invited and how many of them left.\n"
            f"> - {_e('panel_info', 'ℹ️')} Press **Leaderboard** to see who has the most invites."
        ),
        ui.Separator(visible=True, spacing=SMALL),
        ui.ActionRow(
            ui.Button(style=discord.ButtonStyle.primary, label="My Invites", emoji=_e("my_invites", "📨"), custom_id="invites:me"),
            ui.Button(style=discord.ButtonStyle.secondary, label="Leaderboard", emoji=_e("leaderboard", "🏆"), custom_id="invites:top"),
        ),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay(f"-# {_e('footer')} 〃 **GlobalBots, All Rights Reserved {_e('bullet', '•')} Invites**"),
    ]
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*children, accent_colour=INVITES_ACCENT))
    return view


async def build_stats_view(guild: discord.Guild, member: discord.abc.User) -> ui.LayoutView:
    joins, left = await get_stats(guild.id, member.id)
    remaining = joins - left
    rank = await get_rank(guild.id, member.id, joins)
    rank_text = f"#{rank}" if rank else "—"
    children = [
        ui.TextDisplay(f"## {_e('title', '📨')} 〃 __**Invites of {member.display_name}**__"),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay(
            f"> {_e('joins', '📥')} **Total joins:** `{joins}`\n"
            f"> {_e('left', '📤')} **Left:** `{left}`\n"
            f"> {_e('remaining', '✅')} **Still in the server:** `{remaining}`\n"
            f"> {_e('rank', '🏆')} **Leaderboard rank:** `{rank_text}`"
        ),
    ]
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*children, accent_colour=INVITES_ACCENT))
    return view


async def build_leaderboard_view(guild: discord.Guild) -> ui.LayoutView:
    top = await get_top(guild.id, 10)
    if top:
        lines = []
        for i, (uid, joins, left) in enumerate(top, start=1):
            prefix = _medal(i)
            lines.append(f"{prefix} <@{uid}> — **{joins}** joins • {left} left • {joins - left} still here")
        body = "\n".join(lines)
    else:
        body = "*Nobody has invited anyone yet. Be the first!*"
    children = [
        ui.TextDisplay(f"## {_e('leaderboard', '🏆')} 〃 __**Invites Leaderboard**__"),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay(body),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay(f"-# {_e('bullet', '•')} Ranked by total joins."),
    ]
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*children, accent_colour=INVITES_ACCENT))
    return view


def build_log_view(member: discord.Member, inviter_id: int, *, joined: bool, stats: tuple[int, int] | None) -> ui.LayoutView:
    if joined:
        title = f"{_e('log_join', '📥')} 〃 __**Member Joined**__"
        colour = 0x2ECC71
    else:
        title = f"{_e('log_leave', '📤')} 〃 __**Member Left**__"
        colour = 0xE74C3C
    inviter_text = f"<@{inviter_id}> (`{inviter_id}`)" if inviter_id else "*Unknown (vanity URL / deleted invite)*"
    lines = [
        f"> {_e('user', '👤')} **Member:** {member.mention} (`{member.id}`)",
        f"> {_e('inviter', '📨')} **Invited by:** {inviter_text}",
    ]
    if stats is not None:
        joins, left = stats
        lines.append(
            f"> {_e('joins', '📥')} **Inviter totals:** `{joins}` joins • `{left}` left • `{joins - left}` still here"
        )
    children = [
        ui.TextDisplay(f"## {title}"),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay("\n".join(lines)),
        ui.Separator(visible=True, spacing=SMALL),
        ui.TextDisplay(f"-# {_e('footer')} 〃 **GlobalBots {_e('bullet', '•')} Invite Logs**"),
    ]
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*children, accent_colour=colour))
    return view


# --------------------------------------------------------------------- cog
class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> {code: (uses, inviter_id | None)}
        self._cache: dict[int, dict[str, tuple[int, int | None]]] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    async def cog_load(self) -> None:
        db = await _db()
        await db.execute(_CREATE_STATS)
        await db.execute(_CREATE_MEMBERS)

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def _fetch(self, guild: discord.Guild) -> dict[str, tuple[int, int | None]] | None:
        try:
            invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None
        return {i.code: (i.uses or 0, i.inviter.id if i.inviter else None) for i in invites}

    async def _refresh(self, guild: discord.Guild) -> None:
        async with self._lock(guild.id):
            data = await self._fetch(guild)
            if data is not None:
                self._cache[guild.id] = data

    async def _send_log(self, guild: discord.Guild, view: ui.LayoutView) -> None:
        channel_id = getattr(config, "INVITES_LOG_CHANNEL_ID", 0) or config.CHANNEL_LOG
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        try:
            await channel.send(view=view, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException) as e:
            print(f"[invites] log send failed: {e}")

    # ---- cache upkeep
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._refresh(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._refresh(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None:
            return
        self._cache.setdefault(invite.guild.id, {})[invite.code] = (
            invite.uses or 0,
            invite.inviter.id if invite.inviter else None,
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        # Keep the entry: a single-use invite is deleted the moment it is
        # used, and on_member_join needs the old entry to know who owned it.
        pass

    # ---- joins / leaves
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild = member.guild
        async with self._lock(guild.id):
            old = self._cache.get(guild.id, {})
            new = await self._fetch(guild)
            if new is None:
                return
            self._cache[guild.id] = new

            inviter: int | None = None
            for code, (uses, inv) in new.items():
                if uses > old.get(code, (0, None))[0]:
                    inviter = inv
                    break
            if inviter is None:
                # Invite hit its max uses and vanished.
                gone = [c for c in old if c not in new]
                if len(gone) == 1:
                    inviter = old[gone[0]][1]

        if inviter == member.id:
            inviter = None
        try:
            await record_join(guild.id, member.id, inviter or 0)
            stats = await get_stats(guild.id, inviter) if inviter else None
            await self._send_log(guild, build_log_view(member, inviter or 0, joined=True, stats=stats))
        except Exception as e:  # never let tracking break the join flow
            print(f"[invites] record_join failed: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        try:
            inviter = await record_leave(member.guild.id, member.id)
            if inviter is None:
                return
            stats = await get_stats(member.guild.id, inviter) if inviter else None
            await self._send_log(member.guild, build_log_view(member, inviter, joined=False, stats=stats))
        except Exception as e:
            print(f"[invites] record_leave failed: {e}")

    # ---- commands
    @app_commands.command(name="panel-invites", description="Send the Invites panel")
    @slash_is_ownership_only()
    async def panel_invites(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.channel.send(view=build_panel_view())
        await interaction.followup.send("Panel sent.", ephemeral=True)

    @app_commands.command(name="invites", description="Show how many people you (or someone else) invited")
    @app_commands.describe(member="The member to check (default: you)")
    @app_commands.guild_only()
    async def invites(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        view = await build_stats_view(interaction.guild, target)
        await interaction.response.send_message(view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = interaction.data.get("custom_id", "")
        if custom_id == "invites:me":
            view = await build_stats_view(interaction.guild, interaction.user)
        elif custom_id == "invites:top":
            view = await build_leaderboard_view(interaction.guild)
        else:
            return
        await interaction.response.send_message(view=view, ephemeral=True)

    @panel_invites.error
    async def panel_invites_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invites(bot))
