# Each value can be a plain unicode emoji, a static custom emoji
# '<:name:123...>', or an animated one '<a:name:123...>'. Get the exact
# string by typing \:youremojiname: in Discord (backslash before the
# colon) and copying what it sends.

GENERAL = {
    "purchase": "<:name:0>",
    "order": "<:name:0>",
    "close": "<:name:0>",
    "claim": "<:name:0>",
    "ping": "<:name:0>",
    "transcript": "<:name:0>",
    "bot": "<:name:0>",
    "budget": "<:name:0>",
    "payment": "<:name:0>",
    "reason": "<:name:0>",
    "log_open": "<:name:0>",
    "log_close": "<:name:0>",
    "place_order": "<:name:0>",
    "order_accept": "<:name:0>",
    "order_done": "<:name:0>",
    "order_cancel": "<:name:0>",
    "order_pending": "<:name:0>",
    "support_title": "<:name:0>",
    "support_owner": "<:name:0>",
    "support_general": "<:name:0>",
    "support_technical": "<:name:0>",
    "support_billing": "<:name:0>",
    "support_process": "<:name:0>",
    "support_step": "<:name:0>",
    "support_warning": "<:name:0>",
}

SUGGESTIONS = {
    "upvote": "<:name:0>",
    "downvote": "<:name:0>",
    "suggestion": "<:name:0>",
    "submitted": "<:name:0>",
    "bullet": "<:name:0>",
}

# Not present in the original config — filled with sensible defaults,
# replace with your own custom emoji IDs if you have them.
REVIEWS = {
    "review": "<:name:0>",
    "star_filled": "<:name:0>",
    "star_empty": "<:name:0>",
    "user": "<:name:0>",
    "comment": "<:name:0>",
    "date": "<:name:0>",
    "bullet": "<:name:0>",
    "make_review": "<:name:0>",
}

GIVEAWAY = {
    "giveaway": "<:name:0>",
    "join": "<:name:0>",
    "leave": "<:name:0>",
    "info": "<:name:0>",
    "edit": "<:name:0>",
    "reroll": "<:name:0>",
    "end": "<:name:0>",
    "participants": "<:name:0>",
    "winner": "<:name:0>",
    "prize": "<:name:0>",
    "host": "<:name:0>",
    "winners_count": "<:name:0>",
    "entries": "<:name:0>",
    "time": "<:name:0>",
    "id": "<:name:0>",
    "role": "<:name:0>",
    "add_member": "<:name:0>",
}

_CATEGORIES = {
    "general": GENERAL,
    "suggestions": SUGGESTIONS,
    "reviews": REVIEWS,
    "giveaway": GIVEAWAY,
}

# Flat dict of the "general" category, kept for cogs that still do
# EMOJI["some_key"] directly (tickets.py, orders.py, support_tickets.py).
EMOJI: dict = GENERAL


def emoji(category: str, key: str) -> str:
    """Looks up the given category/key. Returns '' if missing instead of
    raising, so an unset emoji just falls back to whatever default the
    caller passes (e.g. `emoji("giveaway", "join") or "🎉"`)."""
    return _CATEGORIES.get(category, {}).get(key, "")
