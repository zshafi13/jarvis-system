"""Tool implementations + their Ollama/OpenAI-style function-calling schemas.

get_weather and get_stock are ported from agent_jarvis/tools/weather.py and
agent_jarvis/tools/stock.py unchanged. search_web replaces the LangChain
TavilySearchResults wrapper with a direct tavily-python call. control_home_assistant
is new: it delegates device-control requests to Home Assistant's own built-in
conversation agent, reusing HA's entity/area matching instead of reimplementing it.
"""
from __future__ import annotations

import logging

import requests
import yfinance as yf
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

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


def get_weather(location: str = "Allentown") -> str:
    try:
        response = requests.get(f"https://wttr.in/{location}?format=j1", timeout=5)
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
        data = stock.history(period="1d")
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
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=3)
        results = response.get("results", [])
        if not results:
            return f"I couldn't find anything useful on '{query}'."

        summary = "\n\n".join(
            f"Title: {r.get('title', '')}\nContent: {r.get('content', '')}" for r in results
        )
        return summary
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
    "garage": {"garage_door", "door", "opening"},
    "lock": {"lock"},
    "locked": {"lock"},
    "motion": {"motion", "occupancy"},
    "leak": {"moisture"},
    "water": {"moisture"},
    "smoke": {"smoke"},
    "temperature": {"temperature"},
    "open": {"window", "door", "garage_door", "opening"},
}


def get_home_state(hass: HomeAssistant, query: str, limit: int = 25) -> str:
    """Search entities by name/id/device_class and return their live state directly.

    HA's built-in conversation agent (used by control_home_assistant below) can only
    answer status questions for entities whose device_class matches its intent
    templates exactly - a binary_sensor with device_class "safety" won't match its
    "is X open" intent even if that's what the sensor represents in practice. Since
    this integration runs in-process inside Home Assistant, it can read any entity's
    live state directly via hass.states and let the model reason about it, sidestepping
    that limitation entirely. Use this for status/state questions; use
    control_home_assistant for actions.
    """
    query_terms = query.lower().split()
    relevant_classes: set[str] = set()
    for term in query_terms:
        # Naive singularization: the model may pass "windows"/"doors"/"locks" while
        # the hint map is keyed on the singular form.
        for candidate in (term, term[:-1] if term.endswith("s") else term):
            relevant_classes |= _DEVICE_CLASS_HINTS.get(candidate, set())

    class_matches = []
    name_matches = []
    for state in hass.states.async_all():
        domain = state.entity_id.split(".", 1)[0]
        if domain in _NOISE_DOMAINS:
            continue
        device_class = state.attributes.get("device_class", "")
        if device_class in relevant_classes:
            class_matches.append(state)
        elif all(term in f"{state.entity_id} {state.name}".lower() for term in query_terms):
            name_matches.append(state)

    # When the query maps to a known device_class (window, door, lock, ...), trust
    # that over name matching: sub-entities sharing a device's name (battery, tamper,
    # firmware, a network-wide "system software failure" flag that's "on" for nearly
    # every node) are noise that previously drowned out the entity that actually
    # answers the question, and could push it past the result limit entirely.
    matches = class_matches if class_matches else name_matches

    if not matches:
        return f"No entities found matching '{query}'."

    lines = []
    for state in matches[:limit]:
        device_class = state.attributes.get("device_class", "")
        dc_note = f" (device_class={device_class})" if device_class else ""
        lines.append(f"{state.entity_id} [{state.name}]{dc_note}: {state.state}")

    note = f"\n({len(matches) - limit} more matches not shown)" if len(matches) > limit else ""
    return "\n".join(lines) + note


async def control_home_assistant(hass: HomeAssistant, command: str) -> str:
    """Delegate a device-control request to HA's own built-in conversation agent.

    Reuses HA's entity/area/intent matching rather than reimplementing it here.
    `agent_id=None` lets HA route to its configured default (built-in) agent;
    if this integration is itself set as the pipeline's default agent, confirm
    in your HA instance that a distinct built-in agent_id is still reachable
    for this delegation to avoid recursing into itself.
    """
    from homeassistant.components import conversation as ha_conversation
    from homeassistant.helpers import intent

    try:
        result = await ha_conversation.async_converse(
            hass,
            text=command,
            conversation_id=None,
            context=None,
            language="en",
            agent_id="conversation.home_assistant",
        )
        if result.response.response_type == intent.IntentResponseType.ERROR:
            return "I couldn't do that with your smart home setup."
        return result.response.speech.get("plain", {}).get("speech", "Done.")
    except Exception as err:
        _LOGGER.warning("Home Assistant device control failed: %s", err)
        return "Something went wrong controlling that device."


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string", "description": "City name"}},
                "required": ["location"],
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
                "device or sensor ('is X open', 'what's the temperature in Y', 'is the door locked') - "
                "it reads live entity state directly and is more reliable than control_home_assistant "
                "for questions, even if the entity's naming or type seems unrelated at first."
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
            "name": "control_home_assistant",
            "description": (
                "Perform an ACTION on a smart home device (turn on/off, open/close, set temperature, etc.) "
                "through Home Assistant. For questions about current state, use get_home_state instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The device command in natural language, e.g. 'turn on the kitchen lights'",
                    }
                },
                "required": ["command"],
            },
        },
    },
]
