"""Best-effort recovery for disguised tool calls.

Even at low temperature, the model occasionally writes a tool call out as plain
text instead of actually invoking Ollama's tool-calling mechanism - e.g. the
literal response 'Control_home_assistant: turn on the bedroom TV' or
'icontrol_home_assistant {"command": "..."}' spoken back to the user instead of
the action happening. Lower temperature (see conversation.py) reduced this from
roughly 1-in-8 to rare, but didn't eliminate it, so this parses the model's own
malformed output back into a real tool call as a safety net.
"""
from __future__ import annotations

import re

_ARG_NAME_BY_TOOL = {
    "get_weather": "location",
    "get_stock": "symbol",
    "search_web": "query",
    "get_home_state": "query",
    "control_home_assistant": "command",
}

# list_devices takes no arguments, so it's excluded from _ARG_NAME_BY_TOOL but
# still a valid tool name to detect below.
_TOOL_NAMES = (*_ARG_NAME_BY_TOOL.keys(), "list_devices")


def parse_disguised_tool_call(content: str) -> tuple[str, dict] | None:
    """Return (tool_name, args) if content looks like a tool call written as text."""
    if not content:
        return None

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
            return tool_name, {}

        # Try the JSON-ish shape first, against the UNSTRIPPED remainder - stripping
        # first would eat the opening quote before the key (e.g. '{"command": "x"}'
        # -> 'command": "x"}'), leaving nothing for this regex to anchor on.
        raw_remainder = content[match.end() :]
        json_match = re.search(r'"[a-z_]+"\s*:\s*"([^"]+)"', raw_remainder)
        value = json_match.group(1) if json_match else raw_remainder.strip(" :{}\"'").rstrip("}").strip(" \"'.")
        if not value:
            continue

        return tool_name, {arg_name: value}

    return None
