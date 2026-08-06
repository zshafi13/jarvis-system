DOMAIN = "jarvis_agent"

CONF_OLLAMA_HOST = "ollama_host"
CONF_OLLAMA_MODEL = "ollama_model"
CONF_TAVILY_API_KEY = "tavily_api_key"
CONF_DEFAULT_LOCATION = "default_location"

DEFAULT_OLLAMA_HOST = "http://192.168.4.21:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_LOCATION = "Allentown"

# Max messages of conversation history kept per HA conversation_id, mirroring the
# original agent_state.py's role but per-conversation instead of one shared global.
# Kept fairly small: a single multi-round tool-calling exchange (e.g. list_devices
# -> get_home_state -> control_home_assistant) can itself produce 6+ messages of
# raw tool-result data, and qwen2.5:7b has shown a real tendency to let stale tool
# results from an earlier, unrelated question bleed into a later one (e.g. a 3D
# printer lookup contaminating a follow-up climate-control answer) rather than
# recognizing it's no longer relevant.
MAX_HISTORY_MESSAGES = 6
