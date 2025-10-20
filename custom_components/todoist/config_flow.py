"""Config flow for todoist integration."""
from __future__ import annotations

import logging
from typing import Any

from todoist_api_python.api_async import TodoistAPIAsync
from todoist_api_python.errors import TodoistAPIError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback

from .const import CONF_ADVANCED_MODE, CONF_INCLUDE_ARCHIVED, DOMAIN

_LOGGER = logging.getLogger(__name__)

SETTINGS_URL = "https://app.todoist.com/app/settings/integrations/developer"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
    }
)


class TodoistConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for todoist."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TodoistOptionsFlowHandler:
        """Get the options flow for this handler."""
        return TodoistOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            api = TodoistAPIAsync(user_input[CONF_TOKEN])
            try:
                await api.get_projects()
            except TodoistAPIError as err:
                if err.is_authentication_error():
                    errors["base"] = "invalid_api_key"
                else:
                    errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="Todoist", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"settings_url": SETTINGS_URL},
        )


class TodoistOptionsFlowHandler(OptionsFlow):
    """Handle a Todoist options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INCLUDE_ARCHIVED,
                        default=self.config_entry.options.get(
                            CONF_INCLUDE_ARCHIVED, False
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_ADVANCED_MODE,
                        default=self.config_entry.options.get(
                            CONF_ADVANCED_MODE, False
                        ),
                    ): bool,
                }
            ),
        )
