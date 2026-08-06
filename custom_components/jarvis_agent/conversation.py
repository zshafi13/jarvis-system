"""The conversation agent entity: replaces agent.py/intent_router.py/tool_runner.py.

Where the original made up to 3 sequential blocking Ollama calls per turn (intent
classification, follow-up classification, then response/summary generation), this
makes 1 call with tool-calling, or 2 if a tool is actually invoked (1 to decide/call
the tool, 1 to turn the tool result into a spoken reply) - and both are always fewer
than the original's fixed 3, since freeform chat (the common case) now takes exactly 1.
"""
from __future__ import annotations

import logging

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from ollama import AsyncClient

from .const import CONF_DEFAULT_LOCATION, CONF_OLLAMA_HOST, CONF_OLLAMA_MODEL, CONF_TAVILY_API_KEY, DEFAULT_LOCATION, MAX_HISTORY_MESSAGES
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, control_home_assistant, get_stock, get_weather, search_web

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([JarvisConversationAgent(entry)])


class JarvisConversationAgent(conversation.ConversationEntity):
    _attr_has_entity_name = True
    _attr_name = "Jarvis"

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._client = AsyncClient(host=entry.data[CONF_OLLAMA_HOST])
        self._model = entry.data[CONF_OLLAMA_MODEL]
        self._tavily_key = entry.data.get(CONF_TAVILY_API_KEY)
        self._default_location = entry.data.get(CONF_DEFAULT_LOCATION, DEFAULT_LOCATION)
        # Per-conversation_id history, unlike the original agent_state.py which
        # was a single global shared across every user/session.
        self._history: dict[str, list[dict]] = {}

    @property
    def supported_languages(self) -> list[str]:
        return ["en"]

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        conversation_id = user_input.conversation_id or self._new_conversation_id()
        history = self._history.setdefault(conversation_id, [{"role": "system", "content": SYSTEM_PROMPT}])
        history.append({"role": "user", "content": user_input.text})

        try:
            reply_text = await self._run_tool_calling_loop(history)
        except Exception as err:  # noqa: BLE001 - always want to speak *something* back
            _LOGGER.exception("Jarvis agent failed to respond")
            reply_text = "Sorry, something went wrong on my end."

        history.append({"role": "assistant", "content": reply_text})
        self._history[conversation_id] = [history[0], *history[1:][-MAX_HISTORY_MESSAGES:]]

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(reply_text)
        return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

    async def _run_tool_calling_loop(self, history: list[dict]) -> str:
        response = await self._client.chat(model=self._model, messages=history, tools=TOOL_SCHEMAS)
        message = response["message"]
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            return (message.get("content") or "").strip()

        history.append({"role": "assistant", "content": message.get("content", ""), "tool_calls": tool_calls})

        for call in tool_calls:
            name = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            result = await self._execute_tool(name, args)
            history.append({"role": "tool", "name": name, "content": result})

        followup = await self._client.chat(model=self._model, messages=history)
        return (followup["message"].get("content") or "").strip()

    async def _execute_tool(self, name: str, args: dict) -> str:
        if name == "get_weather":
            return await self.hass.async_add_executor_job(get_weather, args.get("location", self._default_location))
        if name == "get_stock":
            return await self.hass.async_add_executor_job(get_stock, args.get("symbol", "TSLA"))
        if name == "search_web":
            if not self._tavily_key:
                return "Web search isn't configured with an API key."
            return await self.hass.async_add_executor_job(search_web, args.get("query", ""), self._tavily_key)
        if name == "control_home_assistant":
            return await control_home_assistant(self.hass, args.get("command", ""))
        return f"Unknown tool requested: {name}"

    def _new_conversation_id(self) -> str:
        from homeassistant.util import ulid as ulid_util

        return ulid_util.ulid_now()
