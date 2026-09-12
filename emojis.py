# Each value can be a plain unicode emoji, a static custom emoji
# '<:name:123...>', or an animated one '<a:name:123...>'. Get the exact
# string by typing \:youremojiname: in Discord (backslash before the
# colon) and copying what it sends.

GENERAL = {
    "purchase": "<:name:1548349993830850713>",
    "order": "<:name:1545578583332757665>",
    "close": "<:name:1545364084499808256>",
    "claim": "<:name:1544994894370578474>",
    "ping": "<:name:1545365144538718260>",
    "transcript": "<:name:1545576883536793621>",
    "bot": "<:name:1545576824380067860>",
    "budget": "<:name:1548349637918728232>",
    "payment": "<:name:1545553195760099358>",
    "reason": "<:name:1544996395373559869>",
    "log_open": "<a:name:1544996079626362920>",
    "log_close": "<a:name:1544996055462977556>",
    "place_order": "<a:name:1545552914334875800>",
    "order_accept": "<:name:1544994894370578474>",
    "order_done": "<:name:1544994871369273424>",
    "order_cancel": "<:name:1545364084499808256>",
    "order_pending": "<a:name:1548350905802424441>",
    "support_title": "<:name:1545553071872933898>",
    "support_owner": "<:name:1545576744956727306>",
    "support_general": "<:name:1545553101493248030>",
    "support_technical": "<:name:1545577232922312734>",
    "support_billing": "<:name:1545553195760099358>",
    "support_process": "<:name:1545578059820826745>",
    "support_step": "<a:name:1545552914334875800>",
    "support_warning": "<a:name:1545576625574387762>",
    "check": "<:name:1544994894370578474>",
    "cancel": "<:name:1545364084499808256>",
    "send": "<a:name:1545552914334875800>",
    "plan": "<:name:1548349637918728232>",
    "server": "<:name:1545576824380067860>",
}

SUGGESTIONS = {
    "upvote": "<:name:1544996128809029702>",
    "downvote": "<:name:1544996104511430736>",
    "suggestion": "<:name:1544996395373559869>",
    "submitted": "<:name:1547475085588303943>",
    "bullet": "<:name:1545576267904974859>",
}

# Not present in the original config — filled with sensible defaults,
# replace with your own custom emoji IDs if you have them.
REVIEWS = {
    "review": "<a:name:1544996461245112390>",
    "star_filled": "<a:name:1544996461245112390>",
    "star_empty": "<:name:>",
    "user": "<:name:1547475085588303943>",
    "comment": "<:name:1544996395373559869>",
    "date": "<:name:1547464754593796106>",
    "bullet": "<:name:1545576267904974859>",
    "make_review": "<a:name:1544996461245112390>",
}

GIVEAWAY = {
    "giveaway": "<:name:1547458529089290290>",
    "join": "<:name:1545363231181381642>",
    "leave": "<:name:1545363295467470908>",
    "info": "<:name:1545579981030162432>",
    "edit": "<:name:1545576993448529951>",
    "reroll": "<a:name:1548350905802424441>",
    "end": "<a:name:1544996055462977556>",
    "participants": "<:name:1547475085588303943>",
    "winner": "<:name:1547466980506738779>",
    "prize": "<:name:1545578059820826745>",
    "host": "<:name:1545576744956727306>",
    "winners_count": "<:name:1547460941057101834>",
    "entries": "<:name:1545363231181381642>",
    "time": "<:name:1547464754593796106>",
    "id": "<:name:1548353089927512135>",
    "role": "<:name:1545550175953494187>",
    "add_member": "<:name:1544996128809029702>",
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
