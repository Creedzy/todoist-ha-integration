"""API for the Todoist component."""
from __future__ import annotations

from http import HTTPStatus
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

_LOGGER = logging.getLogger(__name__)


from typing import Any


async def async_get_api(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    """Get a Todoist API instance."""
    try:
        from todoist_api_python.api_async import TodoistAPIAsync
        from todoist_api_python.errors import TodoistAPIError
    except ModuleNotFoundError as err:
        raise ConfigEntryNotReady("Todoist API library not installed") from err

    token = entry.data[CONF_TOKEN]
    api = TodoistAPIAsync(token)
    try:
        await api.get_projects()
    except TodoistAPIError as err:
        if err.is_authentication_error():
            raise ConfigEntryNotReady("Invalid API key") from err
        raise ConfigEntryNotReady(f"Failed to connect to Todoist: {err}") from err
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to connect to Todoist: {err}") from err
    return api
