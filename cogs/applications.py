from __future__ import annotations

import io
import re

import discord
from discord import ui, app_commands
from discord.ext import commands

import config
from emojis import emoji
from utils import storage
from utils.components import add_action_row, add_separator, add_text, build_base_container
from utils.permissions import member_has_any_role, slash_is_ownership_only

STORE_NAME = "applications"
LOCKS_STORE = "application_locks"

APP_ACCENT = discord.Colour(0x0084FF)
MAX_FILES = 10  # Discord allows at most 10 attachments per message
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
URL_RE = re.compile(r"https?://[^\s<>]+")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _q_text(q) -> str:
    return q["text"] if isinstance(q, dict) else q


def _q_type(q) -> str:
    return q.get("type", "text") if isinstance(q, dict) else "text"


def _safe_name(text: str) -> str:
    text = text.lower().strip().replace(" ", "-")
    return "".join(c for c in text if c.isalnum() or c == "-")[:90] or "user"


def _clean_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:] or "file"


def _is_locked(type_key: str) -> bool:
    return bool(storage.get_store(LOCKS_STORE).get(type_key, False))


def _btn_emoji(key: str) -> str | None:
    return emoji("applications", key) or None


def _is_image(file_info: dict) -> bool:
    ctype = (file_info.get("content_type") or "").lower()
    return ctype.startswith("image/") or file_info.get("filename", "").lower().endswith(IMAGE_EXTS)


def _image_links(text: str) -> list[str]:
    """Links inside a text answer that point straight at an image."""
    found: list[str] = []
    for url in URL_RE.findall(text or ""):
        url = url.rstrip(").,!?>]")
        if url.split("?", 1)[0].lower().endswith(IMAGE_EXTS):
            found.append(url)
    return found[:4]


def _mention(applicant, info: dict) -> str:
    return applicant.mention if applicant else "<@" + str(info["user_id"]) + ">"


def _staff_ids() -> list[int]:
    return list(config.APPLICATION_STAFF_ROLE_IDS)


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------

def build_panel_view() -> ui.LayoutView:
    def e(key: str) -> str:
        return emoji("applications", key)

    container = ui.Container(accent_colour=APP_ACCENT)
    if config.APPLICATIONS_BANNER_URL:
        container.add_item(ui.MediaGallery(discord.MediaGalleryItem(media=config.APPLICATIONS_BANNER_URL)))
        add_separator(container)
    add_text(container, f"# {e('title')}** Developer Application**")
    add_separator(container)
    add_text(
        container,
        f"{e('info')} If you want to become a member of our development team, click the button below to "
        "__answer a few questions__ about your work. __We will review your application and get in touch "
        "with you regarding further information and the results.__",
    )
    add_separator(container)
    add_text(container, f"### {e('process')} **__APPLICATION PROCESS__**")
    add_text(
        container,
        f"> {e('step')} Click the **\"Apply\"** button and go to the channel that opens.\n"
        f"> {e('step')} Inside the channel, press the **\"Start\"** button and answer the questions. "
        "Make sure to answer honestly.\n"
        f"> {e('step')} You will be asked to send a photo of something you have created, or a link to a "
        "server where your work is hosted.\n"
        f"> {e('step')} Once you have answered all the questions, click the **\"Sent\"** button, and your "
        "application will be sent to us for review.",
    )
    add_separator(container)
    add_text(
        container,
        f"> **{e('disclaimer')} __Disclaimer:__**\n"
        "> We might have a few more questions, so keep an eye on the application channel.",
    )
    add_action_row(
        container,
        ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Apply",
            emoji=_btn_emoji("apply"),
            custom_id="app_apply:developer",
        ),
    )
    add_separator(container)
    add_text(container, f"> -# {e('footer')} GlobalBots Application System")

    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


# --------------------------------------------------------------------------
# Answers rendering (shared by the review message and "Show Answers")
# --------------------------------------------------------------------------

def _add_answers(container: ui.Container, questions: list, answers: list[dict]) -> None:
    """Adds every question + answer to the container. Uploaded files are
    referenced as attachment://<review_filename>, so the message they are
    shown in must carry those files."""
    count = max(len(answers), 1)
    # A Components V2 message may hold ~4000 characters of text in total.
    budget = max(150, (3300 - sum(len(_q_text(q)) + 10 for q in questions)) // count)

    for i, (q, ans) in enumerate(zip(questions, answers), start=1):
        full_text = ans.get("text", "")
        body = full_text if len(full_text) <= budget else full_text[: budget - 1] + "…"
        block = f"**{i}. {_q_text(q)}**"
        if body:
            block += f"\n{body}"
        add_text(container, block)

        files = ans.get("files", [])
        shown = [f for f in files if f.get("review_filename")]

        gallery = [
            discord.MediaGalleryItem(media=f"attachment://{f['review_filename']}")
            for f in shown if _is_image(f)
        ]
        gallery += [discord.MediaGalleryItem(media=url) for url in _image_links(full_text)]
        if gallery:
            container.add_item(ui.MediaGallery(*gallery[:10]))

        for f in shown:
            if not _is_image(f):
                container.add_item(ui.File(f"attachment://{f['review_filename']}"))

        skipped = [f["filename"] for f in files if not f.get("review_filename")]
        if skipped:
            add_text(container, "-# Not uploaded (too large or unavailable): " + ", ".join(skipped))


# --------------------------------------------------------------------------
# Modal
# --------------------------------------------------------------------------

class DenyReasonModal(ui.Modal, title="Denial reason"):
    reason = ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, channel_id: int, cog: "Applications"):
        super().__init__()
        self.channel_id = channel_id
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.finalize_application(interaction, self.channel_id, accepted=False, reason=str(self.reason))


# --------------------------------------------------------------------------
# Cog
# --------------------------------------------------------------------------

class Applications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- commands ---------------------------------------------------------

    @app_commands.command(name="panel-applications", description="Send the Developer Application panel")
    @slash_is_ownership_only()
    async def panel_applications(self, interaction: discord.Interaction):
        await interaction.channel.send(view=build_panel_view())
        await interaction.response.send_message("Panel sent.", ephemeral=True)

    @app_commands.command(name="lockapplications", description="Close the applications (nobody can apply)")
    @slash_is_ownership_only()
    async def lockapplications(self, interaction: discord.Interaction):
        locks = storage.get_store(LOCKS_STORE)
        locks["developer"] = True
        storage.save(LOCKS_STORE, locks)
        await interaction.response.send_message("Applications are now **locked**.", ephemeral=True)

    @app_commands.command(name="unlockapplications", description="Re-open the applications")
    @slash_is_ownership_only()
    async def unlockapplications(self, interaction: discord.Interaction):
        locks = storage.get_store(LOCKS_STORE)
        locks["developer"] = False
        storage.save(LOCKS_STORE, locks)
        await interaction.response.send_message("Applications are now **unlocked**.", ephemeral=True)

    # ---- apply ------------------------------------------------------------

    async def start_apply(self, interaction: discord.Interaction, type_key: str):
        data = config.APPLICATION_TYPES.get(type_key)
        if not data:
            await interaction.response.send_message("Unknown application type.", ephemeral=True)
            return

        if _is_locked(type_key):
            await interaction.response.send_message(
                f"**{data['label']}** applications are currently closed. Please try again later.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        user = interaction.user

        store = storage.get_store(STORE_NAME)
        for ch_id, info in store.items():
            if info.get("user_id") == user.id and info.get("status") not in ("closed", "denied", "accepted"):
                channel = guild.get_channel(int(ch_id))
                if channel:
                    await interaction.response.send_message(
                        f"You already have an open application: {channel.mention}", ephemeral=True
                    )
                    return

        await interaction.response.defer(ephemeral=True)

        category = guild.get_channel(config.APPLICATIONS_CATEGORY_ID) if config.APPLICATIONS_CATEGORY_ID else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role_id in _staff_ids():
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"application-{_safe_name(user.display_name)}", category=category, overwrites=overwrites
        )

        store[str(channel.id)] = {
            "type": type_key, "user_id": user.id, "status": "pending",
            "current_step": 0, "answers": [],
        }
        storage.save(STORE_NAME, store)

        total = len(data["questions"])
        container = build_base_container(
            title=f"{data['label']} Application",
            description=(
                f"{user.mention}\n"
                f"Press **Start** when you are ready. You will be asked **{total}** questions — "
                "please answer honestly."
            ),
            accent_colour=APP_ACCENT,
        )
        add_separator(container)
        start_btn = ui.Button(label="Start", style=discord.ButtonStyle.success, custom_id=f"app_start:{channel.id}")
        close_btn = ui.Button(label="Close", style=discord.ButtonStyle.danger,
                              emoji=_btn_emoji("close"), custom_id=f"app_close:{channel.id}")
        ping_btn = ui.Button(label="Ping User", style=discord.ButtonStyle.secondary,
                             emoji=_btn_emoji("ping"), custom_id=f"app_ping_user:{channel.id}")
        add_action_row(container, start_btn, close_btn, ping_btn)

        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        await channel.send(view=view)
        await interaction.followup.send(f"Your application: {channel.mention}", ephemeral=True)

    # ---- questions --------------------------------------------------------

    async def send_question(self, channel: discord.TextChannel, type_key: str, step: int):
        questions = config.APPLICATION_TYPES[type_key]["questions"]
        q = questions[step]
        title = f"Question {step + 1}/{len(questions)}"

        if _q_type(q) == "yesno":
            container = build_base_container(title=title, description=_q_text(q), accent_colour=APP_ACCENT)
            yes_btn = ui.Button(label="Yes", style=discord.ButtonStyle.success,
                                emoji=_btn_emoji("yes"), custom_id=f"app_yn:{channel.id}:yes")
            no_btn = ui.Button(label="No", style=discord.ButtonStyle.danger,
                               emoji=_btn_emoji("no"), custom_id=f"app_yn:{channel.id}:no")
            add_action_row(container, yes_btn, no_btn)
        else:
            container = build_base_container(
                title=title,
                description=_q_text(q) + "\n\n*Write your answer in this channel. You can also attach photos or files.*",
                accent_colour=APP_ACCENT,
            )
        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        await channel.send(view=view)

    async def handle_start(self, interaction: discord.Interaction, channel_id: int):
        store = storage.get_store(STORE_NAME)
        info = store.get(str(channel_id))
        if not info or interaction.user.id != info["user_id"]:
            await interaction.response.send_message("Only the applicant can start the application.", ephemeral=True)
            return
        if info.get("status") != "pending":
            await interaction.response.send_message("The application has already been started.", ephemeral=True)
            return
        info["status"] = "answering"
        store[str(channel_id)] = info
        storage.save(STORE_NAME, store)
        await interaction.response.send_message("Let's begin.", ephemeral=True)
        await self.send_question(interaction.channel, info["type"], 0)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        store = storage.get_store(STORE_NAME)
        info = store.get(str(message.channel.id))
        if not info or info.get("status") != "answering" or message.author.id != info["user_id"]:
            return

        questions = config.APPLICATION_TYPES[info["type"]]["questions"]
        if info["current_step"] >= len(questions):
            return
        if _q_type(questions[info["current_step"]]) == "yesno":
            return

        text = message.content.strip()
        files = [
            {
                "id": a.id,
                "message_id": message.id,
                "filename": a.filename,
                "content_type": a.content_type,
                "size": a.size,
            }
            for a in message.attachments
        ]
        if not text and not files:
            return

        await self._advance(message.channel, info, {"text": text, "files": files})
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass

    async def _advance(self, channel: discord.TextChannel, info: dict, answer: dict):
        store = storage.get_store(STORE_NAME)
        questions = config.APPLICATION_TYPES[info["type"]]["questions"]
        info["answers"].append(answer)
        step = info["current_step"] + 1
        info["current_step"] = step

        if step < len(questions):
            store[str(channel.id)] = info
            storage.save(STORE_NAME, store)
            await self.send_question(channel, info["type"], step)
            return

        info["status"] = "ready_to_submit"
        store[str(channel.id)] = info
        storage.save(STORE_NAME, store)

        container = build_base_container(
            title="You have answered all the questions",
            description="Press **Sent** to send your application for review.",
            accent_colour=APP_ACCENT,
        )
        sent_btn = ui.Button(label="Sent", style=discord.ButtonStyle.success,
                             emoji=_btn_emoji("send"), custom_id=f"app_send:{channel.id}")
        add_action_row(container, sent_btn)
        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        await channel.send(view=view)

    async def handle_yesno(self, interaction: discord.Interaction, channel_id: int, answer: str):
        store = storage.get_store(STORE_NAME)
        info = store.get(str(channel_id))
        if not info or interaction.user.id != info["user_id"] or info.get("status") != "answering":
            await interaction.response.send_message("Only the applicant can answer.", ephemeral=True)
            return

        questions = config.APPLICATION_TYPES[info["type"]]["questions"]
        if _q_type(questions[info["current_step"]]) != "yesno":
            await interaction.response.send_message("This question can't be answered with Yes/No.", ephemeral=True)
            return

        await interaction.response.defer()
        label = "Yes" if answer == "yes" else "No"
        await self._advance(interaction.channel, info, {"text": label, "files": []})

    # ---- submit -----------------------------------------------------------

    async def _collect_files(self, channel: discord.TextChannel, info: dict, size_limit: int) -> list[discord.File]:
        """Re-downloads the applicant's attachments from the application
        channel (fresh CDN links) so they can be re-uploaded to the review
        message, where they stay available after the channel is deleted."""
        files: list[discord.File] = []
        total = 0
        messages: dict[int, discord.Message] = {}

        for ai, ans in enumerate(info["answers"], start=1):
            for fi, f in enumerate(ans.get("files", []), start=1):
                if len(files) >= MAX_FILES:
                    continue
                try:
                    msg = messages.get(f["message_id"])
                    if msg is None:
                        msg = await channel.fetch_message(f["message_id"])
                        messages[f["message_id"]] = msg
                    att = next((a for a in msg.attachments if a.id == f["id"]), None)
                    if att is None or total + att.size > size_limit:
                        continue
                    data = await att.read()
                except discord.HTTPException:
                    continue
                name = f"q{ai}_{fi}_{_clean_filename(f['filename'])}"
                f["review_filename"] = name
                total += att.size
                files.append(discord.File(io.BytesIO(data), filename=name))
        return files

    async def handle_send(self, interaction: discord.Interaction, channel_id: int):
        store = storage.get_store(STORE_NAME)
        info = store.get(str(channel_id))
        if not info or interaction.user.id != info["user_id"]:
            await interaction.response.send_message("Only the applicant can send the application.", ephemeral=True)
            return

        if info.get("status") != "ready_to_submit":
            await interaction.response.send_message("Your application has already been sent.", ephemeral=True)
            return

        guild = interaction.guild
        log_channel = guild.get_channel(config.APPLICATIONS_LOG_CHANNEL_ID) if config.APPLICATIONS_LOG_CHANNEL_ID else None
        if not log_channel:
            await interaction.response.send_message(
                "The applications log channel is not configured. Please contact the staff.", ephemeral=True
            )
            return

        # Claim the submission before the first await so a double click can't send it twice.
        info["status"] = "submitting"
        store[str(channel_id)] = info
        storage.save(STORE_NAME, store)
        await interaction.response.defer()

        try:
            files = await self._collect_files(interaction.channel, info, guild.filesize_limit)

            applicant = guild.get_member(info["user_id"])
            type_label = config.APPLICATION_TYPES[info["type"]]["label"]
            questions = config.APPLICATION_TYPES[info["type"]]["questions"]

            container = build_base_container(
                title=f"New Application — {type_label}",
                description=f"User: {_mention(applicant, info)}\n-# ID: {info['user_id']}",
                accent_colour=APP_ACCENT,
            )
            add_separator(container)
            _add_answers(container, questions, info["answers"])
            add_separator(container)
            accept_btn = ui.Button(label="Accept", style=discord.ButtonStyle.success,
                                   emoji=_btn_emoji("accept"), custom_id=f"app_accept:{channel_id}")
            deny_btn = ui.Button(label="Deny", style=discord.ButtonStyle.danger,
                                 emoji=_btn_emoji("deny"), custom_id=f"app_deny:{channel_id}")
            add_action_row(container, accept_btn, deny_btn)

            view = ui.LayoutView(timeout=None)
            view.add_item(container)
            log_message = await log_channel.send(
                view=view, files=files, allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception:
            info["status"] = "ready_to_submit"
            store[str(channel_id)] = info
            storage.save(STORE_NAME, store)
            await interaction.followup.send(
                "Something went wrong while sending your application. Please press **Sent** again.", ephemeral=True
            )
            raise

        info["status"] = "submitted"
        info["log_message_id"] = log_message.id
        store[str(channel_id)] = info
        storage.save(STORE_NAME, store)

        done_container = build_base_container(
            title="Application sent",
            description=(
                "Your application has been sent for review. You will receive the result by **DM**, "
                "so make sure your DMs are open."
            ),
            accent_colour=APP_ACCENT,
        )
        done_view = ui.LayoutView(timeout=None)
        done_view.add_item(done_container)
        await interaction.edit_original_response(view=done_view)

    # ---- review -----------------------------------------------------------

    async def finalize_application(self, interaction: discord.Interaction, channel_id: int, *,
                                   accepted: bool, reason: str | None = None):
        store = storage.get_store(STORE_NAME)
        info = store.get(str(channel_id))
        if not info:
            await self._reply(interaction, "Application not found.")
            return
        if info.get("status") != "submitted":
            await self._reply(interaction, "This application has already been reviewed.")
            return

        if not interaction.response.is_done():
            await interaction.response.defer()

        guild = interaction.guild
        applicant = guild.get_member(info["user_id"])
        type_label = config.APPLICATION_TYPES[info["type"]]["label"]
        problems: list[str] = []

        if accepted:
            role_id = config.APPLICATION_ACCEPTED_ROLE_ID
            role = guild.get_role(role_id) if role_id else None
            if role and applicant:
                try:
                    await applicant.add_roles(role, reason="Application accepted")
                except discord.HTTPException:
                    problems.append(f"I couldn't give {role.mention} to the user (check my permissions / role position).")
            info["status"] = "accepted"
            dm_text = (
                f"Your **{type_label}** application in **{guild.name}** has been **accepted**! "
                "Our team will get in touch with you regarding further information."
            )
        else:
            info["status"] = "denied"
            dm_text = (
                f"Your **{type_label}** application in **{guild.name}** has been **denied**.\n"
                f"Reason: {reason}"
            )

        info["decided_by"] = interaction.user.id
        info["decision_reason"] = reason
        store[str(channel_id)] = info
        storage.save(STORE_NAME, store)

        if applicant:
            try:
                await applicant.send(dm_text)
            except discord.HTTPException:
                problems.append("I couldn't DM the user (their DMs are closed). Please tell them the result manually.")
        else:
            problems.append("The user is no longer in the server, so no DM was sent.")

        status_text = (
            f"**Accepted by** {interaction.user.mention}"
            if accepted
            else f"**Denied by** {interaction.user.mention}\nReason: {reason}"
        )
        container = build_base_container(
            title=f"Application — {type_label}",
            description=f"User: {_mention(applicant, info)}",
            accent_colour=APP_ACCENT,
        )
        add_separator(container)
        add_text(container, status_text)
        add_separator(container)
        show_btn = ui.Button(label="Show Answers", style=discord.ButtonStyle.secondary,
                             custom_id=f"app_showanswers:{channel_id}")
        add_action_row(container, show_btn)

        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        await interaction.message.edit(view=view, allowed_mentions=discord.AllowedMentions.none())

        if problems:
            await interaction.followup.send("\n".join(problems), ephemeral=True)

    @staticmethod
    async def _reply(interaction: discord.Interaction, text: str):
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    async def handle_show_answers(self, interaction: discord.Interaction, channel_id: int):
        store = storage.get_store(STORE_NAME)
        info = store.get(str(channel_id))
        if not info:
            await interaction.response.send_message("Application not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # The uploaded files are still attached to the review message.
        files = [await a.to_file() for a in interaction.message.attachments]

        questions = config.APPLICATION_TYPES[info["type"]]["questions"]
        container = build_base_container(title="Answers", accent_colour=APP_ACCENT)
        add_separator(container)
        _add_answers(container, questions, info.get("answers", []))
        reason = info.get("decision_reason")
        if reason:
            add_separator(container)
            add_text(container, f"**Decision reason**\n{reason}")

        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        await interaction.followup.send(view=view, files=files, ephemeral=True)

    # ---- channel buttons --------------------------------------------------

    async def handle_close(self, interaction: discord.Interaction, channel_id: int):
        store = storage.get_store(STORE_NAME)
        info = store.get(str(channel_id))
        is_staff = member_has_any_role(interaction.user, _staff_ids())
        is_applicant = bool(info) and interaction.user.id == info["user_id"]
        if not (is_staff or is_applicant):
            await interaction.response.send_message("You can't close this application.", ephemeral=True)
            return

        if info:
            info["status"] = "closed"
            store[str(channel_id)] = info
            storage.save(STORE_NAME, store)
        await interaction.response.send_message("Closing the channel...")
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            await channel.delete(reason=f"Application closed by {interaction.user}")

    async def handle_ping_user(self, interaction: discord.Interaction, channel_id: int):
        store = storage.get_store(STORE_NAME)
        info = store.get(str(channel_id))
        if not info:
            await interaction.response.send_message("Application not found.", ephemeral=True)
            return

        if not member_has_any_role(interaction.user, _staff_ids()):
            await interaction.response.send_message("Only the staff team can ping the user.", ephemeral=True)
            return

        applicant = interaction.guild.get_member(info["user_id"])
        await interaction.response.send_message(applicant.mention if applicant else "User not found.")
        if applicant:
            try:
                await applicant.send(f"You have a notification in your application: {interaction.channel.mention}")
            except discord.HTTPException:
                pass

    def _can_review(self, member: discord.Member, channel_id: int) -> bool:
        store = storage.get_store(STORE_NAME)
        if str(channel_id) not in store:
            return False
        return member_has_any_role(member, config.APPLICATION_REVIEW_ROLE_IDS)

    # ---- interaction router ----------------------------------------------

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")

        if custom_id.startswith("app_apply:"):
            await self.start_apply(interaction, custom_id.split(":", 1)[1])
        elif custom_id.startswith("app_start:"):
            await self.handle_start(interaction, int(custom_id.split(":")[1]))
        elif custom_id.startswith("app_yn:"):
            _, ch_id, answer = custom_id.split(":")
            await self.handle_yesno(interaction, int(ch_id), answer)
        elif custom_id.startswith("app_send:"):
            await self.handle_send(interaction, int(custom_id.split(":")[1]))
        elif custom_id.startswith("app_close:"):
            await self.handle_close(interaction, int(custom_id.split(":")[1]))
        elif custom_id.startswith("app_ping_user:"):
            await self.handle_ping_user(interaction, int(custom_id.split(":")[1]))
        elif custom_id.startswith("app_showanswers:"):
            channel_id = int(custom_id.split(":")[1])
            if not self._can_review(interaction.user, channel_id):
                await interaction.response.send_message("You don't have permission.", ephemeral=True)
                return
            await self.handle_show_answers(interaction, channel_id)
        elif custom_id.startswith("app_accept:"):
            channel_id = int(custom_id.split(":")[1])
            if not self._can_review(interaction.user, channel_id):
                await interaction.response.send_message("You don't have permission.", ephemeral=True)
                return
            await self.finalize_application(interaction, channel_id, accepted=True)
        elif custom_id.startswith("app_deny:"):
            channel_id = int(custom_id.split(":")[1])
            if not self._can_review(interaction.user, channel_id):
                await interaction.response.send_message("You don't have permission.", ephemeral=True)
                return
            await interaction.response.send_modal(DenyReasonModal(channel_id, self))


async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))
