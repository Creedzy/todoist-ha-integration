"""Legacy REST client shim preserved for backward compatibility."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_api(hass: HomeAssistant, entry: ConfigEntry) -> Any:  # pragma: no cover
    """Legacy entry point kept temporarily for compatibility.

    The integration now relies exclusively on the Sync API implementation; this shim
    exists so older imports fail loudly if invoked.
    """

    raise RuntimeError(
        "todoist.api.async_get_api is deprecated. The integration now uses the Sync API."
    )
