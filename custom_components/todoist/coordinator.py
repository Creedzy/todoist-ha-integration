"""DataUpdateCoordinator for the Todoist component."""

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .types import TodoistData


class TodoistDataUpdateCoordinator(DataUpdateCoordinator[TodoistData]):
    """Coordinator for updating data from Todoist."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        entry: ConfigEntry,
        api: Any,
    ) -> None:
        """Initialize the Todoist coordinator."""
        from todoist_api_python.api_async import TodoistAPIAsync
        from todoist_api_python.models import Task

        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.api = api
        self.entry = entry

    async def _async_update_data(self) -> TodoistData:
        """Fetch data from the Todoist API."""
        try:
            tasks, projects, labels = await asyncio.gather(
                self.api.get_tasks(),
                self.api.get_projects(),
                self.api.get_labels(),
            )
            return TodoistData(
                tasks=[task for page in tasks for task in page],
                projects=[project for page in projects for project in page],
                labels=[label for page in labels for label in page],
            )
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def async_add_task(self, data: dict) -> Any:
        """Add a task."""
        task = await self.api.add_task(**data)
        await self.async_refresh()
        return task

    async def async_update_task(self, task_id: str, data: dict) -> bool:
        """Update a task."""
        result = await self.api.update_task(task_id, **data)
        await self.async_refresh()
        return result

    async def async_close_task(self, task_id: str) -> bool:
        """Close a task."""
        result = await self.api.close_task(task_id)
        await self.async_refresh()
        return result

    async def async_reopen_task(self, task_id: str) -> bool:
        """Reopen a task."""
        result = await self.api.reopen_task(task_id)
        await self.async_refresh()
        return result

    async def async_delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        result = await self.api.delete_task(task_id)
        await self.async_refresh()
        return result
