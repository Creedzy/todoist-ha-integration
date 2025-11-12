"""DataUpdateCoordinator for the Todoist component."""

import asyncio
from datetime import date, datetime, timedelta
import logging
from typing import Any

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
    self._session = async_get_clientsession(hass)
    self._token = entry.data.get(CONF_TOKEN)
    self._task_lookup: dict[str, Any] = {}

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
                    since=dt_util.start_of_local_day(
                        datetime.combine(three_months_ago, datetime.min.time())
                    ),
                    until=dt_util.now().replace(
                        hour=23, minute=59, second=59, microsecond=999999
                    ),
                ),
                self.api.get_projects(),
                self.api.get_labels(),
            )
            self.logger.debug(f"Tasks type: {type(tasks)}")
            self.logger.debug(f"Completed tasks type: {type(completed_tasks)}")
            all_tasks = [task async for page in tasks for task in page]
            all_tasks.extend(
                [task async for page in completed_tasks for task in page]
            )
            self._task_lookup = {task.id: task for task in all_tasks}
            return TodoistData(
                tasks=all_tasks,
                projects=[project async for page in projects for project in page],
                labels=[label async for page in labels for label in page],
                last_update=dt_util.utcnow().timestamp(),
            )
        except Exception as err:
            self.logger.error("Error communicating with API: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def async_add_task(self, data: dict, *, refresh: bool = True) -> Any:
        """Add a task."""
        task = await self.api.add_task(**data)
        self._task_lookup[task.id] = task
        if refresh:
            await self.async_refresh()
        return task

    async def async_update_task(self, task_id: str, data: dict, *, refresh: bool = True) -> bool:
        """Update a task."""
        sanitized = {key: value for key, value in data.items() if key != "task_id"}
        result = await self.api.update_task(task_id, **sanitized)
        self._task_lookup.pop(task_id, None)
        if refresh:
            await self.async_refresh()
        return result

    async def _async_task_action(self, task_id: str, action: str) -> None:
        """Perform a Todoist REST task action when the SDK lacks helpers."""

        if not self._token:
            raise HomeAssistantError("Todoist token missing from config entry")

        url = f"https://api.todoist.com/rest/v2/tasks/{task_id}/{action}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        try:
            async with self._session.post(url, headers=headers, timeout=15) as response:
                if response.status >= 400:
                    body = await response.text()
                    raise HomeAssistantError(
                        f"Todoist API returned HTTP {response.status} for {action}: {body}"
                    )
        except ClientError as err:
            raise HomeAssistantError(f"Todoist API request failed: {err}") from err

    async def async_close_task(self, task_id: str, *, refresh: bool = True) -> bool:
        """Close a task."""
        close_fn = getattr(self.api, "close_task", None)
        if callable(close_fn):
            result = await close_fn(task_id)
        else:
            await self._async_task_action(task_id, "close")
            result = True
        self._task_lookup.pop(task_id, None)
        if refresh:
            await self.async_refresh()
        return result

    async def async_reopen_task(self, task_id: str, *, refresh: bool = True) -> bool:
        """Reopen a task."""
        reopen_fn = getattr(self.api, "reopen_task", None)
        if callable(reopen_fn):
            result = await reopen_fn(task_id)
        else:
            await self._async_task_action(task_id, "reopen")
            result = True
        self._task_lookup.pop(task_id, None)
        if refresh:
            await self.async_refresh()
        return result

    async def async_delete_task(self, task_id: str, *, refresh: bool = True) -> bool:
        """Delete a task."""
        result = await self.api.delete_task(task_id)
        self._task_lookup.pop(task_id, None)
        if refresh:
            await self.async_refresh()
        return result

    async def async_refresh_task(self, task_id: str) -> None:
        """Fetch a single task and update local state."""
        try:
            task = await self.api.get_task(task_id)
        except Exception as err:  # broad except: Todoist SDK raises many types
            self.logger.warning("Failed to fetch task %s: %s", task_id, err)
            await self.async_refresh()
            return

        existing = self._task_lookup.get(task_id)
        if existing and self.data:
            tasks = list(self.data.tasks)
            for index, current in enumerate(tasks):
                if current.id == task_id:
                    tasks[index] = task
                    break
            else:
                tasks.append(task)
            self._task_lookup[task_id] = task
            self.async_set_updated_data(
                TodoistData(
                    tasks=tasks,
                    projects=self.data.projects,
                    labels=self.data.labels,
                    last_update=dt_util.utcnow().timestamp(),
                )
            )
        else:
            self._task_lookup[task_id] = task
            await self.async_refresh()
