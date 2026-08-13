"""Tool implementations + their Ollama/OpenAI-style function-calling schemas.

get_weather and get_stock are ported from agent_jarvis/tools/weather.py and
agent_jarvis/tools/stock.py unchanged. search_web replaces the LangChain
TavilySearchResults wrapper with a direct tavily-python call. get_home_state,
list_devices and control_device are new: get_home_state/list_devices let the model
discover exact entity_ids, and control_device acts on those ids via direct service
calls - no natural-language round trip through HA's own NLU, which was lossy and
required Assist exposure to be configured.
"""
from __future__ import annotations

import logging
import random
import re

import requests
import yfinance as yf
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Every outbound network call needs an explicit bound. These run in executor
# threads, so one that never returns hangs the turn silently - the voice pipeline
# sits on "processing" forever with nothing in the log to explain it.
SEARCH_TIMEOUT_SECONDS = 15
STOCK_TIMEOUT_SECONDS = 10

# The assistant key HA records exposure under for voice/conversation.
_ASSISTANT = "conversation"


def is_exposed(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether voice is allowed to see/touch this entity.

    Exposure is the single source of truth for both tiers. HA's built-in agent
    already honours it, but hass.states and hass.services do not - so without
    this check the LLM path could still read and actuate entities deliberately
    hidden from voice. That gap is not theoretical: the 3D printers' cooling and
    chamber fans are hidden precisely so a bulk "turn everything off in the lab"
    can't kill an in-progress print, and an unfiltered LLM path would walk
    straight around that protection.
    """
    try:
        from homeassistant.components.homeassistant.exposed_entities import (
            async_should_expose,
        )
    except ImportError:  # pragma: no cover - core component, but fail safe
        _LOGGER.warning("Exposure helper unavailable; treating entities as exposed")
        return True
    try:
        return async_should_expose(hass, _ASSISTANT, entity_id)
    except Exception:  # noqa: BLE001 - never let a lookup error unblock actuation
        _LOGGER.exception("Exposure check failed for %s; treating as hidden", entity_id)
        return False

SYMBOL_MAP = {
    "tesla": "TSLA",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "google": "GOOG",
    "alphabet": "GOOG",
    "meta": "META",
    "facebook": "META",
    "amazon": "AMZN",
    "netflix": "NFLX",
    "intel": "INTC",
    "paypal": "PYPL",
    "amd": "AMD",
    "qualcomm": "QCOM",
}


# HA's condition slugs are single words ("partlycloudy") that get read aloud as
# one mangled word by TTS. Spelled out for speech.
_WEATHER_CONDITIONS = {
    "clear-night": "clear",
    "partlycloudy": "partly cloudy",
    "lightning-rainy": "thunderstorms",
    "lightning": "thunderstorms",
    "snowy-rainy": "sleet",
    "pouring": "pouring rain",
    "windy-variant": "windy",
    "exceptional": "unusual weather",
}


def get_weather(hass: HomeAssistant, location: str | None = None) -> str:
    """Home weather from HA's own forecast entity; other cities via wttr.in.

    HA already has a weather entity configured for this house's exact
    coordinates, so for "what's the weather" it is both authoritative and free.
    Going out to wttr.in with a city name instead produced answers that were
    simply wrong - 80F and raining, then 88F and sunny, minutes apart, while HA
    itself reported 84F partly cloudy - because the model has no reliable idea
    which city it is in and the two sources disagree anyway. Reading the local
    entity also makes this answer identical to the one tier 1 gives.
    """
    if not location:
        weather_states = [
            s for s in hass.states.async_all("weather")
            if s.state not in ("unknown", "unavailable")
        ]
        if weather_states:
            state = weather_states[0]
            temp = state.attributes.get("temperature")
            unit = state.attributes.get("temperature_unit", "")
            condition = _WEATHER_CONDITIONS.get(
                state.state, state.state.replace("-", " ").replace("_", " ")
            )
            parts = [f"{temp}{unit}" if temp is not None else "", condition]
            humidity = state.attributes.get("humidity")
            wind = state.attributes.get("wind_speed")
            extra = []
            if humidity is not None:
                extra.append(f"{humidity}% humidity")
            if wind is not None:
                extra.append(f"wind {wind} {state.attributes.get('wind_speed_unit', '')}".strip())
            summary = " and ".join(p for p in parts if p)
            if extra:
                summary += f" ({', '.join(extra)})"
            return f"Currently {summary} at home."

    # Only reached for an explicitly named city, or if no weather entity exists.
    try:
        response = requests.get(f"https://wttr.in/{location or 'Allentown'}?format=j1", timeout=5)
        data = response.json()
        current = data["current_condition"][0]
        temp_f = current["temp_F"]
        desc = current["weatherDesc"][0]["value"]
        return f"It's currently {temp_f}°F and {desc.lower()} in {location}."
    except Exception as err:
        _LOGGER.warning("Weather lookup failed: %s", err)
        return "Sorry, I couldn't fetch the weather right now."


def get_stock(symbol: str = "TSLA") -> str:
    try:
        symbol = SYMBOL_MAP.get(symbol.lower(), symbol.upper())
        stock = yf.Ticker(symbol)
        # Bounded for the same reason as search_web: unbounded network calls run
        # in an executor thread and can hang a turn indefinitely.
        data = stock.history(period="1d", timeout=STOCK_TIMEOUT_SECONDS)
        if data.empty:
            return f"Couldn't find stock data for {symbol}."

        latest = data.iloc[-1]
        price = latest["Close"]
        change = latest["Close"] - latest["Open"]
        change_percent = (change / latest["Open"]) * 100
        direction = "up" if change > 0 else "down" if change < 0 else "unchanged"
        return f"{symbol} is at ${price:.2f}, {direction} {abs(change_percent):.2f}% today."
    except Exception as err:
        _LOGGER.warning("Stock lookup failed: %s", err)
        return "Couldn't fetch stock data right now, sir."


def search_web(query: str, api_key: str) -> str:
    try:
        # Called against Tavily's REST endpoint rather than the SDK so the request
        # carries an explicit timeout. This runs in an executor thread, and the SDK
        # exposes no timeout parameter: a hung search blocked the entire turn with
        # no error and no log line, leaving the voice pipeline "processing"
        # indefinitely instead of failing audibly.
        #
        # include_answer is what makes this usable for factual questions. Without
        # it Tavily returns raw page snippets - for "who won the most recent Super
        # Bowl" those were truncated Wikipedia tables that never stated a winner,
        # so the model found nothing to work with and fell back to its (wrong,
        # years-stale) training answer. The synthesized answer states it outright.
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": 3,
                "include_answer": True,
                "search_depth": "advanced",
            },
            timeout=SEARCH_TIMEOUT_SECONDS,
        ).json()
        answer = (response.get("answer") or "").strip()
        results = response.get("results", [])
        if not answer and not results:
            return f"I couldn't find anything useful on '{query}'."

        # When Tavily synthesizes an answer, return ONLY that. Appending the raw
        # snippets alongside it actively hurt: asked who won the most recent Super
        # Bowl, the model ignored the answer line, latched onto a scraped
        # all-time-wins table in the snippets, and confidently answered a question
        # nobody asked ("the Patriots have won the most, with 6"). A 7B model
        # follows the loudest text in context, so don't put competing text there.
        if answer:
            return answer
        return "\n\n".join(
            f"Title: {r.get('title', '')}\nContent: {r.get('content', '')}"
            for r in results
        )
    except Exception as err:
        _LOGGER.warning("Web search failed: %s", err)
        return "Sorry, the web search didn't come back with anything."


# Domains that are essentially never the answer to a status question - excluding
# these keeps diagnostic/config noise (retry limits, firmware update entities, etc.)
# from crowding out the entities that actually matter in a limited result set.
_NOISE_DOMAINS = {"number", "button", "update", "select"}

# Query keywords mapped to binary_sensor/cover device_classes that answer them, so a
# search for "window" also surfaces entities named nothing like "window" (e.g.
# "philio_multi_sensor_window_door_is_open") as long as they're typed correctly.
_DEVICE_CLASS_HINTS = {
    "window": {"window", "door", "opening"},
    "door": {"door", "garage_door", "opening", "lock"},
    "lock": {"lock"},
    "locked": {"lock"},
    "motion": {"motion", "occupancy"},
    "leak": {"moisture"},
    "water": {"moisture"},
    "smoke": {"smoke"},
    "temperature": {"temperature"},
    "open": {"window", "door", "garage_door", "opening"},
}
# Deliberately NOT in the map above: words like "garage" that are locations in
# THIS house, not device-type concepts. Mapping "garage" -> garage_door/door/opening
# used to mean any door-class entity in the whole house (including an entirely
# unrelated 3D printer's own enclosure door, which is also device_class=door)
# would match a "garage" query with no way to prefer the actually-relevant one.
# Location words are handled by the area-aware name matching below instead.

# Stripped before matching regardless of what the model actually sends as the query
# (the tool description asks for bare keywords, but that's not reliably followed) -
# "is the garage open" needs to behave like "garage open", since "is"/"the" will
# essentially never appear in an entity's name/id and would otherwise force every
# query containing them down the noisier device_class-only fallback path.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "am", "be", "been", "being",
    "any", "some", "please", "can", "you", "could", "would", "will", "to", "of",
    "in", "on", "at", "for", "and", "or", "what", "whats", "what's", "how",
    "check", "tell", "me", "my", "there", "it", "its", "it's",
}


# Domains that can actually be acted on. Anything else reports state and has no
# actuator, so offering to change it is always wrong. The model has repeatedly
# volunteered impossible actions ("shall I pause the print?" when every printer
# control is hidden from voice; offering to close a window that is only a contact
# sensor), so entities are labelled read-only in the tool output itself rather
# than relying on the prompt to discourage it.
_ACTIONABLE_DOMAINS = {
    "light", "switch", "fan", "climate", "cover", "lock", "media_player",
    "vacuum", "humidifier", "water_heater", "script", "scene", "automation",
    "input_boolean", "input_number", "input_select", "siren", "valve",
}


def _is_actionable(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether voice can change this entity, as opposed to only read it."""
    domain = entity_id.split(".", 1)[0]
    if domain not in _ACTIONABLE_DOMAINS:
        return False
    # Exposure is the other half: a hidden entity is read-only as far as the
    # model is concerned, so it must not be offered as something to control.
    return is_exposed(hass, entity_id)


# (on_meaning, off_meaning) per binary_sensor device_class, mirroring the wording
# Home Assistant's own UI uses. Anything not listed keeps raw on/off, which is
# already unambiguous for those classes.
_BINARY_MEANINGS = {
    "door": ("open", "closed"),
    "garage_door": ("open", "closed"),
    "window": ("open", "closed"),
    "opening": ("open", "closed"),
    "lock": ("unlocked", "locked"),
    "motion": ("motion detected", "no motion"),
    "occupancy": ("occupied", "clear"),
    "presence": ("home", "away"),
    "moisture": ("wet - leak detected", "dry"),
    "smoke": ("smoke detected", "clear"),
    "gas": ("gas detected", "clear"),
    "carbon_monoxide": ("CO detected", "clear"),
    "heat": ("too hot", "normal"),
    "cold": ("too cold", "normal"),
    "problem": ("problem detected", "OK"),
    "safety": ("unsafe", "safe"),
    "tamper": ("tampered", "clear"),
    "battery": ("low battery", "battery OK"),
    "connectivity": ("connected", "disconnected"),
    "running": ("running", "not running"),
    "update": ("update available", "up to date"),
    "vibration": ("vibration detected", "clear"),
    "sound": ("sound detected", "clear"),
    "power": ("power detected", "no power"),
    "plug": ("plugged in", "unplugged"),
}


def _humanize_state(state) -> str:
    """Render a raw state into something the model can't misread.

    Two failure modes seen in practice, both from handing raw values to a 7B model
    and hoping it converts correctly:
      - "0.0833333333333333" with unit "h" was reported as "about an hour left"
        when it actually meant five minutes.
      - A UTC timestamp "2026-08-12T22:28:00+00:00" was read out as "10:28 PM"
        with no timezone conversion; locally that is 6:28 PM. This affects every
        timestamp sensor in the house, not just the printer.
    Converting here means the model never sees the ambiguous form.
    """
    raw = state.state
    if raw in ("unknown", "unavailable", "", None):
        return str(raw)

    unit = state.attributes.get("unit_of_measurement") or ""
    device_class = state.attributes.get("device_class", "")

    # Binary sensors: "on"/"off" carries opposite meanings depending on device
    # class, and the model guessed the polarity wrong - it reported the garage
    # door as CLOSED when garage_intrusion was "on", which for device_class
    # garage_door means OPEN. Resolving to the word HA itself would display
    # removes the guess entirely.
    if state.entity_id.startswith("binary_sensor.") and raw in ("on", "off"):
        words = _BINARY_MEANINGS.get(device_class)
        if words:
            return f"{words[0] if raw == 'on' else words[1]} (raw: {raw})"

    # Durations: express small fractional hours/minutes in whole minutes.
    if unit in ("h", "min"):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return raw
        minutes = value * 60 if unit == "h" else value
        if minutes <= 0:
            # Zero means finished/idle, not "almost done" - glossing it as "less
            # than a minute" made the model describe a completed print as still
            # having time left.
            return f"{raw} {unit} (none remaining)"
        if minutes < 1:
            return f"{raw} {unit} (less than a minute)"
        if minutes < 90:
            return f"{raw} {unit} ({round(minutes)} minutes)"
        hours, rem = divmod(round(minutes), 60)
        return f"{raw} {unit} ({hours}h {rem}m)"

    # Timestamps: append the local-time rendering the user actually means.
    if state.attributes.get("device_class") == "timestamp" or _ISO_TS.match(str(raw)):
        try:
            parsed = dt_util.parse_datetime(str(raw))
            if parsed is not None:
                local = dt_util.as_local(parsed)
                return f"{raw} (local time: {local.strftime('%-I:%M %p on %A')})"
        except Exception:  # noqa: BLE001 - never let formatting break a lookup
            return raw
    return raw


_ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _term_matches(term: str, haystack: str) -> bool:
    """Match a query term against whole tokens, not raw substrings.

    A plain `term in haystack` matched coincidental fragments inside unrelated
    identifiers: asking about the "P1S" printer pulled in a Ring motion sensor
    because its model number is 4SP1SZ, which contains "p1s". The model then
    reported on that sensor as if it were relevant to the printer.

    Tokenizing on non-alphanumerics keeps the useful behaviour - "garage" still
    matches binary_sensor.garage_intrusion, since "_" and "." are separators -
    while a fragment buried mid-token no longer counts.

    Matching is whole-token only, deliberately. Allowing prefixes ("temp" finding
    "temperature") also made "open" match "opener", so a garage-door question
    pulled in switch.garage_opener and the answer drifted onto the relay instead
    of the door sensor. Semantic near-misses are already covered by
    _DEVICE_CLASS_HINTS, which is the right mechanism for them.
    """
    return any(token == term for token in _TOKEN_SPLIT.split(haystack) if token)


_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def get_home_state(hass: HomeAssistant, query: str, limit: int = 25) -> str:
    """Search entities by name/id/device_class and return their live state directly.

    HA's built-in conversation agent (the tier-1 fast path) can only answer status
    questions for entities whose device_class matches its intent templates exactly -
    a binary_sensor with device_class "safety" won't match its "is X open" intent
    even if that's what the sensor represents in practice. Since this integration
    runs in-process inside Home Assistant, it can read any entity's live state
    directly via hass.states and let the model reason about it, sidestepping that
    limitation entirely. Use this for status/state questions, and to resolve exact
    entity_ids to hand to control_device for actions.
    """
    query_terms = [term for term in query.lower().split() if term not in _STOPWORDS] or query.lower().split()
    relevant_classes: set[str] = set()
    for term in query_terms:
        # Naive singularization: the model may pass "windows"/"doors"/"locks" while
        # the hint map is keyed on the singular form.
        for candidate in (term, term[:-1] if term.endswith("s") else term):
            relevant_classes |= _DEVICE_CLASS_HINTS.get(candidate, set())

    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    full_matches = []  # class_ok AND every query term present
    partial_matches = []  # (state, overlap_score) - class_ok OR at least one term present
    for state in hass.states.async_all():
        domain = state.entity_id.split(".", 1)[0]
        if domain in _NOISE_DOMAINS:
            continue
        # Filtered here rather than only at actuation time so the model never even
        # learns a hidden entity exists - otherwise it will happily narrate plans
        # involving entities it is not permitted to touch.
        if not is_exposed(hass, state.entity_id):
            continue
        device_class = state.attributes.get("device_class", "")

        # device_class is part of the searchable text so semantic matches rank
        # above coincidental ones: for "garage door open", garage_intrusion
        # (device_class=garage_door) matches both words, while front_door_intrusion
        # only matches "door" - previously they tied and the front door won on
        # iteration order alone.
        haystack = f"{state.entity_id} {state.name} {device_class}".lower()
        entity_entry = entity_reg.async_get(state.entity_id)
        area_id = None
        if entity_entry:
            area_id = entity_entry.area_id
            if entity_entry.device_id:
                device = device_reg.async_get(entity_entry.device_id)
                if device:
                    haystack += f" {device.name or ''} {device.manufacturer or ''} {device.model or ''}".lower()
                    area_id = area_id or device.area_id
        if area_id:
            area = area_reg.async_get_area(area_id)
            if area:
                haystack += f" {area.name}".lower()

        class_ok = device_class in relevant_classes
        overlap_score = sum(1 for term in query_terms if _term_matches(term, haystack))
        name_ok = overlap_score == len(query_terms)

        if class_ok and name_ok:
            full_matches.append(state)
        elif class_ok or overlap_score > 0:
            partial_matches.append((state, overlap_score, class_ok))

    # Entities satisfying BOTH the device_class hint and every query term by name/area
    # are trusted exclusively when any exist - e.g. "bedroom temperature" needs an
    # entity that's both device_class=temperature AND actually associated with
    # "bedroom", not just any temperature sensor in the house (which previously
    # included a 3D printer's print-bed temperature - "bed" was enough to slip
    # through as a false positive here, so mixing in weaker matches even when this
    # tier already has a confident answer would reintroduce that same noise).
    #
    # Otherwise, fall back to every entity with at least some relevance (device_class
    # match and/or partial name overlap), ranked by how relevant it actually is
    # rather than left unordered. class_ok is the PRIMARY sort key, not overlap_score:
    # for "garage open", switch.garage_opener has a higher raw overlap_score than
    # garage_intrusion (its name coincidentally contains both "garage" AND "open",
    # since "open" is a substring of "opener") but isn't actually the right kind of
    # entity to answer a status question - being device_class=garage_door and thus
    # semantically an actual position sensor matters more than incidental text
    # overlap, so that has to be checked first, with overlap_score only breaking
    # ties among entities that are equally class-relevant (or equally not).
    if full_matches:
        matches = full_matches
    else:
        partial_matches.sort(key=lambda item: (item[2], item[1]), reverse=True)
        matches = [state for state, _score, _class_ok in partial_matches]

    if not matches:
        return f"No entities found matching '{query}'."

    lines = []
    any_readonly = False
    for state in matches[:limit]:
        device_class = state.attributes.get("device_class", "")
        dc_note = f" (device_class={device_class})" if device_class else ""
        readable = _humanize_state(state)
        # Rendered as a data field alongside device_class rather than a prose label
        # like [READ-ONLY]. A warning-shaped marker invited the model to explain it
        # to the user ("since it's a read-only sensor, we can't check it" - said
        # immediately after checking it); an attribute reads as metadata to skip.
        if _is_actionable(hass, state.entity_id):
            attrs = dc_note
        else:
            attrs = f"{dc_note[:-1]}, control=none)" if dc_note else " (control=none)"
            any_readonly = True
        lines.append(f"{state.entity_id} [{state.name}]{attrs}: {readable}")

    note = f"\n({len(matches) - limit} more matches not shown)" if len(matches) > limit else ""
    if any_readonly:
        note += (
            "\n(control=none means that entity reports state but cannot be changed. "
            "Report its value normally and don't offer to act on it. This is metadata "
            "for you, not something to mention or explain to the user.)"
        )
    return "\n".join(lines) + note


def list_devices(hass: HomeAssistant) -> str:
    """List every physical device's name/manufacturer/model/area.

    Fallback for when get_home_state finds nothing: a query like "3D printer" will
    never keyword-match a device named "X1C Genie" by "Bambu Lab" - there's no
    literal overlap. Rather than hardcoding an ever-growing synonym dictionary for
    every possible device type (which doesn't scale to new devices added later),
    this hands the model the raw device list so it can use its own knowledge (e.g.
    recognizing Bambu Lab makes 3D printers) to find the right one, then call
    get_home_state again with that device's actual name to read its entities. This
    is what makes adding new devices in HA require zero code changes here.
    """
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    lines = []
    for device in device_reg.devices.values():
        name = device.name_by_user or device.name
        if not name:
            continue
        area_name = ""
        if device.area_id:
            area = area_reg.async_get_area(device.area_id)
            area_name = area.name if area else ""
        parts = [name]
        if device.manufacturer:
            parts.append(f"by {device.manufacturer}")
        if device.model:
            parts.append(f"({device.model})")
        if area_name:
            parts.append(f"in {area_name}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


# Spoken acknowledgements for tier-1 hits. HA's own reply ("Turned on light.lab")
# is accurate but flat, and routing it through the LLM purely to add personality
# would give back all the latency tier 1 exists to save. Picking from a list costs
# nothing and keeps the character intact.
_ACK_PHRASES = (
    "Done.",
    "Consider it handled.",
    "As you wish.",
    "Already done.",
    "Of course.",
    "Taken care of.",
)

# Questions whose answer moves with time. The model has repeatedly answered these
# from training data with full confidence (insisting the most recent Super Bowl was
# in 2022), and instructing it to search first did not change that - so the caller
# searches on its behalf instead of asking it to choose correctly.
_RECENCY = re.compile(
    r"\b(?:who won|most recent|latest|newest|this year|last year|nowadays|"
    r"currently (?:the|in)|news|headlines|score|released|came? out|"
    r"who is the (?:president|prime minister|ceo)|stock price|how much is)\b",
    re.IGNORECASE,
)

# Terms that mean the question is about this house, where a web search is useless
# noise - get_home_state answers those, and "what's the current temperature" must
# not be dragged off to the internet.
_HOME_CONTEXT = re.compile(
    r"\b(?:thermostat|temperature|humidity|door|window|light|lamp|fan|lock|locked|"
    r"garage|bedroom|kitchen|lab|office|printer|battery|sensor|open|closed|"
    r"turn on|turn off|upstairs|downstairs)\b",
    re.IGNORECASE,
)


def needs_fresh_information(text: str) -> bool:
    """Whether this question should be answered from a live web search."""
    return bool(_RECENCY.search(text)) and not _HOME_CONTEXT.search(text)


# "turn everything off in the lab" is the single most natural way to say this, but
# HA's built-in templates parse "everything" as a device NAME and return
# no_valid_targets. That dropped the phrase through to the LLM, which then claimed
# it had turned things off without ever calling a tool. Handling it deterministically
# here keeps it in tier 1, where it can't be hallucinated.
_AREA_BULK = re.compile(
    r"\b(?:turn|shut|switch|power)\s+"
    r"(?:(?P<a>on|off)\s+)?"
    r"(?:everything|all(?:\s+(?:the|my))?(?:\s+devices?|\s+lights?)?)"
    r"(?:\s+(?P<b>on|off))?"
    r"\b.*?\b(?:in|inside)\s+(?:the\s+)?(?P<area>.+?)\s*[.!?]*$",
    re.IGNORECASE,
)

# Domains a blanket "everything off" should act on. Deliberately excludes things
# where a blanket toggle is surprising or destructive (locks, covers, vacuums).
_BULK_DOMAINS = {"light", "switch", "fan", "media_player"}


async def try_area_bulk(hass: HomeAssistant, text: str) -> str | None:
    """Handle 'turn everything on/off in <area>'; None if it isn't that shape."""
    match = _AREA_BULK.search(text)
    if not match:
        return None
    action_word = match.group("a") or match.group("b")
    if not action_word:
        return None
    area_text = match.group("area").strip().lower()

    area_reg = ar.async_get(hass)
    area = None
    for candidate in area_reg.async_list_areas():
        names = {candidate.name.lower(), *(a.lower() for a in (candidate.aliases or ()))}
        if area_text in names or any(area_text == n for n in names):
            area = candidate
            break
    if area is None:
        return None

    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    targets = []
    for entry in entity_reg.entities.values():
        if entry.disabled_by or entry.hidden_by or entry.entity_category:
            continue
        if entry.entity_id.split(".", 1)[0] not in _BULK_DOMAINS:
            continue
        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = device_reg.async_get(entry.device_id)
            area_id = device.area_id if device else None
        if area_id != area.id:
            continue
        if not is_exposed(hass, entry.entity_id):
            continue  # honours the same hidden-from-voice rule as everywhere else
        if hass.states.get(entry.entity_id) is None:
            continue
        targets.append(entry.entity_id)

    if not targets:
        return None

    action = "turn_off" if action_word.lower() == "off" else "turn_on"
    _LOGGER.debug("Area bulk %s in %s -> %s", action, area.name, targets)

    # Report what actually succeeded, not what was attempted - claiming success for
    # a call that failed is precisely the behaviour this tier exists to eliminate,
    # and it would be no better coming from here than from the model.
    succeeded, failed, _blocked, fatal = await _apply_control(hass, targets, action)
    if fatal or not succeeded:
        _LOGGER.warning("Area bulk %s in %s failed: %s", action, area.name, fatal or failed)
        return f"I couldn't turn {action_word.lower()} anything in the {area.name}."

    noun = "thing" if len(succeeded) == 1 else "things"
    msg = (
        f"{random.choice(_ACK_PHRASES)} Turned {action_word.lower()} "
        f"{len(succeeded)} {noun} in the {area.name}."
    )
    if failed:
        msg += f" {len(failed)} wouldn't respond."
    return msg


async def try_builtin_intent(hass: HomeAssistant, text: str, language: str = "en") -> str | None:
    """Run HA's built-in intent matcher; return speech on a hit, None on a miss.

    Returning None (rather than an error string) is what lets the caller fall
    through to the LLM, so a template miss costs one cheap local match attempt
    and nothing else. agent_id is pinned to the built-in agent explicitly: this
    integration is itself the pipeline's default agent, so routing by default
    would recurse straight back into us.
    """
    from homeassistant.components import conversation as ha_conversation
    from homeassistant.helpers import intent as ha_intent

    try:
        result = await ha_conversation.async_converse(
            hass,
            text=text,
            conversation_id=None,
            context=None,
            language=language,
            agent_id="conversation.home_assistant",
        )
    except Exception as err:  # noqa: BLE001 - a tier-1 failure must never break the turn
        _LOGGER.debug("Built-in intent match unavailable, falling through to LLM: %s", err)
        return None

    response = result.response
    if response.response_type == ha_intent.IntentResponseType.ERROR:
        # Includes "no matching intent" and "no matching entity" - both mean the
        # LLM should get a chance, since it can search entities the templates miss.
        return None

    speech = response.speech.get("plain", {}).get("speech", "").strip()

    # An action that matched a sentence but touched no entity isn't a real hit;
    # fall through rather than cheerfully claiming success. Attribute name is
    # read defensively so a HA version rename degrades to "trust it" instead of
    # raising and killing the turn.
    if response.response_type == ha_intent.IntentResponseType.ACTION_DONE:
        succeeded = getattr(response, "success_results", None)
        if succeeded is not None and len(succeeded) == 0:
            return None
        return f"{random.choice(_ACK_PHRASES)}{' ' + speech if speech else ''}".strip()

    if speech:
        return speech
    return None


# Actions the model may request, mapped to the service each domain actually
# implements. Most domains use the generic turn_on/turn_off/toggle, but covers
# and locks have their own verbs, hence the per-domain overrides.
_ACTION_SERVICES = {
    "turn_on": "turn_on",
    "turn_off": "turn_off",
    "toggle": "toggle",
    "open": "open_cover",
    "close": "close_cover",
    "lock": "lock",
    "unlock": "unlock",
}

# Params the model may pass, mapped to the service-data key HA expects. Anything
# not listed here is dropped rather than forwarded, so a hallucinated key can't
# turn into an invalid service call.
_PARAM_KEYS = {
    "temperature": "temperature",
    "brightness": "brightness_pct",
    "brightness_pct": "brightness_pct",
    "position": "position",
    "color_temp": "color_temp_kelvin",
    # "set the bedroom climate to cool" needs set_hvac_mode; without these the
    # request had nowhere to go at all. preset_mode is included because the model
    # reaches for it by name even when the value is really an hvac mode.
    "hvac_mode": "hvac_mode",
    "mode": "hvac_mode",
    "preset_mode": "preset_mode",
    "fan_mode": "fan_mode",
}

# set_temperature/set_position aren't turn_on-style verbs; they're their own
# services on their own domains.
_PARAM_SERVICES = {
    "temperature": ("climate", "set_temperature"),
    "brightness": ("light", "turn_on"),
    "brightness_pct": ("light", "turn_on"),
    "position": ("cover", "set_cover_position"),
    "color_temp": ("light", "turn_on"),
    "hvac_mode": ("climate", "set_hvac_mode"),
    "mode": ("climate", "set_hvac_mode"),
    "preset_mode": ("climate", "set_preset_mode"),
    "fan_mode": ("climate", "set_fan_mode"),
}

# HVAC modes accepted as a bare action ("action": "cool") rather than a param,
# since that is how the request is phrased and how the model tends to send it.
_HVAC_MODES = {"cool", "heat", "heat_cool", "auto", "dry", "fan_only"}


async def _apply_control(
    hass: HomeAssistant,
    entity_ids: list[str] | str,
    action: str,
    params: dict | None = None,
) -> tuple[list[str], list[str], list[str], str | None]:
    """Do the actuation. Returns (succeeded, failed, blocked, fatal_error).

    Split from control_device so callers that need counts (try_area_bulk) can use
    the real outcome instead of re-parsing a human-readable sentence.
    """
    if isinstance(entity_ids, str):
        # Models frequently send a bare string or a comma-joined list despite the
        # array schema; accept both rather than failing the whole turn.
        entity_ids = [e.strip() for e in entity_ids.split(",") if e.strip()]
    entity_ids = [e for e in entity_ids if isinstance(e, str) and "." in e]
    if not entity_ids:
        return [], [], [], "No valid entity_ids were given. Call get_home_state first to find them."

    blocked = [e for e in entity_ids if not is_exposed(hass, e)]
    entity_ids = [e for e in entity_ids if e not in blocked]
    if blocked:
        _LOGGER.warning("Refused to control entities hidden from voice: %s", blocked)
    if not entity_ids:
        return [], [], blocked, (
            "Those entities are hidden from voice control on purpose, so I didn't touch them: "
            f"{', '.join(blocked)}. Tell the user they'll need to use the Home Assistant app for these."
        )

    params = params or {}
    action = (action or "").strip().lower()

    # A param-bearing request (set temperature/brightness/position) determines the
    # service on its own; the action verb is redundant and often wrong there.
    service_data: dict = {}
    domain_service = None
    for key, value in params.items():
        key = key.strip().lower()
        if key in _PARAM_KEYS:
            service_data[_PARAM_KEYS[key]] = value
            domain_service = _PARAM_SERVICES[key]

    # "set the bedroom climate to cool" arrives as action="cool" at least as often
    # as it arrives as params={"hvac_mode": "cool"}; accept both rather than
    # rejecting the request over which slot the value landed in.
    if not domain_service and action in _HVAC_MODES:
        service_data["hvac_mode"] = action
        domain_service = _PARAM_SERVICES["hvac_mode"]

    unknown = []
    results = []
    for entity_id in entity_ids:
        entity_domain = entity_id.split(".", 1)[0]
        if hass.states.get(entity_id) is None:
            unknown.append(entity_id)
            continue

        if domain_service:
            _expected_domain, service = domain_service
            domain = entity_domain
        elif action in _ACTION_SERVICES:
            service = _ACTION_SERVICES[action]
            domain = entity_domain
            # open/close are cover verbs; on a non-cover, fall back to on/off so
            # "open the office blinds" still works if the entity is a switch.
            if service in ("open_cover", "close_cover") and entity_domain != "cover":
                service = "turn_on" if service == "open_cover" else "turn_off"
        else:
            return [], [], blocked, (
                f"Unsupported action '{action}'. Use one of: "
                f"{', '.join(sorted(_ACTION_SERVICES))}, or pass params like "
                "{'temperature': 70}."
            )

        if not hass.services.has_service(domain, service):
            unknown.append(f"{entity_id} (no {domain}.{service} service)")
            continue

        try:
            await hass.services.async_call(
                domain, service, {"entity_id": entity_id, **service_data}, blocking=True
            )
            results.append(entity_id)
        except Exception as err:  # noqa: BLE001 - report per-entity, don't fail the batch
            _LOGGER.warning("control_device failed on %s: %s", entity_id, err)
            unknown.append(f"{entity_id} ({err})")

    return results, unknown, blocked, None


async def control_device(
    hass: HomeAssistant,
    entity_ids: list[str] | str,
    action: str,
    params: dict | None = None,
) -> str:
    """Act on entities directly via service calls, by entity_id (LLM-facing tool).

    Deliberately does NOT round-trip through HA's built-in conversation agent.
    The model already has exact entity_ids from get_home_state; re-synthesizing
    an English sentence for HA's NLU to re-parse back into those same ids lost
    information at every hop and depended on Assist exposure being configured.
    Service calls need neither. A list of entity_ids is accepted so compound
    requests ("turn everything off in the lab") are one call, not one per device.
    """
    results, unknown, blocked, fatal = await _apply_control(hass, entity_ids, action, params)
    if fatal:
        return fatal
    if not results:
        return f"Failed to control: {', '.join(unknown)}"
    msg = f"Done. Affected {len(results)} entity/entities: {', '.join(results)}."
    if unknown:
        msg += f" Could not act on: {', '.join(unknown)}."
    if blocked:
        msg += f" Skipped (hidden from voice on purpose): {', '.join(blocked)}."
    return msg


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get the current weather. With no location it reports this house's own "
                "weather station, which is always correct for where the user is."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "ONLY set this when the user explicitly names a different city. "
                            "Omit it for 'what's the weather', 'weather today', or anything "
                            "about here/home - omitting is what gives the accurate local "
                            "reading. Never guess a city name."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": "Get the current stock price for a ticker symbol or company name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. TSLA, or company name"}
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for current information, news, or anything not covered by other tools.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_home_state",
            "description": (
                "Look up the current state of smart home entities by searching their name/id, e.g. "
                "'garage' or 'bedroom temperature'. Use this for ANY status/state question about a "
                "device or sensor ('is X open', 'what's the temperature in Y', 'is the door locked'), "
                "and ALWAYS before control_device, to get the exact entity_ids it requires. It reads "
                "live entity state directly, so it finds entities even when their naming or type seems "
                "unrelated to how the user described them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to search entity names/ids for, e.g. 'garage' or 'bedroom'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_devices",
            "description": (
                "List every physical device in the smart home (name, manufacturer, model, area). Use this "
                "when get_home_state finds no matching entities for something you'd expect to exist - e.g. "
                "'3D printer' won't keyword-match a device literally named 'X1C Genie' by 'Bambu Lab', but "
                "you can recognize that from this list using what you know about the world. Once you find "
                "the right device here, call get_home_state again with its actual name."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_device",
            "description": (
                "Perform an ACTION on one or more smart home devices, addressed by exact entity_id. "
                "Always call get_home_state first to get the entity_ids, then pass them here verbatim. "
                "Pass ALL affected entity_ids in a single call - for 'turn everything off in the lab', "
                "make one call listing every lab entity_id, not one call per device. "
                "For questions about current state, use get_home_state instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Exact entity_ids copied from get_home_state output, e.g. "
                            "['light.lab_ceiling', 'fan.lab_chamber_fan']. Never invent an entity_id "
                            "and never pass a friendly name here."
                        ),
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            "turn_on", "turn_off", "toggle", "open", "close", "lock", "unlock",
                            "cool", "heat", "auto", "dry", "fan_only",
                        ],
                        "description": (
                            "What to do to every entity in entity_ids. For a thermostat or AC, "
                            "use the mode name directly, e.g. 'cool'."
                        ),
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "Optional settings, e.g. {'temperature': 70}, {'brightness': 50} "
                            "(percent), {'position': 30}, or {'hvac_mode': 'cool'}. Omit "
                            "entirely for plain on/off/open/close."
                        ),
                    },
                },
                "required": ["entity_ids", "action"],
            },
        },
    },
]
