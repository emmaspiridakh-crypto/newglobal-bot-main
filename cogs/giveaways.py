from __future__ import annotations

import asyncio
import json
import os
import random
import re
import string
import datetime
from typing import Optional

import discord
from discord import ui, app_commands
from discord.ext import commands, tasks

import config
from emojis import emoji
from utils.permissions import has_roles
from utils import turso

def _gen_id(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _parse_duration(text: str) -> Optional[datetime.timedelta]:
    pattern = r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?"
    m = re.fullmatch(pattern, text.strip().lower())
    if not m or not any(m.groups()):
        return None
    d, h, mins = (int(x) if x else 0 for x in m.groups())
    return datetime.timedelta(days=d, hours=h, minutes=mins)


def _parse_signed_duration(text: str) -> Optional[datetime.timedelta]:
    text = text.strip()
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    delta = _parse_duration(text)
    if delta is None:
        return None
    return -delta if negative else delta


def _fmt_dt(ts: float) -> str:
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return discord.utils.format_dt(dt, style="R")


def _log_embed(guild: discord.Guild, *, title: str, color: int, fields: list[tuple[str, str, bool]]) -> discord.Embed:
    embed = discord.Embed(title=title, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


async def _send_log(guild: discord.Guild, embed: discord.Embed):
    ch = guild.get_channel(config.LOG_GIVEAWAY_CHANNEL_ID)
    if ch:
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            pass


def _is_authorized(member: discord.Member, host_id: int) -> bool:
    if member.id == host_id:
        return True
    return has_roles(member, config.CEO_ROLE_ID)

class CreateGiveawayModal(ui.Modal, title="Δημιουργία Giveaway"):
    prize = ui.TextInput(label="Έπαθλο", placeholder="π.χ. Discord Nitro", max_length=200, required=True)
    duration = ui.TextInput(label="Διάρκεια", placeholder="π.χ. 1d, 2h, 30m, 1h30m", max_length=20, required=True)
    winners = ui.TextInput(label="Αριθμός νικητών", placeholder="1", max_length=2, required=True, default="1")
    required_role = ui.TextInput(label="Required Role ID (προαιρετικό)", placeholder="Αφησε κενό αν δεν θεσ", required=False, max_length=20)

    def __init__(self, cog: "Giveaways"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        delta = _parse_duration(str(self.duration))
        if not delta:
            await interaction.response.send_message("Λάθος format διάρκειας. Χρήση: `1d`, `2h`, `30m`, `1h30m`", ephemeral=True)
            return

        try:
            winner_count = max(1, int(str(self.winners)))
        except ValueError:
            await interaction.response.send_message("Ο αριθμός νικητών πρέπει να είναι αριθμός.", ephemeral=True)
            return

        role_id = None
        role_raw = str(self.required_role).strip()
        if role_raw:
            try:
                role_id = int(role_raw)
                if not interaction.guild.get_role(role_id):
                    await interaction.response.send_message("Δεν βρέθηκε ρόλος με αυτό το ID.", ephemeral=True)
                    return
            except ValueError:
                await interaction.response.send_message("Το Required Role ID πρέπει να είναι αριθμός.", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)
        await self.cog.create_giveaway(
            interaction=interaction,
            prize=str(self.prize),
            delta=delta,
            winner_count=winner_count,
            role_id=role_id,
        )


class EditGiveawayModal(ui.Modal, title="Επεξεργασία Giveaway"):
    prize = ui.TextInput(label="Νέο Έπαθλο", max_length=200, required=False)
    duration_add = ui.TextInput(label="Χρόνος +/- (προαιρετικό)", placeholder="π.χ. 1h προσθέτει, -30m αφαιρεί", required=False, max_length=20)
    winners = ui.TextInput(label="Νέος αριθμός νικητών (προαιρετικό)", required=False, max_length=2)
    required_role = ui.TextInput(label="Required Role ID (0 για αφαίρεση)", required=False, max_length=20)

    def __init__(self, giveaway_id: str, cog: "Giveaways"):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gw = await self.cog.db_get(self.giveaway_id)
        if not gw or gw["status"] != "active":
            await interaction.followup.send("Το giveaway δεν βρέθηκε ή έχει λήξει.", ephemeral=True)
            return

        changes = []
        new_prize = str(self.prize).strip() if str(self.prize).strip() else None
        new_winners = str(self.winners).strip()
        new_role = str(self.required_role).strip()
        duration_add = str(self.duration_add).strip()

        updates: dict = {}

        if new_prize:
            updates["prize"] = new_prize
            changes.append(f"Έπαθλο → **{new_prize}**")

        if new_winners:
            try:
                wc = max(1, int(new_winners))
                updates["winner_count"] = wc
                changes.append(f"Νικητές → **{wc}**")
            except ValueError:
                pass

        if new_role:
            try:
                rid = int(new_role)
                updates["required_role_id"] = None if rid == 0 else rid
                changes.append(f"Required Role → {'Καμία' if rid == 0 else f'<@&{rid}>'}")
            except ValueError:
                pass

        if duration_add:
            delta = _parse_signed_duration(duration_add)
            if delta:
                now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
                new_end = max(gw["end_time"] + delta.total_seconds(), now_ts + 10)
                updates["end_time"] = new_end
                changes.append(f"Νέος χρόνος → {_fmt_dt(new_end)}")

        if not updates:
            await interaction.followup.send("Δεν άλλαξε τίποτα.", ephemeral=True)
            return

        await self.cog.db_update(self.giveaway_id, updates)
        gw.update(updates)

        guild = interaction.guild
        ch = guild.get_channel(gw["channel_id"])
        if ch:
            try:
                msg = await ch.fetch_message(gw["message_id"])
                view = self.cog.build_panel(gw, guild)
                await msg.edit(view=view)
            except discord.NotFound:
                pass

        await interaction.followup.send(f"Το giveaway ενημερώθηκε:\n" + "\n".join(changes), ephemeral=True)

        host = guild.get_member(gw["host_id"])
        await _send_log(guild, _log_embed(guild,
            title=f"{emoji('giveaway','edit')} Giveaway Edited",
            color=0xFEE75C,
            fields=[
                ("ID", f"`#{self.giveaway_id}`", True),
                ("Έπαθλο", gw.get("prize", "—"), True),
                ("Επεξεργάστηκε από", interaction.user.mention, False),
                ("Host", host.mention if host else str(gw["host_id"]), True),
                ("Αλλαγές", "\n".join(changes) or "—", False),
            ]
        ))

class AddMemberModal(ui.Modal, title="Προσθήκη Μελών στο Giveaway"):
    users = ui.TextInput(
        label="User ID(s)",
        style=discord.TextStyle.paragraph,
        placeholder="Ένα ή περισσότερα ID, χωρισμένα με κόμμα/κενό/νέα γραμμή",
        max_length=1000,
        required=True,
    )

    def __init__(self, giveaway_id: str, cog: "Giveaways"):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gw = await self.cog.db_get(self.giveaway_id)
        if not gw or gw["status"] != "active":
            await interaction.followup.send("Το giveaway δεν βρέθηκε ή έχει λήξει.", ephemeral=True)
            return

        tokens = re.split(r"[,\s]+", str(self.users).strip())
        entries: list = gw["entries"]
        added, already, invalid, missing = [], [], [], []

        for raw in tokens:
            token = raw.strip("<@!>").strip()
            if not token:
                continue
            if not token.isdigit():
                invalid.append(raw)
                continue
            uid = int(token)
            member = interaction.guild.get_member(uid)
            if not member:
                missing.append(raw)
                continue
            if uid in entries:
                already.append(raw)
                continue
            entries.append(uid)
            added.append(uid)

        if added:
            await self.cog.db_save_entries(self.giveaway_id, entries)
            gw["entries"] = entries
            guild = interaction.guild
            ch = guild.get_channel(gw["channel_id"])
            if ch:
                try:
                    msg = await ch.fetch_message(gw["message_id"])
                    await msg.edit(view=self.cog.build_panel(gw, guild))
                except (discord.NotFound, discord.HTTPException):
                    pass

        summary = []
        if added:
            summary.append(f"{emoji('giveaway','add_member')} Προστέθηκαν: " + ", ".join(f"<@{u}>" for u in added))
        if already:
            summary.append("Ήδη συμμετείχαν: " + ", ".join(already))
        if missing:
            summary.append("Δεν βρέθηκαν στον server: " + ", ".join(missing))
        if invalid:
            summary.append("Μη έγκυρα ID: " + ", ".join(invalid))
        await interaction.followup.send("\n".join(summary) or "Καμία αλλαγή.", ephemeral=True)

        if added:
            await _send_log(interaction.guild, _log_embed(interaction.guild,
                title=f"{emoji('giveaway','add_member')} Μέλη Προστέθηκαν στο Giveaway",
                color=0x57F287,
                fields=[
                    ("ID", f"`#{self.giveaway_id}`", True),
                    ("Έπαθλο", gw["prize"], True),
                    ("Προστέθηκαν από", interaction.user.mention, True),
                    ("Μέλη", " ".join(f"<@{u}>" for u in added), False),
                ]
            ))

class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await turso.async_execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                host_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winner_count INTEGER NOT NULL DEFAULT 1,
                end_time REAL NOT NULL,
                required_role_id INTEGER,
                entries TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                winners TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL
            )
        """)
        self.check_giveaways.start()

    async def cog_unload(self):
        self.check_giveaways.cancel()

    @staticmethod
    def _row_to_gw(d: dict) -> dict:
        d = dict(d)
        d["entries"] = json.loads(d["entries"])
        d["winners"] = json.loads(d["winners"])
        return d

    async def db_get(self, giveaway_id: str) -> Optional[dict]:
        rows = await turso.async_execute("SELECT * FROM giveaways WHERE id = ?", [giveaway_id])
        if not rows:
            return None
        return self._row_to_gw(rows[0])

    async def db_all_active(self) -> list[dict]:
        rows = await turso.async_execute("SELECT * FROM giveaways WHERE status = 'active'")
        return [self._row_to_gw(r) for r in rows]

    async def db_update(self, giveaway_id: str, fields: dict):
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [giveaway_id]
        await turso.async_execute(f"UPDATE giveaways SET {set_clause} WHERE id = ?", values)

    async def db_save_entries(self, giveaway_id: str, entries: list[int]):
        await turso.async_execute("UPDATE giveaways SET entries = ? WHERE id = ?",
                                   [json.dumps(entries), giveaway_id])

    def build_panel(self, gw: dict, guild: discord.Guild) -> ui.LayoutView:
        is_ended = gw["status"] != "active"
        entries_count = len(gw["entries"])
        host = guild.get_member(gw["host_id"])
        host_str = host.mention if host else f"<@{gw['host_id']}>"

        role_str = ""
        if gw.get("required_role_id"):
            role_str = f"\n{emoji('giveaway','role')} **Required:** <@&{gw['required_role_id']}>"

        winners_str = ""
        if gw["winners"]:
            winners_str = "\n{} **Winners:** {}".format(
                emoji("giveaway", "winner"),
                " ".join(f"<@{w}>" for w in gw["winners"])
            )

        panel_text = (
            f"## {emoji('giveaway','giveaway')} GIVEAWAY\n - GlobalBots\n"
            f"{emoji('giveaway','prize')} **Έπαθλο:** {gw['prize']}\n"
            f"{emoji('giveaway','host')} **Host:** {host_str}\n"
            f"{emoji('giveaway','winners_count')} **Νικητές:** {gw['winner_count']}\n"
            f"{emoji('giveaway','entries')} **Συμμετοχές:** {entries_count}\n"
            f"{emoji('giveaway','time')} **{'Έληξε' if is_ended else 'Λήγει'}:** {_fmt_dt(gw['end_time'])}"
            f"{role_str}"
            f"{winners_str}"
        )

        container = ui.Container(accent_colour=discord.Colour(0x3D91FF) if not is_ended else discord.Colour.greyple())

        if config.GIVEAWAY_BANNER_URL:
            container.add_item(ui.MediaGallery(discord.MediaGalleryItem(media=config.GIVEAWAY_BANNER_URL)))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        container.add_item(ui.TextDisplay(panel_text))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        join_btn = ui.Button(
            label="Join" if not is_ended else "Ended",
            style=discord.ButtonStyle.success if not is_ended else discord.ButtonStyle.secondary,
            emoji=emoji("giveaway", "join") or "🎉",
            custom_id=f"gw_join:{gw['id']}",
            disabled=is_ended,
        )
        info_btn = ui.Button(
            label="Information",
            style=discord.ButtonStyle.secondary,
            emoji=emoji("giveaway", "info") or "ℹ️",
            custom_id=f"gw_info:{gw['id']}",
        )

        row = ui.ActionRow()
        row.add_item(join_btn)
        row.add_item(info_btn)
        container.add_item(row)

        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        return view

    def build_info_panel(self, gw: dict) -> ui.LayoutView:
        container = ui.Container(accent_colour=discord.Colour(0x3D91FF))
        container.add_item(ui.TextDisplay(
            f"## {emoji('giveaway','info')} Giveaway Management\n"
            f"**ID:** `#{gw['id']}` | **Έπαθλο:** {gw['prize']}\n"
            f"**Συμμετοχές:** {len(gw['entries'])}"
        ))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        edit_btn = ui.Button(label="Edit", style=discord.ButtonStyle.primary,
                              emoji=emoji("giveaway", "edit") or "✏️",
                              custom_id=f"gw_edit:{gw['id']}")
        reroll_btn = ui.Button(label="Reroll", style=discord.ButtonStyle.secondary,
                                emoji=emoji("giveaway", "reroll") or "🔄",
                                custom_id=f"gw_reroll:{gw['id']}")
        end_btn = ui.Button(label="End", style=discord.ButtonStyle.danger,
                             emoji=emoji("giveaway", "end") or "⏹️",
                             custom_id=f"gw_end_now:{gw['id']}")
        participants_btn = ui.Button(label="Participants", style=discord.ButtonStyle.secondary,
                                      emoji=emoji("giveaway", "participants") or "👥",
                                      custom_id=f"gw_participants:{gw['id']}")
        add_member_btn = ui.Button(label="Add Member", style=discord.ButtonStyle.success,
                                    emoji=emoji("giveaway", "add_member") or "➕",
                                    custom_id=f"gw_addmember:{gw['id']}",
                                    disabled=gw["status"] != "active")

        row1 = ui.ActionRow()
        row1.add_item(edit_btn)
        row1.add_item(reroll_btn)
        row1.add_item(end_btn)
        container.add_item(row1)

        row2 = ui.ActionRow()
        row2.add_item(participants_btn)
        row2.add_item(add_member_btn)
        container.add_item(row2)

        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        return view

    async def create_giveaway(self, interaction: discord.Interaction, *, prize: str,
                               delta: datetime.timedelta, winner_count: int, role_id: Optional[int]):
        guild = interaction.guild
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        end_ts = now + delta.total_seconds()

        gw_id = _gen_id()
        while await self.db_get(gw_id):
            gw_id = _gen_id()

        gw: dict = {
            "id": gw_id, "guild_id": guild.id, "channel_id": interaction.channel.id,
            "message_id": None, "host_id": interaction.user.id, "prize": prize,
            "winner_count": winner_count, "end_time": end_ts,
            "required_role_id": role_id, "entries": [], "status": "active",
            "winners": [], "created_at": now,
        }

        view = self.build_panel(gw, guild)
        msg = await interaction.channel.send(view=view)
        gw["message_id"] = msg.id

        await turso.async_execute("""
            INSERT INTO giveaways
            (id, guild_id, channel_id, message_id, host_id, prize, winner_count,
             end_time, required_role_id, entries, status, winners, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [gw_id, guild.id, interaction.channel.id, msg.id, interaction.user.id,
              prize, winner_count, end_ts, role_id, "[]", "active", "[]", now])

        await interaction.followup.send(f" Giveaway δημιουργήθηκε! ID: `#{gw_id}`", ephemeral=True)

        role_str = f"<@&{role_id}>" if role_id else "Καμία"
        await _send_log(guild, _log_embed(guild,
            title=f"{emoji('giveaway','giveaway')} Giveaway Created",
            color=0x57F287,
            fields=[
                ("ID", f"`#{gw_id}`", True),
                ("Έπαθλο", prize, True),
                ("Host", interaction.user.mention, True),
                ("Νικητές", str(winner_count), True),
                ("Λήγει", _fmt_dt(end_ts), True),
                ("Required Role", role_str, True),
            ]
        ))

    async def end_giveaway(self, gw: dict, *, reroll: bool = False, forced_by: Optional[discord.Member] = None):
        guild = self.bot.get_guild(gw["guild_id"])
        if not guild:
            return

        entries = gw["entries"]
        winner_count = gw["winner_count"]
        prize = gw["prize"]

        if gw.get("required_role_id"):
            role = guild.get_role(gw["required_role_id"])
            if role:
                entries = [uid for uid in entries if guild.get_member(uid) and
                           any(r.id == role.id for r in guild.get_member(uid).roles)]

        if not entries:
            winners = []
        else:
            k = min(winner_count, len(entries))
            winners = random.sample(entries, k)

        await self.db_update(gw["id"], {"status": "ended", "winners": json.dumps(winners)})
        gw["winners"] = winners
        gw["status"] = "ended"

        ch = guild.get_channel(gw["channel_id"])
        if ch:
            try:
                msg = await ch.fetch_message(gw["message_id"])
                view = self.build_panel(gw, guild)
                await msg.edit(view=view)
            except (discord.NotFound, discord.HTTPException):
                pass

            if winners:
                mentions = " ".join(f"<@{w}>" for w in winners)
                ann_container = ui.Container(accent_colour=discord.Colour.gold())
                ann_container.add_item(ui.TextDisplay(
                    f"## {emoji('giveaway','winner')} {'Rerolled Winner' if reroll else 'Giveaway Ended'}!\n"
                    f"{emoji('giveaway','prize')} **Έπαθλο:** {prize}\n"
                    f"**{'Νέος ν' if reroll else 'Ν'}ικητ{'ές' if len(winners) > 1 else 'ής'}:** {mentions}\n"
                    f"Συγχαρητήρια! {emoji('giveaway','giveaway')}"
                ))
                ann_view = ui.LayoutView(timeout=None)
                ann_view.add_item(ann_container)
                await ch.send(view=ann_view)

                for uid in winners:
                    member = guild.get_member(uid)
                    if member:
                        try:
                            await member.send(
                                f"Κέρδισες **{prize}** στον server **{guild.name}**! "
                                f"Επικοινώνησε με τον δημιουργό του giveaway ή άνοιξε ένα ticket για να λάβεις το έπαθλο σου."
                            )
                        except discord.Forbidden:
                            pass
            else:
                no_win_container = ui.Container(accent_colour=discord.Colour.red())
                no_win_container.add_item(ui.TextDisplay(
                    f"## {emoji('giveaway','end')} Giveaway Ended\n"
                    f"**Έπαθλο:** {prize}\n"
                    f"Δεν υπήρχαν αρκετοί συμμετέχοντες για να βγουν νικητές."
                ))
                no_view = ui.LayoutView(timeout=None)
                no_view.add_item(no_win_container)
                await ch.send(view=no_view)

        action = "Rerolled" if reroll else "Ended"
        log_color = 0xEB459E if reroll else 0xED4245
        fields = [("ID", f"`#{gw['id']}`", True), ("Έπαθλο", prize, True)]
        if forced_by:
            fields.append(("Έκλεισε από", forced_by.mention, True))
        fields.append(("Νικητές", " ".join(f"<@{w}>" for w in winners) if winners else "Κανείς", False))
        fields.append(("Συμμετοχές", str(len(gw["entries"])), True))

        await _send_log(guild, _log_embed(guild,
            title=f"{emoji('giveaway', 'reroll' if reroll else 'end')} Giveaway {action}",
            color=log_color, fields=fields
        ))

    @tasks.loop(seconds=10)
    async def check_giveaways(self):
        try:
            now = datetime.datetime.now(datetime.timezone.utc).timestamp()
            active = await self.db_all_active()
            for gw in active:
                if gw["end_time"] <= now:
                    await self.end_giveaway(gw)
        except Exception as e:
            print(f"[Giveaways] Error in check_giveaways: {e}")

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id: str = interaction.data.get("custom_id", "")

        if custom_id.startswith("gw_join:"):
            await self._handle_join(interaction, custom_id.split(":", 1)[1])
        elif custom_id.startswith("gw_info:"):
            await self._handle_info(interaction, custom_id.split(":", 1)[1])
        elif custom_id.startswith("gw_edit:"):
            await self._handle_edit(interaction, custom_id.split(":", 1)[1])
        elif custom_id.startswith("gw_reroll:"):
            await self._handle_reroll(interaction, custom_id.split(":", 1)[1])
        elif custom_id.startswith("gw_end_now:"):
            await self._handle_end_now(interaction, custom_id.split(":", 1)[1])
        elif custom_id.startswith("gw_participants:"):
            await self._handle_participants(interaction, custom_id.split(":", 1)[1])
        elif custom_id.startswith("gw_addmember:"):
            await self._handle_add_member(interaction, custom_id.split(":", 1)[1])

    async def _handle_join(self, interaction: discord.Interaction, gw_id: str):
        gw = await self.db_get(gw_id)
        if not gw or gw["status"] != "active":
            await interaction.response.send_message("Αυτό το giveaway έχει λήξει.", ephemeral=True)
            return

        if gw.get("required_role_id"):
            role = interaction.guild.get_role(gw["required_role_id"])
            if role and role not in interaction.user.roles:
                await interaction.response.send_message(
                    f"Χρειάζεσαι τον ρόλο {role.mention} για να συμμετέχεις.", ephemeral=True
                )
                return

        entries: list = gw["entries"]
        uid = interaction.user.id

        if uid in entries:
            entries.remove(uid)
            await self.db_save_entries(gw_id, entries)
            gw["entries"] = entries
            try:
                await interaction.message.edit(view=self.build_panel(gw, interaction.guild))
            except discord.HTTPException:
                pass
            await interaction.response.send_message(
                f"{emoji('giveaway','leave')} Αφαιρέθηκες από το giveaway **{gw['prize']}**.", ephemeral=True
            )
            await _send_log(interaction.guild, _log_embed(interaction.guild,
                title=f"{emoji('giveaway','leave')} Giveaway Left",
                color=0xED4245,
                fields=[("User", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                        ("ID", f"`#{gw_id}`", True), ("Έπαθλο", gw["prize"], True)]
            ))
        else:
            entries.append(uid)
            await self.db_save_entries(gw_id, entries)
            gw["entries"] = entries
            try:
                await interaction.message.edit(view=self.build_panel(gw, interaction.guild))
            except discord.HTTPException:
                pass
            await interaction.response.send_message(
                f"{emoji('giveaway','join')} Μπήκες στο giveaway **{gw['prize']}**! Καλή τύχη!", ephemeral=True
            )
            await _send_log(interaction.guild, _log_embed(interaction.guild,
                title=f"{emoji('giveaway','join')} Giveaway Joined",
                color=0x57F287,
                fields=[("User", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                        ("ID", f"`#{gw_id}`", True), ("Έπαθλο", gw["prize"], True),
                        ("Συμμετοχές", str(len(entries)), True)]
            ))

    async def _handle_info(self, interaction: discord.Interaction, gw_id: str):
        gw = await self.db_get(gw_id)
        if not gw:
            await interaction.response.send_message("Giveaway δεν βρέθηκε.", ephemeral=True)
            return
        if not _is_authorized(interaction.user, gw["host_id"]):
            await interaction.response.send_message(
                f"{emoji('giveaway','end')} Δεν έχεις δικαίωμα να δεις αυτό το panel.", ephemeral=True
            )
            return
        view = self.build_info_panel(gw)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def _handle_edit(self, interaction: discord.Interaction, gw_id: str):
        gw = await self.db_get(gw_id)
        if not gw:
            await interaction.response.send_message("Giveaway δεν βρέθηκε.", ephemeral=True)
            return
        if not _is_authorized(interaction.user, gw["host_id"]):
            await interaction.response.send_message("Δεν έχεις δικαίωμα.", ephemeral=True)
            return
        if gw["status"] != "active":
            await interaction.response.send_message("Το giveaway έχει ήδη λήξει.", ephemeral=True)
            return
        await interaction.response.send_modal(EditGiveawayModal(gw_id, self))

    async def _handle_reroll(self, interaction: discord.Interaction, gw_id: str):
        gw = await self.db_get(gw_id)
        if not gw:
            await interaction.response.send_message("Giveaway δεν βρέθηκε.", ephemeral=True)
            return
        if not _is_authorized(interaction.user, gw["host_id"]):
            await interaction.response.send_message("Δεν έχεις δικαίωμα.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gw_fresh = await self.db_get(gw_id)
        pool = [e for e in gw_fresh["entries"] if e not in gw_fresh["winners"]] or gw_fresh["entries"]
        if not pool:
            await interaction.followup.send("Δεν υπάρχουν συμμετοχές για reroll.", ephemeral=True)
            return
        gw_fresh["status"] = "ended"
        gw_fresh["entries"] = pool
        await self.end_giveaway(gw_fresh, reroll=True, forced_by=interaction.user)
        await interaction.followup.send("Reroll ολοκληρώθηκε!", ephemeral=True)

    async def _handle_end_now(self, interaction: discord.Interaction, gw_id: str):
        gw = await self.db_get(gw_id)
        if not gw:
            await interaction.response.send_message("Giveaway δεν βρέθηκε.", ephemeral=True)
            return
        if not _is_authorized(interaction.user, gw["host_id"]):
            await interaction.response.send_message("Δεν έχεις δικαίωμα.", ephemeral=True)
            return
        if gw["status"] != "active":
            await interaction.response.send_message("Το giveaway έχει ήδη λήξει.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.end_giveaway(gw, forced_by=interaction.user)
        await interaction.followup.send("Το giveaway τερματίστηκε.", ephemeral=True)

    async def _handle_participants(self, interaction: discord.Interaction, gw_id: str):
        gw = await self.db_get(gw_id)
        if not gw:
            await interaction.response.send_message("Giveaway δεν βρέθηκε.", ephemeral=True)
            return
        if not _is_authorized(interaction.user, gw["host_id"]):
            await interaction.response.send_message("Δεν έχεις δικαίωμα.", ephemeral=True)
            return

        entries = gw["entries"]
        if not entries:
            participant_text = "*Κανείς δεν έχει συμμετάσχει ακόμα.*"
        else:
            lines = [f"`{i+1}.` <@{uid}>" for i, uid in enumerate(entries[:50])]
            if len(entries) > 50:
                lines.append(f"*... και {len(entries) - 50} ακόμα*")
            participant_text = "\n".join(lines)

        container = ui.Container(accent_colour=discord.Colour(0x3D91FF))
        container.add_item(ui.TextDisplay(
            f"## {emoji('giveaway','participants')} Συμμετέχοντες — `#{gw_id}`\n"
            f"**Σύνολο:** {len(entries)}\n\n{participant_text}"
        ))
        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def _handle_add_member(self, interaction: discord.Interaction, gw_id: str):
        gw = await self.db_get(gw_id)
        if not gw:
            await interaction.response.send_message("Giveaway δεν βρέθηκε.", ephemeral=True)
            return
        if not _is_authorized(interaction.user, gw["host_id"]):
            await interaction.response.send_message("Δεν έχεις δικαίωμα.", ephemeral=True)
            return
        if gw["status"] != "active":
            await interaction.response.send_message("Το giveaway έχει ήδη λήξει.", ephemeral=True)
            return
        await interaction.response.send_modal(AddMemberModal(gw_id, self))


    giveaway_group = app_commands.Group(name="giveaway", description="Giveaway commands")

    @giveaway_group.command(name="create", description="Δημιουργεί νέο giveaway")
    @app_commands.checks.has_any_role(config.CEO_ROLE_ID)
    async def giveaway_create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CreateGiveawayModal(self))

    @giveaway_group.command(name="delete", description="Διαγράφει giveaway (CEO only)")
    @app_commands.describe(giveaway_id="Το ID του giveaway (χωρίς #)")
    @app_commands.checks.has_any_role(config.CEO_ROLE_ID)
    async def giveaway_delete(self, interaction: discord.Interaction, giveaway_id: str):
        gw = await self.db_get(giveaway_id.upper())
        if not gw:
            await interaction.response.send_message("Giveaway δεν βρέθηκε.", ephemeral=True)
            return

        guild = interaction.guild
        ch = guild.get_channel(gw["channel_id"])
        if ch:
            try:
                msg = await ch.fetch_message(gw["message_id"])
                await msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

        await turso.async_execute("DELETE FROM giveaways WHERE id = ?", [giveaway_id.upper()])

        await interaction.response.send_message(f"Giveaway `#{giveaway_id.upper()}` διαγράφηκε.", ephemeral=True)
        await _send_log(guild, _log_embed(guild,
            title=f"{emoji('giveaway','end')} Giveaway Deleted",
            color=0xED4245,
            fields=[
                ("ID", f"`#{giveaway_id.upper()}`", True),
                ("Έπαθλο", gw["prize"], True),
                ("Διαγράφηκε από", interaction.user.mention, False),
            ]
        ))

    @giveaway_group.command(name="list", description="Εμφανίζει τα ενεργά giveaways")
    @app_commands.checks.has_any_role(config.CEO_ROLE_ID)
    async def giveaway_list(self, interaction: discord.Interaction):
        active = await self.db_all_active()
        if not active:
            await interaction.response.send_message("Δεν υπάρχουν ενεργά giveaways.", ephemeral=True)
            return

        container = ui.Container(accent_colour=discord.Colour.gold())
        lines = [f"## {emoji('giveaway','giveaway')} Ενεργά Giveaways\n"]
        for gw in active:
            lines.append(
                f"**`#{gw['id']}`** — {gw['prize']} | "
                f"Λήγει: {_fmt_dt(gw['end_time'])} | "
                f"Συμμετοχές: {len(gw['entries'])}"
            )
        container.add_item(ui.TextDisplay("\n".join(lines)))
        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
