"""API for the Todoist component."""
from __future__ import annotations

import logging
from typing import Any

import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

_LOGGER = logging.getLogger(__name__)


async def async_get_api(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    """Get a Todoist API instance."""
    try:
        from todoist_api_python.api_async import TodoistAPIAsync
    except ModuleNotFoundError as err:
        raise ConfigEntryNotReady("Todoist API library not installed") from err

    token = entry.data[CONF_TOKEN]
    api = TodoistAPIAsync(token)
    try:
        await api.get_projects()
    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 401:
            raise ConfigEntryNotReady("Invalid API key") from err
        raise ConfigEntryNotReady(f"Failed to connect to Todoist: {err}") from err
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to connect to Todoist: {err}") from err
    return api
