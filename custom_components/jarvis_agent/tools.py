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
            "name": "control_home_assistant",
            "description": (
                "Control or query smart home devices (lights, switches, thermostats, sensors, etc.) "
                "through Home Assistant. Use this for anything about the user's home devices."
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
