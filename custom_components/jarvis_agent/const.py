DOMAIN = "jarvis_agent"

CONF_OLLAMA_HOST = "ollama_host"
CONF_OLLAMA_MODEL = "ollama_model"
CONF_TAVILY_API_KEY = "tavily_api_key"
CONF_DEFAULT_LOCATION = "default_location"

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_LOCATION = "Allentown"

# Max turns of conversation history kept per HA conversation_id, mirroring the
# original agent_state.py's role but per-conversation instead of one shared global.
MAX_HISTORY_MESSAGES = 12
