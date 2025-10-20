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
    _LOGGER.debug("Attempting to import todoist_api_python")
    try:
        from todoist_api_python.api_async import TodoistAPIAsync
        from todoist_api_python.errors import TodoistAPIError
        _LOGGER.debug("Successfully imported todoist_api_python")
    except ModuleNotFoundError as err:
        _LOGGER.error("Failed to import todoist_api_python: %s", err)
        raise ConfigEntryNotReady("Todoist API library not installed") from err

    token = entry.data[CONF_TOKEN]
    _LOGGER.debug("Creating TodoistAPIAsync with token")
    api = TodoistAPIAsync(token)
    try:
        _LOGGER.debug("Attempting to get projects from Todoist API")
        await api.get_projects()
        _LOGGER.debug("Successfully got projects from Todoist API")
    except TodoistAPIError as err:
        _LOGGER.error("Todoist API error: %s", err)
        if err.is_authentication_error():
            raise ConfigEntryNotReady("Invalid API key") from err
        raise ConfigEntryNotReady(f"Failed to connect to Todoist: {err}") from err
    except Exception as err:
        _LOGGER.error("Unexpected error connecting to Todoist API: %s", err)
        raise ConfigEntryNotReady(f"Failed to connect to Todoist: {err}") from err
    _LOGGER.debug("Returning api object")
    return api
