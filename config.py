import os

# Fill in your real IDs below. Right-click a role/channel in Discord
# (Developer Mode on) and 'Copy ID'. Emoji live in emojis.py, not here.


def _env_or(env_name: str, value: str) -> str:
    """Render (or any host) env vars take priority over the value below,
    so secrets don't have to be committed to this file."""
    return os.environ.get(env_name, value)


GUILD_ID: int = 0

ROLE_DEVELOPER: int = 0
ROLE_CEO: int = 0
ROLE_CO_CEO: int = 0
ROLE_OWNERSHIP: int = 0

# Convenience aliases used across cogs (bot_status, giveaways, permissions).
CEO_ROLE_ID: int = ROLE_CEO
OWNERSHIP_ROLE_ID: int = ROLE_OWNERSHIP

CHANNEL_TICKET_PANEL: int = 0
CHANNEL_LOG: int = 0
CHANNEL_ORDERS: int = 0
CHANNEL_ORDERS_LOG: int = 0
LOG_GIVEAWAY_CHANNEL_ID: int = 0
REVIEWS_LOG_CHANNEL_ID: int = 0
SUGGESTIONS_CHANNEL_ID: int = 0

TICKET_CATEGORY: int = 0

# URLs used for the ticket panel (banner + thumbnail). Leave as None to skip.
# The per-ticket panel inside each ticket channel only ever shows a
# thumbnail (the customer's avatar) — no banner there, by design.
PANEL_BANNER_URL: str | None = None
PANEL_THUMBNAIL_URL: str | None = None

# --- Support ticket system (Owner / General Support / Technical / Billing) ---
# staff_roles is its own list of role IDs — fill it in yourself, it can
# overlap with or differ from ROLE_DEVELOPER/ROLE_CEO/ROLE_CO_CEO above.
SUPPORT_CATEGORY: int = 0
SUPPORT_STAFF_ROLES: list[int] = []
SUPPORT_PANEL_CHANNEL: int = 0
SUPPORT_BANNER_URL: str | None = None
SUPPORT_THUMBNAIL_URL: str | None = None

# --- Giveaways / Reviews banners ---
GIVEAWAY_BANNER_URL: str | None = None
REVIEWS_BANNER_URL: str | None = None

BOT_TOKEN: str = _env_or("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")

TURSO_URL: str = _env_or("TURSO_URL", "libsql://your-database-name.turso.io")
TURSO_AUTH_TOKEN: str = _env_or("TURSO_AUTH_TOKEN", "PUT_YOUR_TURSO_AUTH_TOKEN_HERE")

# Render (and other hosts) require the process to bind to a port so their
# health check passes. This does not need to be a "real" web server.
KEEP_ALIVE_PORT: int = int(os.environ.get("PORT", 1000))


def staff_role_ids() -> list[int]:
    """Roles allowed to view/manage every ticket (Developer, CEO, Co-CEO)."""
    return [ROLE_DEVELOPER, ROLE_CEO, ROLE_CO_CEO]
