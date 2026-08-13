DOMAIN = "jarvis_agent"

CONF_OLLAMA_HOST = "ollama_host"
CONF_OLLAMA_MODEL = "ollama_model"
CONF_TAVILY_API_KEY = "tavily_api_key"
CONF_DEFAULT_LOCATION = "default_location"

DEFAULT_OLLAMA_HOST = "http://192.168.4.21:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_LOCATION = "Allentown"

# Per-request cap on the Ollama HTTP call. Without this the client waits on an
# unreachable GPU box indefinitely: when that machine dropped off the network, a
# turn hung for 90s+ with no speech at all, which in a voice pipeline is worse
# than an error - the user just gets silence. Generous enough for a slow local
# generation, short enough to fail audibly.
OLLAMA_TIMEOUT_SECONDS = 30

# Hard wall-clock budgets for a single turn. The per-call timeouts above only
# bound the calls we know about; anything else that blocks (a wedged tool, a
# hung library with no timeout of its own) would otherwise leave the Assist
# pipeline showing "processing" indefinitely, with no error and nothing in the
# log. Speaking a failure is always better than silence on a voice assistant.
TIER1_TIMEOUT_SECONDS = 10
RESPONSE_TIMEOUT_SECONDS = 75

# Max messages of conversation history kept per HA conversation_id, mirroring the
# original agent_state.py's role but per-conversation instead of one shared global.
# Kept fairly small: a single multi-round tool-calling exchange (e.g. list_devices
# -> get_home_state -> control_device) can itself produce 6+ messages of
# raw tool-result data, and qwen2.5:7b has shown a real tendency to let stale tool
# results from an earlier, unrelated question bleed into a later one (e.g. a 3D
# printer lookup contaminating a follow-up climate-control answer) rather than
# recognizing it's no longer relevant.
MAX_HISTORY_MESSAGES = 6
