import os

# Fill in your real IDs below. Right-click a role/channel in Discord
# (Developer Mode on) and 'Copy ID'. Emoji live in emojis.py, not here.


def _env_or(env_name: str, value: str) -> str:
    """Render (or any host) env vars take priority over the value below,
    so secrets don't have to be committed to this file."""
    return os.environ.get(env_name, value)


GUILD_ID: int = 1544741507049721926

ROLE_DEVELOPER: int = 1545533347877625886
ROLE_CEO: int = 1545533341032382504
ROLE_CO_CEO: int = 1545533343888580699
ROLE_OWNERSHIP: int = 1548308555701026906
ROLE_STAFF: int = 1545533352377974996
ROLE_MANAGER: int = 1548418196078596158

# Convenience aliases used across cogs (bot_status, giveaways, permissions).
CEO_ROLE_ID: int = ROLE_CEO
OWNERSHIP_ROLE_ID: int = ROLE_OWNERSHIP

CHANNEL_TICKET_PANEL: int = 1548345379810975755
CHANNEL_LOG: int = 1545572198016745512
CHANNEL_ORDERS: int = 1545533450541338716
CHANNEL_ORDERS_LOG: int = 1545533457629974578
LOG_GIVEAWAY_CHANNEL_ID: int = 1545573812047716400
REVIEWS_LOG_CHANNEL_ID: int = 1545533444556066916
SUGGESTIONS_CHANNEL_ID: int = 1545533516878450708

TICKET_CATEGORY: int = 1545575251864330270

# Each ticket "kind" now gets its own category. Fill in real IDs — 0 falls
# back to no category (channel created at the top level) until you do.
CATEGORY_PURCHASE: int = 1545575251864330270
CATEGORY_ORDER: int = 1548390952060723270
CATEGORY_OWNER: int = 1548391395558039613
CATEGORY_GENERAL: int = 1548346082767929519
CATEGORY_TECHNICAL: int = 1548391613150138539
CATEGORY_BILLING: int = 1548391218596020274
CATEGORY_MANAGER: int = 1557696643321565184

TICKET_CATEGORIES: dict[str, int] = {
    "purchase": CATEGORY_PURCHASE,
    "order": CATEGORY_ORDER,
    "owner": CATEGORY_OWNER,
    "manager": CATEGORY_MANAGER,
    "general": CATEGORY_GENERAL,
    "technical": CATEGORY_TECHNICAL,
    "billing": CATEGORY_BILLING,
}

# URLs used for the ticket panel (banner + thumbnail). Leave as None to skip.
# The per-ticket panel inside each ticket channel only ever shows a
# thumbnail (the customer's avatar) — no banner there, by design.
PANEL_BANNER_URL: str | None = "https://i.imgur.com/Rr4tGCX.jpeg"
PANEL_THUMBNAIL_URL: str | None = "https://i.imgur.com/kaYAwgW.gif"

# --- Support ticket system (Owner / General Support / Technical / Billing) ---
# staff_roles is its own list of role IDs — fill it in yourself, it can
# overlap with or differ from ROLE_DEVELOPER/ROLE_CEO/ROLE_CO_CEO above.
# (Each support kind now has its own category above in TICKET_CATEGORIES —
# CATEGORY_OWNER / CATEGORY_GENERAL / CATEGORY_TECHNICAL / CATEGORY_BILLING.)
TICKET_KIND_STAFF_ROLES: dict[str, list[int]] = {
    "owner": [ROLE_OWNERSHIP],
    "order": [ROLE_OWNERSHIP, ROLE_DEVELOPER],
    "purchase": [ROLE_OWNERSHIP],
    "general": [ROLE_STAFF, ROLE_MANAGER],
    "technical": [ROLE_DEVELOPER, ROLE_OWNERSHIP],
    "manager": [ROLE_MANAGER],
    "billing": [ROLE_OWNERSHIP],
}

SUPPORT_PANEL_CHANNEL: int = 1545576092323287101
SUPPORT_BANNER_URL: str | None = "https://i.imgur.com/Rr4tGCX.jpeg"
SUPPORT_THUMBNAIL_URL: str | None = "https://i.imgur.com/kaYAwgW.gif"

SUPPORT_LOG_CHANNEL: int = 1545572161014726756

# --- Giveaways / Reviews banners ---
GIVEAWAY_BANNER_URL: str | None = "https://i.imgur.com/Rr4tGCX.jpeg"
REVIEWS_BANNER_URL: str | None = "https://i.imgur.com/Rr4tGCX.jpeg"
REVIEWS_THUMBNAIL_URL: str | None = "https://i.imgur.com/kaYAwgW.gif"

# --- Developer applications ---
# Category where each applicant's private application channel is created
# (0 = no category, channel is created at the top level).
APPLICATIONS_CATEGORY_ID: int = 1563946311668072498
# Staff-only channel where submitted applications arrive for review. REQUIRED —
# applicants can't press "Sent" until this is filled in.
APPLICATIONS_LOG_CHANNEL_ID: int = 1563946425417601054
# Roles that can see the application channels, use Ping User / Close.
APPLICATION_STAFF_ROLE_IDS: list[int] = [ROLE_OWNERSHIP, ROLE_CEO, ROLE_CO_CEO]
# Roles that can Accept / Deny and use Show Answers in the log channel.
APPLICATION_REVIEW_ROLE_IDS: list[int] = [ROLE_OWNERSHIP, ROLE_CEO, ROLE_CO_CEO]
# Role given to the applicant when accepted (0 = give no role).
APPLICATION_ACCEPTED_ROLE_ID: int = ROLE_DEVELOPER
# Banner shown at the top of the /panel-applications panel (None = no banner).
APPLICATIONS_BANNER_URL: str | None = "https://i.imgur.com/Rr4tGCX.jpeg"

# Questions asked in the application. A plain string is a normal question
# (the applicant types the answer and can attach photos/files); a dict with
# "type": "yesno" shows Yes / No buttons instead.
# NOTE: these are SAMPLE questions — replace them with your own.
APPLICATION_QUESTIONS: list = [
    "How old are you?",
    "Which programming languages do you work with?",
    {"text": "Do you have experience building Discord bots?", "type": "yesno"},
    "How many years of development experience do you have?",
    "Why do you want to join our development team?",
    "Send a photo of something you have created, or a link to a server where your work is hosted.",
    "Do you work at another shop that deals with bots? And if so, where, and what is your position?",
    "Do you work with components v2?",
    "How many hours are you active during the week, and how many hours will you be able to work?",
    {"text": "Are you aware that it is prohibited to share customers personal information, and that doing so will result in serious penalties?", "type": "yesno"},
]

# Application types. Only "developer" exists; its custom_id on the panel
# button is "app_apply:developer".
APPLICATION_TYPES: dict[str, dict] = {
    "developer": {"label": "Developer", "questions": APPLICATION_QUESTIONS},
}

BOT_TOKEN: str = _env_or("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")

TURSO_URL: str = _env_or("TURSO_URL", "libsql://your-database-name.turso.io")
TURSO_AUTH_TOKEN: str = _env_or("TURSO_AUTH_TOKEN", "PUT_YOUR_TURSO_AUTH_TOKEN_HERE")

# Render (and other hosts) require the process to bind to a port so their
# health check passes. This does not need to be a "real" web server.
KEEP_ALIVE_PORT: int = int(os.environ.get("PORT", 1000))


def staff_role_ids() -> list[int]:
    """Roles allowed to view/manage every ticket (Developer, CEO, Co-CEO)."""
    return [ROLE_DEVELOPER, ROLE_CEO, ROLE_CO_CEO]
