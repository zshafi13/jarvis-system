"""The conversation agent entity: replaces agent.py/intent_router.py/tool_runner.py.

Where the original made up to 3 sequential blocking Ollama calls per turn (intent
classification, follow-up classification, then response/summary generation), this
makes 1 call with tool-calling for plain chat, or up to a few more when tools chain
(e.g. list_devices to find an unfamiliar device, then get_home_state to read it) -
still typically fewer than the original's fixed 3 for the common freeform-chat case.
"""
from __future__ import annotations

import asyncio
import logging
import re
from functools import partial

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from ollama import AsyncClient

from .const import (
    CONF_DEFAULT_LOCATION,
    CONF_OLLAMA_HOST,
    CONF_OLLAMA_MODEL,
    CONF_TAVILY_API_KEY,
    DEFAULT_LOCATION,
    MAX_HISTORY_MESSAGES,
    OLLAMA_TIMEOUT_SECONDS,
    RESPONSE_TIMEOUT_SECONDS,
    TIER1_TIMEOUT_SECONDS,
)
from .prompts import SYSTEM_PROMPT
from .tool_recovery import parse_disguised_tool_call, sanitize_for_speech
from .tools import (
    TOOL_SCHEMAS,
    control_device,
    get_home_state,
    get_stock,
    get_weather,
    list_devices,
    needs_fresh_information,
    search_web,
    try_area_bulk,
    try_builtin_intent,
)

_LOGGER = logging.getLogger(__name__)

# Filler the model emits *instead of* calling a tool. Anchored to the start so a
# real answer that merely mentions checking ("I checked the garage, it's open")
# is never mistaken for a stall.
_STALL_INTENT = re.compile(
    r"^(?:sure|ok(?:ay)?|alright|right)?[,.!\s]*"
    r"(?:let(?:'s| me| us)|i(?:'ll| will| am going to| shall)?)\s+"
    r"(?:just\s+)?(?:check|look|see|find out|verify|take a look|get)\b",
    re.IGNORECASE,
)

# Bare openers that only indicate stalling in a message too short to also contain
# an answer - "Looking at the data, the bedroom is 78 degrees" is a real reply and
# must not be suppressed just because it starts with a gerund.
_STALL_BARE = re.compile(
    r"^(?:checking|looking|searching|one moment|1 moment|hold on|"
    r"give me a (?:second|moment)|just a (?:second|moment))\b",
    re.IGNORECASE,
)


def _is_stalling(content: str) -> bool:
    """True if this is 'I'll go check' filler rather than an actual answer."""
    stripped = content.strip()
    if len(stripped) > 160:
        return False  # long enough to contain a real answer
    if _STALL_INTENT.search(stripped):
        return True
    # 30 chars covers "Checking now...", "One moment please.", "Hold on a sec."
    # while leaving room for a real sentence that merely opens with a gerund
    # ("Searching the web turned up that the Chiefs won.").
    return len(stripped) < 30 and bool(_STALL_BARE.search(stripped))

# httpx (what the ollama client uses underneath) raises its own error hierarchy
# that does NOT subclass OSError/ConnectionError, so catching the builtins alone
# silently misses every real connectivity failure. Imported defensively so a
# packaging change degrades to the generic handler instead of breaking setup.
try:
    import httpx

    _CONNECTIVITY_ERRORS: tuple[type[BaseException], ...] = (
        httpx.HTTPError,
        ConnectionError,
        TimeoutError,
        OSError,
    )
except ImportError:  # pragma: no cover
    _CONNECTIVITY_ERRORS = (ConnectionError, TimeoutError, OSError)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([JarvisConversationAgent(entry)])


class JarvisConversationAgent(conversation.ConversationEntity):
    _attr_has_entity_name = True
    _attr_name = "Jarvis"

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._ollama_host = entry.data[CONF_OLLAMA_HOST]
        self._client: AsyncClient | None = None
        self._model = entry.data[CONF_OLLAMA_MODEL]
        self._tavily_key = entry.data.get(CONF_TAVILY_API_KEY)
        self._default_location = entry.data.get(CONF_DEFAULT_LOCATION, DEFAULT_LOCATION)
        # Per-conversation_id history, unlike the original agent_state.py which
        # was a single global shared across every user/session.
        self._history: dict[str, list[dict]] = {}

    async def async_added_to_hass(self) -> None:
        # AsyncClient() does blocking SSL cert loading in its constructor, so it
        # can't be built inline in __init__, which runs in the event loop.
        self._client = await self.hass.async_add_executor_job(
            partial(AsyncClient, host=self._ollama_host, timeout=OLLAMA_TIMEOUT_SECONDS)
        )

    @property
    def supported_languages(self) -> list[str]:
        return ["en"]

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        conversation_id = user_input.conversation_id or self._new_conversation_id()

        # Tier 1: HA's own intent engine handles templated commands ("turn on X",
        # "turn everything off in the lab") deterministically in ~50-200ms. Trying
        # it first means the common case never reaches a 7B model, so it can't be
        # slow, malformed, or hallucinated. Only unmatched input falls through.
        # Area-bulk first: HA's templates mis-parse "everything" as a device name,
        # so this shape has to be claimed before the built-in matcher sees it.
        try:
            async with asyncio.timeout(TIER1_TIMEOUT_SECONDS):
                fast = await try_area_bulk(self.hass, user_input.text)
                if fast is None:
                    fast = await try_builtin_intent(
                        self.hass, user_input.text, user_input.language
                    )
        except TimeoutError:
            # Tier 1 is meant to answer in well under a second; if it somehow
            # blocks, fall through to the LLM rather than stalling the pipeline.
            _LOGGER.warning("Tier-1 intent matching timed out, falling through")
            fast = None
        if fast is not None:
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(fast)
            return conversation.ConversationResult(
                response=intent_response, conversation_id=conversation_id
            )

        # Tier 2: freeform chat, tools, and device requests HA's templates missed.
        # The date is injected per-turn rather than baked into SYSTEM_PROMPT: the
        # model otherwise has no idea what year it is and will confidently answer
        # stale questions ("most recent Super Bowl") from training data.
        # Date AND time: with only the date supplied, "what time is it" was answered
        # from nothing at all - it confidently said 3:47 PM when it was 2:39 PM.
        # There is no clock tool, so the fact has to be handed over directly.
        now = dt_util.now()
        system = (
            f"{SYSTEM_PROMPT}\n\nRight now it is "
            f"{now.strftime('%-I:%M %p on %A, %B %-d, %Y')} in the user's local timezone. "
            "Use this for any question about the current date or time; never guess it."
        )
        history = self._history.setdefault(conversation_id, [{"role": "system", "content": system}])
        history[0] = {"role": "system", "content": system}
        history.append({"role": "user", "content": user_input.text})

        # Deterministic search for recency questions. Asking the prompt to "always
        # call search_web" did not work - the model stayed confident and wrong - so
        # the search is performed here and injected, rather than left to its
        # discretion. Same principle as tier 1: don't request behaviour you can guarantee.
        if self._tavily_key and needs_fresh_information(user_input.text):
            try:
                found = await self.hass.async_add_executor_job(
                    search_web, user_input.text, self._tavily_key
                )
                # Injected as a system message, NOT a "tool" message: a tool-role
                # entry is only valid directly after an assistant turn that made a
                # matching tool_call. Appending a bare one leaves the history
                # malformed and the model silently discards it - which is exactly
                # what happened, it kept answering from memory with the live
                # results sitting right there in the context.
                history.append(
                    {
                        "role": "system",
                        "content": (
                            "Live web search results for the user's question, retrieved "
                            "just now. These are current and override anything you "
                            "remember from training. Answer from these:\n" + found
                        ),
                    }
                )
                _LOGGER.debug("Pre-fetched web results for recency question")
            except Exception:  # noqa: BLE001 - a failed search shouldn't kill the turn
                _LOGGER.exception("Pre-emptive web search failed")

        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT_SECONDS):
                reply_text = await self._run_tool_calling_loop(history)
        except TimeoutError:
            # The backstop for anything that blocks without a timeout of its own.
            # Whatever went wrong, the user gets speech instead of a pipeline that
            # sits on "processing" forever.
            _LOGGER.error(
                "Turn exceeded %ss budget; giving up on: %r",
                RESPONSE_TIMEOUT_SECONDS,
                user_input.text,
            )
            reply_text = "That one took too long and I gave up. Try me again?"
        except _CONNECTIVITY_ERRORS as err:
            # Distinguished from a generic failure on purpose: device control still
            # works in this state via tier 1, so say what's actually broken rather
            # than implying the whole assistant is down.
            _LOGGER.error("Ollama unreachable at %s: %s", self._ollama_host, err)
            reply_text = "I can't reach my language model right now, though I can still control the house."
        except Exception:  # noqa: BLE001 - always want to speak *something* back
            _LOGGER.exception("Jarvis agent failed to respond")
            reply_text = "Sorry, something went wrong on my end."

        # Unconditional: no tool-call syntax may ever reach TTS, whatever path
        # produced this string or however recovery above did or didn't handle it.
        reply_text = sanitize_for_speech(reply_text) or "Sorry, I'm drawing a blank on that one."

        history.append({"role": "assistant", "content": reply_text})
        # Persist only the conversation itself - drop tool results and the assistant
        # turns that carried tool_calls. Raw tool output is relevant to the turn that
        # fetched it and actively harmful afterwards: stale entity dumps from an
        # earlier question bled into later answers, producing invented claims (an
        # "active" lab motion sensor that was in fact off). Keeping just user/assistant
        # text preserves the thread of conversation without the stale facts.
        conversational = [
            m
            for m in history[1:]
            if m.get("role") in ("user", "assistant") and not m.get("tool_calls") and m.get("content")
        ]
        self._history[conversation_id] = [history[0], *conversational[-MAX_HISTORY_MESSAGES:]]

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(reply_text)
        return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

    async def _run_tool_calling_loop(self, history: list[dict], max_rounds: int = 5) -> str:
        # Looped (not a single call + one followup) so tools can chain - e.g.
        # list_devices to identify an unfamiliar device by manufacturer, then
        # get_home_state on the name it found. `tools` must be passed on every
        # round, including followups, or the model can never make a second call.
        for _ in range(max_rounds):
            # Low temperature: measured ~1/8 failure rate at Ollama's default (0.8)
            # where the model writes a tool call out as plain text instead of
            # actually invoking it (e.g. 'control_home_assistant {"command": ...}'
            # as the spoken response) - 0/8 across the same test at 0.1.
            response = await self._client.chat(
                model=self._model, messages=history, tools=TOOL_SCHEMAS, options={"temperature": 0.1}
            )
            message = response["message"]
            tool_calls = message.get("tool_calls")
            content = (message.get("content") or "").strip()

            if not tool_calls:
                recovered = parse_disguised_tool_call(content)
                if recovered:
                    name, args = recovered
                    _LOGGER.warning("Recovered a disguised tool call from model output: %s(%s)", name, args)
                    history.append({"role": "assistant", "content": content})
                    result = await self._execute_tool(name, args)
                    history.append({"role": "tool", "name": name, "content": result})
                    continue

                if content and _is_stalling(content):
                    # "Let's check that for you. 1 moment please." with no tool call
                    # is not an answer - the user asked a question and would get
                    # filler and silence. The prompt forbids this and the model does
                    # it anyway, so treat it as a non-answer and make it try again
                    # rather than speaking it.
                    _LOGGER.warning("Model stalled instead of calling a tool: %r", content)
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                "You said you would check but did not call a tool. Do not "
                                "narrate. Either call the tool now, or give the final answer."
                            ),
                        }
                    )
                    continue

                if content:
                    return content

                # Genuinely empty content with no tool call is never a valid final
                # answer - nudge and retry instead of silently speaking nothing.
                _LOGGER.warning("Model returned empty content with no tool call, retrying")
                history.append(
                    {"role": "user", "content": "(Empty response - please answer the previous message, calling a tool if needed.)"}
                )
                continue

            history.append({"role": "assistant", "content": message.get("content", ""), "tool_calls": tool_calls})

            for call in tool_calls:
                name = call["function"]["name"]
                args = call["function"].get("arguments") or {}
                result = await self._execute_tool(name, args)
                history.append({"role": "tool", "name": name, "content": result})

        # Hit max_rounds without a final answer - force one without tools available.
        followup = await self._client.chat(model=self._model, messages=history)
        return (followup["message"].get("content") or "").strip() or "Sorry, I'm drawing a blank on that one."

    async def _execute_tool(self, name: str, args: dict) -> str:
        if name == "get_weather":
            location = args.get("location")
            if not location:
                # Reads a local entity, no network call, so it must not go to the
                # executor - and it needs hass.
                return get_weather(self.hass)
            return await self.hass.async_add_executor_job(get_weather, self.hass, location)
        if name == "get_stock":
            return await self.hass.async_add_executor_job(get_stock, args.get("symbol", "TSLA"))
        if name == "search_web":
            if not self._tavily_key:
                return "Web search isn't configured with an API key."
            return await self.hass.async_add_executor_job(search_web, args.get("query", ""), self._tavily_key)
        if name == "control_device":
            return await control_device(
                self.hass,
                args.get("entity_ids") or [],
                args.get("action", ""),
                args.get("params") or {},
            )
        if name == "get_home_state":
            return get_home_state(self.hass, args.get("query", ""))
        if name == "list_devices":
            return list_devices(self.hass)
        return f"Unknown tool requested: {name}"

    def _new_conversation_id(self) -> str:
        from homeassistant.util import ulid as ulid_util

        return ulid_util.ulid_now()
