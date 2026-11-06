# Each value can be a plain unicode emoji, a static custom emoji
# '<:name:123...>', or an animated one '<a:name:123...>'. Get the exact
# string by typing \:youremojiname: in Discord (backslash before the
# colon) and copying what it sends.

GENERAL = {
    "purchase": "<:name:1548349993830850713>",
    "order": "<:name:1545578583332757665>",
    "close": "<:name:1566453823189418146>",
    "claim": "<:name:1545577232922312734>",
    "ping": "<:name:1566453919842836520>",
    "transcript": "<:name:1545576883536793621>",
    "bot": "<:name:1545576824380067860>",
    "budget": "<:name:1548349637918728232>",
    "payment": "<:name:1545553195760099358>",
    "reason": "<:name:1566461391878095091>",
    "log_open": "<a:name:1544996079626362920>",
    "log_close": "<a:name:1544996055462977556>",
    "place_order": "<a:name:1545552914334875800>",
    "order_accept": "<:name:1544994894370578474>",
    "order_done": "<:name:1544994894370578474>",
    "order_cancel": "<:name:1545364084499808256>",
    "order_pending": "<a:name:1548350905802424441>",
    "support_title": "<:name:1545553071872933898>",
    "support_owner": "<:name:1545576744956727306>",
    "support_manager": "<:name:1557694211602513950>",
    "support_general": "<:name:1548740498603122788>",
    "support_technical": "<:name:1545577232922312734>",
    "support_billing": "<:name:1545553195760099358>",
    "support_replacement": "<:name:1548741673109037116>",
    "support_process": "<:name:1545578059820826745>",
    "support_step": "<a:name:1545552914334875800>",
    "support_warning": "<a:name:1545576625574387762>",
    "check": "<:name:1544994894370578474>",
    "cancel": "<:name:1545364084499808256>",
    "send": "<a:name:1545552914334875800>",
    "plan": "<:name:1548349637918728232>",
    "server": "<:name:1545576824380067860>",
    # Modify button on the ticket panel. Uses the same emoji as the giveaway
    # "edit" button for now — replace the ID with your own custom emoji.
    "modify": "<:name:1545577232922312734>",
}

SUGGESTIONS = {
    "upvote": "<:name:1558849951906136134>",
    "downvote": "<:name:1558850110014881922>",
    "remove": "<:name:1544996104511430736>",
    "total": "<:name:1545579981030162432>",
    "time": "<:name:1566453777131774022>",
    "footer_left": "<:name:1545831836339409048>",
    "suggestion": "<:name:1544996395373559869>",
    "submitted": "<:name:1566133385254928504>",
    "bullet": "<:name:1545576267904974859>",
}

# Not present in the original config — filled with sensible defaults,
# replace with your own custom emoji IDs if you have them.
REVIEWS = {
    "review": "<:name:1566447157165166714>",
    "star_filled": "<:name:1566447157165166714>",
    "star_empty": "<:name:1566448350205837472>",
    "user": "<:name:1547475085588303943>",
    "comment": "<:name:1544996395373559869>",
    "date": "<:name:1547464754593796106>",
    "bullet": "<:name:1545576267904974859>",
    "make_review": "<:name:1557703805041119304>",
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

APPLICATIONS = {
    # Developer Application panel (from the DWEEB design)
    "title": "<:name:1563918477746503830>",
    "info": "<:name:1545576267904974859>",
    "process": "<:name:1545579981030162432>",
    "step": "<a:name:1545552914334875800>",
    "disclaimer": "<:name:1563933758824914965>",
    "apply": "<:name:1563918477746503830>",
    "footer": "<:name:1545831836339409048>",
    # Buttons — reusing existing emoji, replace the IDs with your own if you want.
    "yes": "<:name:1544994894370578474>",
    "no": "<:name:1545364084499808256>",
    "send": "<a:name:1545552914334875800>",
    "accept": "<:name:1544994894370578474>",
    "deny": "<:name:1545364084499808256>",
    "close": "<:name:1545364084499808256>",
    "ping": "<:name:1545365144538718260>",
}

INFO = {
    "title": "<:name:1566461391878095091>",
    "note": "<:name:1566128213858459848>",
    "tos": "<:name:1566484047943704656>",
    "privacy": "<:name:1566484521073905824>",
    "faq": "<:name:1548740498603122788>",
    "footer": "<:name:1545831836339409048>",
    "footer_right": "<:name:1545576267904974859>",
}

# Invites system. Defaults reuse existing server emoji so it works right away;
# replace any ID with your own custom emoji ('<:name:ID>' or '<a:name:ID>').
INVITES = {
    "title": "<:name:1545578059820826745>",
    "panel_info": "<:name:1566461391878095091>",
    "my_invites": "<:name:1566133385254928504>",
    "leaderboard": "<:name:1545576883536793621>",
    "joins": "<:name:1545363231181381642>",
    "left": "<:name:1545363295467470908>",
    "remaining": "<:name:1566133385254928504>",
    "rank": "<:name:1545578059820826745>",
    "first": "<:name:1559959698554228827>",
    "second": "<:name:1559959731634962464>",
    "third": "<:name:<:3rd:1559959755978571846>>",
    "bullet": "<:name:1545576267904974859>",
    "footer": "<:name:1545831836339409048>",
    "log_join": "<:name:1545363231181381642>",
    "log_leave": "<:name:1545363295467470908>",
    "user": "<:name:1566133385254928504>",
    "inviter": "<:name:1545550175953494187>",
}

_CATEGORIES = {
    "invites": INVITES,
    "info": INFO,
    "applications": APPLICATIONS,
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
