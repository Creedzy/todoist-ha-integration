"""The todoist integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import async_get_api
from .const import DOMAIN
from .coordinator import TodoistDataUpdateCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)


PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.TODO]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up todoist from a config entry."""
    _LOGGER.debug("Starting async_setup_entry")

    _LOGGER.debug("Calling async_get_api")
    api = await async_get_api(hass, entry)
    _LOGGER.debug("async_get_api finished, api object: %s", api)

    _LOGGER.debug("Creating TodoistDataUpdateCoordinator")
    coordinator = TodoistDataUpdateCoordinator(hass, _LOGGER, entry, api)
    _LOGGER.debug("Calling async_config_entry_first_refresh")
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("async_config_entry_first_refresh finished")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Todoist component."""
    return True
