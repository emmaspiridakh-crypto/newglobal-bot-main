GENERAL = {
    "purchase": "<:name:1548349993830850713>",
    "order": "<:name:1545578583332757665>",
    "close": "<:name:1566453862343385289>",
    "claim": "<:name:1566450319351611504>",
    "ping": "<:name:1566453919842836520>",
    "transcript": "<:name:1545576883536793621>",
    "bot": "<:name:1545576824380067860>",
    "budget": "<:name:1548349637918728232>",
    "payment": "<:name:1545553195760099358>",
    "log_open": "<a:name:1544996079626362920>",
    "place_order": "<a:name:1545552914334875800>",
    "order_accept": "<:name:1545577943953186816>",
    "order_done": "<:name:1544994894370578474>",
    "order_cancel": "<:name:1566453862343385289>",
    "order_pending": "<a:name:1548350905802424441>",
    "check": "<:name:1544994894370578474>",
    "cancel": "<:name:1544994871369273424>",
    "send": "<a:name:1545552914334875800>",
    "plan": "<:name:1566453662937649182>",
    "server": "<:name:1545579981030162432>",
    "modify": "<:name:1566127862657060894>",
}

SUGGESTIONS = {
    "upvote": "<:name:1558849951906136134>",
    "downvote": "<:name:1558850110014881922>",
    "remove": "<:name:1544996104511430736>",
    "total": "<:name:1545579981030162432>",
    "time": "<:name:1566453740343394456>",
    "footer_left": "<:name:1545831836339409048>",
    "suggestion": "<:name:1566453702900973578>",
    "submitted": "<:name:1566133385254928504>",
    "bullet": "<:name:1545576267904974859>",
}

REVIEWS = {
    "review": "<:name:1566447157165166714>",
    "star_filled": "<:name:1566447157165166714>",
    "star_empty": "<:name:1566448350205837472>",
}

GIVEAWAY = {
    "giveaway": "<:name:1566492002965528587>",
    "join": "<:name:1545363231181381642>",
    "leave": "<:name:1545363295467470908>",
    "info": "<:name:1566461429903790241>",
    "edit": "<:name:1566127862657060894>",
    "reroll": "<:name:1548741673109037116>",
    "end": "<:name:1566453862343385289>",
    "participants": "<:name:1566133385254928504>",
    "winner": "<:name:1547466980506738779>",
    "prize": "<:name:1547458529089290290>",
    "host": "<:name:1545576744956727306>",
    "winners_count": "<:name:1557694211602513950>",
    "entries": "<:name:1545363231181381642>",
    "time": "<:name:1566492002965528587>",
    "role": "<:name:1566133385254928504>",
    "add_member": "<:name:1544996128809029702>",
}

APPLICATIONS = {
    "yes": "<:name:1544994894370578474>",
    "no": "<:name:1544994871369273424>",
    "send": "<a:name:1545577943953186816>",
    "accept": "<:name:1566450319351611504>",
    "deny": "<:name:1566450266469961778>",
    "close": "<:name:1566453823189418146>",
    "ping": "<:name:1566453919842836520>",
}

INFO = {
    "title": "<:name:1566461391878095091>",
    "note": "<a:name:1545552914334875800>",
    "tos": "<:name:1566484047943704656>",
    "privacy": "<:name:1566484521073905824>",
    "faq": "<:name:1548740498603122788>",
    "footer": "<:name:1545831836339409048>",
    "footer_right": "<:name:1545576267904974859>",
}

INVITES = {
    "title": "<a:name:1545548139203919934>",
    "panel_info": "<:name:1566461391878095091>",
    "my_invites": "<:name:1566133385254928504>",
    "leaderboard": "<:name:1568643002715344907>",
    "joins": "<:name:1545363231181381642>",
    "left": "<:name:1545363295467470908>",
    "remaining": "<:name:1568643933452632214>",
    "rank": "<:name:1557694211602513950>",
    "first": "<:name:1559959698554228827>",
    "second": "<:name:1559959731634962464>",
    "third": "<:name:1559959755978571846>",
    "bullet": "<:name:1545576267904974859>",
    "footer": "<:name:1545831836339409048>",
    "log_join": "<:name:1545363231181381642>",
    "log_leave": "<:name:1545363295467470908>",
    "user": "<:name:1548353089927512135>",
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

EMOJI: dict = GENERAL


def emoji(category: str, key: str) -> str:
    return _CATEGORIES.get(category, {}).get(key, "")
