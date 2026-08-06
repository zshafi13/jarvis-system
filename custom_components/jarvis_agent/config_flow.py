from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_DEFAULT_LOCATION,
    CONF_OLLAMA_HOST,
    CONF_OLLAMA_MODEL,
    CONF_TAVILY_API_KEY,
    DEFAULT_LOCATION,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DOMAIN,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_OLLAMA_HOST, default=DEFAULT_OLLAMA_HOST): str,
        vol.Required(CONF_OLLAMA_MODEL, default=DEFAULT_OLLAMA_MODEL): str,
        vol.Optional(CONF_TAVILY_API_KEY): str,
        vol.Optional(CONF_DEFAULT_LOCATION, default=DEFAULT_LOCATION): str,
    }
)


class JarvisAgentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Jarvis Agent", data=user_input)

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
