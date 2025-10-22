"""DataUpdateCoordinator for the Todoist component."""

import asyncio
from datetime import date, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
        today = date.today()
        three_months_ago = today - timedelta(days=90)
        try:
            (
                tasks,
                completed_tasks,
                projects,
                labels,
            ) = await asyncio.gather(
                self.api.get_tasks(),
                self.api.get_completed_tasks_by_completion_date(
                    since=dt_util.start_of_local_day(three_months_ago),
                    until=dt_util.end_of_local_day(today),
                ),
                self.api.get_projects(),
                self.api.get_labels(),
            )
            all_tasks = [task async for page in tasks for task in page]
            all_tasks.extend(completed_tasks)
            return TodoistData(
                tasks=all_tasks,
                projects=[project async for page in projects for project in page],
                labels=[label async for page in labels for label in page],
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
