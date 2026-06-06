"""Team-name matching between The Odds API and the MLB Stats API.

Both feeds mostly use full team names, but a handful differ (the MLB Stats API
sometimes returns a bare nickname like "Athletics" / "Red Sox", while The Odds
API tends to use "Oakland Athletics" / "Boston Red Sox"). The Athletics are the
gnarliest case: after leaving Oakland the franchise has been listed as
"Athletics", "Oakland Athletics", and Sacramento/Las Vegas variants.

We solve this by normalizing every name to a canonical *nickname-based* key.
Matching is done on the unique nickname (e.g. "red sox" vs "white sox"), which
also disambiguates same-city clubs (Cubs/White Sox, Yankees/Mets,
Angels/Dodgers). Standard library only.
"""
from __future__ import annotations

import re
from typing import Dict, List

# --- the 30 current franchises: canonical key -> display name ----------------
# The key is the unique, punctuation-free nickname (spaces -> underscores). The
# controller can iterate this to sanity-check that every team it sees resolves.
CANONICAL_TEAMS: Dict[str, str] = {
    "diamondbacks": "Arizona Diamondbacks",
    "braves": "Atlanta Braves",
    "orioles": "Baltimore Orioles",
    "red_sox": "Boston Red Sox",
    "cubs": "Chicago Cubs",
    "white_sox": "Chicago White Sox",
    "reds": "Cincinnati Reds",
    "guardians": "Cleveland Guardians",
    "rockies": "Colorado Rockies",
    "tigers": "Detroit Tigers",
    "astros": "Houston Astros",
    "royals": "Kansas City Royals",
    "angels": "Los Angeles Angels",
    "dodgers": "Los Angeles Dodgers",
    "marlins": "Miami Marlins",
    "brewers": "Milwaukee Brewers",
    "twins": "Minnesota Twins",
    "yankees": "New York Yankees",
    "mets": "New York Mets",
    "athletics": "Athletics",
    "phillies": "Philadelphia Phillies",
    "pirates": "Pittsburgh Pirates",
    "padres": "San Diego Padres",
    "giants": "San Francisco Giants",
    "mariners": "Seattle Mariners",
    "cardinals": "St. Louis Cardinals",
    "rays": "Tampa Bay Rays",
    "rangers": "Texas Rangers",
    "blue_jays": "Toronto Blue Jays",
    "nationals": "Washington Nationals",
}

# --- aliases: every cleaned spelling we might see -> canonical key ------------
# Strings here are already in cleaned form (lowercase, punctuation -> space,
# single-spaced). City-only forms are included where unambiguous; same-city
# clubs only get their full or nickname form so they never collide.
_ALIAS_SOURCES: Dict[str, List[str]] = {
    "diamondbacks": [
        "arizona diamondbacks", "diamondbacks", "d backs", "dbacks",
        "arizona", "az diamondbacks", "ari",
    ],
    "braves": ["atlanta braves", "braves", "atlanta", "atl"],
    "orioles": ["baltimore orioles", "orioles", "baltimore", "bal", "os"],
    "red_sox": ["boston red sox", "red sox", "boston", "bosox", "bos"],
    "cubs": ["chicago cubs", "cubs", "chicago cubs cubs", "chc"],
    "white_sox": ["chicago white sox", "white sox", "chisox", "chw", "cws"],
    "reds": ["cincinnati reds", "reds", "cincinnati", "cin"],
    "guardians": [
        "cleveland guardians", "guardians", "cleveland",
        "cleveland indians", "indians", "cle",
    ],
    "rockies": ["colorado rockies", "rockies", "colorado", "col"],
    "tigers": ["detroit tigers", "tigers", "detroit", "det"],
    "astros": ["houston astros", "astros", "houston", "hou"],
    "royals": ["kansas city royals", "royals", "kansas city", "kc", "kcr"],
    "angels": [
        "los angeles angels", "la angels", "angels",
        "los angeles angels of anaheim", "anaheim angels", "laa",
    ],
    "dodgers": ["los angeles dodgers", "la dodgers", "dodgers", "lad"],
    "marlins": ["miami marlins", "marlins", "miami", "florida marlins", "mia"],
    "brewers": ["milwaukee brewers", "brewers", "milwaukee", "mil"],
    "twins": ["minnesota twins", "twins", "minnesota", "min"],
    "yankees": ["new york yankees", "ny yankees", "yankees", "nyy"],
    "mets": ["new york mets", "ny mets", "mets", "nym"],
    "athletics": [
        "athletics", "oakland athletics", "oakland", "oakland as",
        "sacramento athletics", "las vegas athletics", "athletics as",
        "as", "a s", "oak", "ath",
    ],
    "phillies": ["philadelphia phillies", "phillies", "philadelphia", "phils", "phi"],
    "pirates": ["pittsburgh pirates", "pirates", "pittsburgh", "pit"],
    "padres": ["san diego padres", "padres", "san diego", "sd", "sdp"],
    "giants": ["san francisco giants", "giants", "san francisco", "sf", "sfg"],
    "mariners": ["seattle mariners", "mariners", "seattle", "sea"],
    "cardinals": [
        "st louis cardinals", "saint louis cardinals", "cardinals",
        "st louis", "cards", "stl",
    ],
    "rays": [
        "tampa bay rays", "rays", "tampa bay", "tampa",
        "tampa bay devil rays", "devil rays", "tb", "tbr",
    ],
    "rangers": ["texas rangers", "rangers", "texas", "tex"],
    "blue_jays": ["toronto blue jays", "blue jays", "toronto", "jays", "tor"],
    "nationals": [
        "washington nationals", "nationals", "washington", "nats",
        "montreal expos", "expos", "wsh", "was",
    ],
}

# Reverse lookup built once at import time: cleaned string -> canonical key.
_ALIAS_TO_KEY: Dict[str, str] = {}
for _key, _aliases in _ALIAS_SOURCES.items():
    for _alias in _aliases:
        _ALIAS_TO_KEY[_alias] = _key

# Distinctive nickname phrases for substring fallback, longest first so that
# multi-word nicknames ("red sox", "white sox", "blue jays", "diamondbacks")
# win over any shorter token that might be a substring of them.
_NICKNAME_PHRASES: Dict[str, str] = {
    "diamondbacks": "diamondbacks",
    "braves": "braves",
    "orioles": "orioles",
    "red_sox": "red sox",
    "cubs": "cubs",
    "white_sox": "white sox",
    "reds": "reds",
    "guardians": "guardians",
    "rockies": "rockies",
    "tigers": "tigers",
    "astros": "astros",
    "royals": "royals",
    "angels": "angels",
    "dodgers": "dodgers",
    "marlins": "marlins",
    "brewers": "brewers",
    "twins": "twins",
    "yankees": "yankees",
    "mets": "mets",
    "athletics": "athletics",
    "phillies": "phillies",
    "pirates": "pirates",
    "padres": "padres",
    "giants": "giants",
    "mariners": "mariners",
    "cardinals": "cardinals",
    "rays": "rays",
    "rangers": "rangers",
    "blue_jays": "blue jays",
    "nationals": "nationals",
}
# (phrase, key) pairs sorted by phrase length, longest first.
_NICKNAME_FALLBACK: List[tuple] = sorted(
    ((phrase, key) for key, phrase in _NICKNAME_PHRASES.items()),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")


def _clean(name: str) -> str:
    """Lowercase, strip punctuation to spaces, and collapse whitespace."""
    s = (name or "").lower().strip()
    s = _NON_ALNUM.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def normalize_team(name: str) -> str:
    """Return a canonical nickname-based key for a team name.

    Resolves any spelling used by The Odds API or the MLB Stats API to the same
    key (e.g. "Oakland Athletics" and "Athletics" both -> "athletics"). Unknown
    names fall back to their cleaned form so identical strings still compare
    equal via :func:`same_team`.
    """
    cleaned = _clean(name)
    if not cleaned:
        return ""
    # 1) exact alias match (fast path, handles every known spelling).
    key = _ALIAS_TO_KEY.get(cleaned)
    if key is not None:
        return key
    # 2) distinctive-nickname substring fallback (longest phrase wins), so an
    #    unseen variant like "x red sox y" still resolves correctly.
    for phrase, k in _NICKNAME_FALLBACK:
        if phrase in cleaned:
            return k
    # 3) unknown team: return cleaned form so equal strings still match.
    return cleaned


def same_team(a: str, b: str) -> bool:
    """True iff the two names normalize to the same canonical key."""
    na = normalize_team(a)
    nb = normalize_team(b)
    return bool(na) and na == nb
