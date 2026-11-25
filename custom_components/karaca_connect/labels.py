"""Human-friendly names for the raw codes the Karaca Connect API returns.

The server sends compact lowercase codes such as "teabrewing" or "brewedfresh".
Only some of them have been observed; unknown codes are split into known words
where possible ("boilingdone" -> "Boiling done") and otherwise just capitalised,
so a new server value never breaks a sensor.
"""

from __future__ import annotations

import re

# Robotea modeName values (keys of detail.modes, lower-cased by the server).
MODE_NAMES = {
    "standby": "Standby",
    "off": "Off",
    "teabrewing": "Tea brewing",
    "boilingwater": "Boiling water",
    "filtercoffee": "Filter coffee",
    "babyfood": "Baby food",
    "herbaltea": "Herbal tea",
    "kettlemode": "Kettle",
    "kettle": "Kettle",
    "schedule": "Schedule",
}

# Robotea modeStateLabel values seen live (with the app's Turkish status text).
MODE_STATE_NAMES = {
    "off": "Off",  # modeState 0, "Kapalı"
    "waterboiling": "Water boiling",  # 1, "Su Kaynıyor"
    "brewing": "Brewing",  # 3, "Çay Demleniyor"
    "brewedfresh": "Fresh",  # 4, "Çayınız Taze" - tea is fresh, freshness countdown running
    "brewedstale": "Stale",  # 5, "Çay Bayatladı" - freshness window has ended
}

# Notification wording per stepView.id ("<mode>_<state>"), as observed on a Robotea Pro 4in1.
STEP_MESSAGES = {
    "teabrewing_waterboiling": "water is boiling for tea",
    "teabrewing_brewing": "tea brewing started",
    "teabrewing_brewedfresh": "tea is brewed",
    "teabrewing_brewedstale": "tea is no longer fresh",
    "standby_off": "off",
}

# Vocabulary for splitting unknown run-together codes, longest match first.
_WORDS = sorted(
    {
        "baby", "boiled", "boiling", "brewed", "brewing", "coffee", "completed", "cooking",
        "cooling", "done", "empty", "filling", "filter", "finished", "food", "fresh", "heating",
        "herbal", "idle", "kettle", "keep", "mode", "off", "on", "paused", "preheat",
        "preheating", "prepared", "preparing", "ready", "stale", "standby", "started",
        "stopped", "tea", "waiting", "warm", "warming", "water",
    },
    key=len,
    reverse=True,
)


def humanize(code: str | None) -> str | None:
    """Turn an unknown API code into readable text without guessing its meaning."""
    if code is None:
        return None
    text = str(code).strip()
    if not text:
        return None
    # snake_case / kebab-case / UPPER_CASE
    if re.search(r"[_\-\s]", text) or text.isupper():
        words = [w for w in re.split(r"[_\-\s]+", text.lower()) if w]
        return " ".join(words).capitalize()
    # camelCase
    if re.search(r"[a-z][A-Z]", text):
        return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text).capitalize()
    # runtogether lowercase: greedy split into known words, only if it fully splits
    lower = text.lower()
    words: list[str] = []
    i = 0
    while i < len(lower):
        match = next((w for w in _WORDS if lower.startswith(w, i)), None)
        if match is None:
            return text.capitalize()
        words.append(match)
        i += len(match)
    return " ".join(words).capitalize()


def mode_name(code: str | None) -> str | None:
    if code is None:
        return None
    return MODE_NAMES.get(str(code).lower()) or humanize(code)


def mode_state_name(code: str | None) -> str | None:
    if code is None:
        return None
    return MODE_STATE_NAMES.get(str(code).lower()) or humanize(code)
