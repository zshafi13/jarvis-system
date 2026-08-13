"""Recovery for disguised tool calls, plus a hard sanitizer for spoken output.

Even at low temperature, the model occasionally writes a tool call out as plain
text instead of actually invoking Ollama's tool-calling mechanism - e.g. the
literal response 'Control_home_assistant: turn on the bedroom TV', or a
'<tool_call>{"name": ..., "arguments": {...}}</tool_call>' block embedded mid
sentence. Lower temperature (see conversation.py) made this rare but didn't
eliminate it.

Two layers here, and they are different jobs:
  - parse_disguised_tool_call: best-effort, turn malformed text back into a real
    tool call so the action still happens.
  - sanitize_for_speech: a guarantee, not an attempt. Whatever recovery does or
    doesn't manage, no tool-call syntax may ever reach TTS. The previous design
    only had the first layer, so anything recovery declined to parse got spoken
    aloud verbatim.
"""
from __future__ import annotations

import json
import logging
import re

_LOGGER = logging.getLogger(__name__)

_ARG_NAME_BY_TOOL = {
    "get_weather": "location",
    "get_stock": "symbol",
    "search_web": "query",
    "get_home_state": "query",
}

# Tools taking no arguments, or whose arguments are too structured for the
# single-string heuristic below, still need to be recognized by name.
_TOOL_NAMES = (*_ARG_NAME_BY_TOOL.keys(), "list_devices", "control_device")

# Where a tool-call JSON object may start: after a <tool_call> tag, or a bare
# object whose first key is "name". The object's extent is found by brace
# matching, not regex - these payloads nest ({"arguments": {...}}), and a
# non-greedy .*?\} stops at the first inner brace, producing invalid JSON and
# leaving a stray "}" behind in the spoken text.
_TOOL_CALL_START = re.compile(
    r"<tool_call>\s*(?=\{)|(?=\{\s*\"(?:name|function)\"\s*:)", re.IGNORECASE
)

# A tool name written out in prose, followed by its arguments as a JSON object -
# 'Get_home_state called with: {"query": "bedroom AC"}'. The earlier recovery only
# looked at the START of the message, so a call announced mid-sentence was neither
# recovered nor stripped: the model narrated both calls, performed neither, and
# then claimed the device had been set.
_TOOL_MENTION = re.compile(
    r"\b(get_home_state|control_device|get_weather|get_stock|search_web|list_devices)\b"
    r"[^{\n]{0,40}?(?=\{)",
    re.IGNORECASE,
)

# Any JSON-ish object left in text destined for speech. Deliberately broad: no
# object literal is ever something a person should hear read aloud.
_BARE_OBJECT = re.compile(r"(?=\{\s*[\"']?[a-z_]+[\"']?\s*:)", re.IGNORECASE)

# The prose that introduced a narrated call, left behind once its JSON is gone.
_TOOL_LEADIN = re.compile(
    r"\b(?:get_home_state|control_device|get_weather|get_stock|search_web|list_devices)\b"
    r"\s*(?:was\s+|is\s+)?(?:called|invoked|used|run)?\s*(?:with)?\s*:?\s*",
    re.IGNORECASE,
)

# Tags and control tokens that should never be read out loud. The JSON payload
# itself is removed separately, by brace matching.
_SPEECH_NOISE = (
    re.compile(r"</?tool_call>", re.IGNORECASE),
    re.compile(r"</?function_call>", re.IGNORECASE),
    re.compile(r"<\|[^|>]*\|>"),  # chat-template control tokens
    # Roleplay stage directions like "*wink*" or "*chuckles*". Piper reads the
    # word aloud, which lands as the assistant saying "wink" out loud. Bounded
    # length and no sentence punctuation inside, so it can't swallow real prose
    # that happens to use asterisks for emphasis across a clause.
    re.compile(r"\*[^*\n.!?]{1,24}\*"),
)


def _balanced_object(text: str, start: int) -> tuple[str, int] | None:
    """Return (json_text, end_index) for the {...} beginning at `start`.

    Tracks string literals and escapes so a brace inside a quoted value doesn't
    end the object early.
    """
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
    return None


def parse_disguised_tool_call(content: str) -> tuple[str, dict] | None:
    """Return (tool_name, args) if content looks like a tool call written as text."""
    if not content:
        return None

    # Structured form first: a real JSON payload carries full arguments, so it
    # recovers multi-arg tools (control_device) that the heuristic below can't.
    for match in _TOOL_CALL_START.finditer(content):
        found = _balanced_object(content, match.end())
        if not found:
            continue
        try:
            data = json.loads(found[0])
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name") or data.get("function")
        args = data.get("arguments") or data.get("parameters") or {}
        if isinstance(name, str) and name in _TOOL_NAMES and isinstance(args, dict):
            return name, args

    # A tool named in prose with its arguments as JSON, anywhere in the message.
    for match in _TOOL_MENTION.finditer(content):
        found = _balanced_object(content, match.end())
        if not found:
            continue
        try:
            args = json.loads(found[0])
        except (ValueError, TypeError):
            continue
        if isinstance(args, dict):
            name = match.group(1).lower()
            # Guard against the nested {"name": ..., "arguments": {...}} shape
            # already handled above being re-parsed here as flat arguments.
            if set(args) == {"name", "arguments"}:
                continue
            return name, args

    normalized = re.sub(r"[^a-z]", "", content.lower())

    for tool_name in _TOOL_NAMES:
        key = tool_name.replace("_", "")
        idx = normalized.find(key)
        # Only trust a match very near the start - keeps this from misfiring on
        # ordinary sentences that happen to mention these words later on.
        if idx == -1 or idx > 3:
            continue

        # Up to 2 arbitrary leading characters tolerates stray output like the "i"
        # in "icontrol_home_assistant {...}" - a real occurrence, not hypothetical.
        match = re.search(
            r"^.{0,2}" + r"[\s_]*".join(re.escape(word) for word in tool_name.split("_")),
            content,
            re.IGNORECASE,
        )
        if not match:
            continue

        arg_name = _ARG_NAME_BY_TOOL.get(tool_name)
        if arg_name is None:
            # list_devices takes nothing; control_device needs structured args
            # that this single-string path can't reconstruct, so let the caller
            # re-prompt rather than invent an entity_id.
            return (tool_name, {}) if tool_name == "list_devices" else None

        # Try the JSON-ish shape first, against the UNSTRIPPED remainder - stripping
        # first would eat the opening quote before the key (e.g. '{"query": "x"}'
        # -> 'query": "x"}'), leaving nothing for this regex to anchor on.
        raw_remainder = content[match.end() :]
        json_match = re.search(r'"[a-z_]+"\s*:\s*"([^"]+)"', raw_remainder)
        value = json_match.group(1) if json_match else raw_remainder.strip(" :{}\"'").rstrip("}").strip(" \"'.")
        if not value:
            continue

        return tool_name, {arg_name: value}

    return None


# Entity ids read aloud as "binary sensor dot garage intrusion", which is how the
# model cites its sources when it has tool output in context. Rewritten to the
# human-readable tail instead of stripped, so the sentence still parses. Anchored
# to real HA domains so it can't mangle decimals, filenames or urls.
_HA_DOMAINS = (
    "binary_sensor|sensor|light|switch|fan|climate|cover|lock|media_player|vacuum|"
    "humidifier|camera|number|select|button|update|scene|script|automation|"
    "input_boolean|input_number|device_tracker|person|weather|sun|zone|conversation"
)
_ENTITY_ID = re.compile(rf"`?\b(?:{_HA_DOMAINS})\.([a-z0-9_]+)\b`?")


def sanitize_for_speech(content: str) -> str:
    """Strip anything tool-call-shaped so it can never be spoken aloud.

    Unconditional: called on every reply regardless of how it was produced.
    """
    if not content:
        return ""

    # Remove tool-call JSON objects wholesale, brace-matched so nested arguments
    # come out in one piece rather than leaving a dangling "}".
    cleaned = content
    while True:
        match = _TOOL_CALL_START.search(cleaned)
        if not match:
            break
        found = _balanced_object(cleaned, match.end())
        if not found:
            break
        cleaned = cleaned[: match.start()] + " " + cleaned[found[1] :]

    # Then any remaining object literal, whatever its keys. The tool-call form
    # above only matches {"name": ...}; a narrated call carries its arguments
    # directly ({"query": "bedroom AC"}) and would otherwise be read aloud.
    while True:
        match = _BARE_OBJECT.search(cleaned)
        if not match:
            break
        found = _balanced_object(cleaned, match.start())
        if not found:
            break
        cleaned = cleaned[: match.start()] + " " + cleaned[found[1] :]

    # Drop the prose lead-in that introduced the removed object, so speech doesn't
    # end on a dangling "Control_device called with:".
    cleaned = _TOOL_LEADIN.sub(" ", cleaned)

    for pattern in _SPEECH_NOISE:
        cleaned = pattern.sub(" ", cleaned)

    # "the binary_sensor.garage_intrusion sensor" -> "the garage intrusion sensor"
    cleaned = _ENTITY_ID.sub(lambda m: m.group(1).replace("_", " "), cleaned)
    cleaned = cleaned.replace("`", "")


    # Collapse the whitespace the substitutions leave behind, and drop any
    # trailing lead-in ("Let's try:", "...directly.") left dangling by removal.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[\s,;:]*(?:like|such as|e\.g\.?)?[\s,;:]*$", "", cleaned).strip()

    if cleaned != content.strip():
        _LOGGER.warning("Stripped tool-call syntax from spoken output: %r", content)

    return cleaned
