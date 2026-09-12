import os

# Fill in your real IDs below. Right-click a role/channel in Discord
# (Developer Mode on) and 'Copy ID'. Emoji live in emojis.py, not here.


def _env_or(env_name: str, value: str) -> str:
    """Render (or any host) env vars take priority over the value below,
    so secrets don't have to be committed to this file."""
    return os.environ.get(env_name, value)


GUILD_ID: int = 1544741507049721926

ROLE_DEVELOPER: int = 1545533359558492261
ROLE_CEO: int = 1545533341032382504
ROLE_CO_CEO: int = 1545533343888580699
ROLE_OWNERSHIP: int = 1548308555701026906

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

TICKET_CATEGORIES: dict[str, int] = {
    "purchase": CATEGORY_PURCHASE,
    "order": CATEGORY_ORDER,
    "owner": CATEGORY_OWNER,
    "general": CATEGORY_GENERAL,
    "technical": CATEGORY_TECHNICAL,
    "billing": CATEGORY_BILLING,
}

# URLs used for the ticket panel (banner + thumbnail). Leave as None to skip.
# The per-ticket panel inside each ticket channel only ever shows a
# thumbnail (the customer's avatar) — no banner there, by design.
PANEL_BANNER_URL: str | None = "https://i.imgur.com/qUfaZMv.png"
PANEL_THUMBNAIL_URL: str | None = "https://i.imgur.com/kaYAwgW.gif"

# --- Support ticket system (Owner / General Support / Technical / Billing) ---
# staff_roles is its own list of role IDs — fill it in yourself, it can
# overlap with or differ from ROLE_DEVELOPER/ROLE_CEO/ROLE_CO_CEO above.
# (Each support kind now has its own category above in TICKET_CATEGORIES —
# CATEGORY_OWNER / CATEGORY_GENERAL / CATEGORY_TECHNICAL / CATEGORY_BILLING.)
SUPPORT_STAFF_ROLES: list[int] = [1548308555701026906, 1545533359558492261, 1545533352377974996]
SUPPORT_PANEL_CHANNEL: int = 1545576092323287101
SUPPORT_BANNER_URL: str | None = "https://i.imgur.com/qUfaZMv.png"
SUPPORT_THUMBNAIL_URL: str | None = "https://i.imgur.com/kaYAwgW.gif"

SUPPORT_LOG_CHANNEL: int = 1545572161014726756

# --- Giveaways / Reviews banners ---
GIVEAWAY_BANNER_URL: str | None = "https://i.imgur.com/qUfaZMv.png"
REVIEWS_BANNER_URL: str | None = "https://i.imgur.com/qUfaZMv.png"
REVIEWS_THUMBNAIL_URL: str | None = "https://i.imgur.com/kaYAwgW.gif"

BOT_TOKEN: str = _env_or("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")

TURSO_URL: str = _env_or("TURSO_URL", "libsql://your-database-name.turso.io")
TURSO_AUTH_TOKEN: str = _env_or("TURSO_AUTH_TOKEN", "PUT_YOUR_TURSO_AUTH_TOKEN_HERE")

# Render (and other hosts) require the process to bind to a port so their
# health check passes. This does not need to be a "real" web server.
KEEP_ALIVE_PORT: int = int(os.environ.get("PORT", 1000))


def staff_role_ids() -> list[int]:
    """Roles allowed to view/manage every ticket (Developer, CEO, Co-CEO)."""
    return [ROLE_DEVELOPER, ROLE_CEO, ROLE_CO_CEO]
