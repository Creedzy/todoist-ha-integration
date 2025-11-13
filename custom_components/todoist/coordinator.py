"""DataUpdateCoordinator for the Todoist component."""

import asyncio
from datetime import date, datetime, timedelta
import logging
import time
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


def _task_key(task: Any) -> str | None:
    """Return the string key for a Todoist task-like object."""

    if task is None:
        return None

    identifier = getattr(task, "id", None) or getattr(task, "task_id", None)
    if identifier is None:
        return None
    return str(identifier)


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

    def _log_timing(self, operation: str, started: float, **context: Any) -> None:
        """Emit a timing message for coordinator operations."""

        elapsed = (time.perf_counter() - started) * 1000
        extras = [f"{key}={value}" for key, value in context.items() if value is not None]
        suffix = f" ({', '.join(extras)})" if extras else ""
        self.logger.info("[TodoistCoordinator] %s in %.2f ms%s", operation, elapsed, suffix)

    async def _async_update_data(self) -> TodoistData:
        """Fetch data from the Todoist API."""
        started = time.perf_counter()
        task_count = project_count = label_count = 0
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
            self._task_lookup = {}
            for task in all_tasks:
                key = _task_key(task)
                if key is not None:
                    self._task_lookup[key] = task
            task_count = len(all_tasks)
            project_list = [project async for page in projects for project in page]
            label_list = [label async for page in labels for label in page]
            project_count = len(project_list)
            label_count = len(label_list)
            return TodoistData(
                tasks=all_tasks,
                projects=project_list,
                labels=label_list,
                last_update=dt_util.utcnow().timestamp(),
            )
        except Exception as err:
            self.logger.error("Error communicating with API: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        finally:
            self._log_timing(
                "_async_update_data",
                started,
                tasks=task_count,
                projects=project_count,
                labels=label_count,
            )

    async def async_add_task(self, data: dict, *, refresh: bool = True) -> Any:
        """Add a task."""
        started = time.perf_counter()
        task = await self.api.add_task(**data)
        key = _task_key(task)
        if key is not None:
            self._task_lookup[key] = task
        if refresh:
            await self.async_refresh()
        self._log_timing("async_add_task", started, refresh=refresh, task_id=_task_key(task))
        return task

    async def async_update_task(self, task_id: str, data: dict, *, refresh: bool = True) -> bool:
        """Update a task."""
        started = time.perf_counter()
        sanitized = {key: value for key, value in data.items() if key != "task_id"}
        result = await self.api.update_task(task_id, **sanitized)
        if refresh:
            self._task_lookup.pop(str(task_id), None)
            await self.async_refresh()
        self._log_timing("async_update_task", started, refresh=refresh, task_id=task_id)
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
        started = time.perf_counter()
        close_fn = getattr(self.api, "close_task", None)
        if callable(close_fn):
            result = await close_fn(task_id)
        else:
            await self._async_task_action(task_id, "close")
            result = True
        if refresh:
            self._task_lookup.pop(str(task_id), None)
            await self.async_refresh()
        self._log_timing("async_close_task", started, refresh=refresh, task_id=task_id)
        return result

    async def async_reopen_task(self, task_id: str, *, refresh: bool = True) -> bool:
        """Reopen a task."""
        started = time.perf_counter()
        reopen_fn = getattr(self.api, "reopen_task", None)
        if callable(reopen_fn):
            result = await reopen_fn(task_id)
        else:
            await self._async_task_action(task_id, "reopen")
            result = True
        if refresh:
            self._task_lookup.pop(str(task_id), None)
            await self.async_refresh()
        self._log_timing("async_reopen_task", started, refresh=refresh, task_id=task_id)
        return result

    async def async_delete_task(self, task_id: str, *, refresh: bool = True) -> bool:
        """Delete a task."""
        started = time.perf_counter()
        result = await self.api.delete_task(task_id)
        self._task_lookup.pop(str(task_id), None)
        if refresh:
            await self.async_refresh()
        self._log_timing("async_delete_task", started, refresh=refresh, task_id=task_id)
        return result

    async def async_refresh_task(self, task_id: str) -> None:
        """Fetch a single task and update local state."""
        started = time.perf_counter()
        try:
            task = await self.api.get_task(task_id)
        except Exception as err:  # broad except: Todoist SDK raises many types
            self.logger.warning("Failed to fetch task %s: %s", task_id, err)
            await self.async_refresh()
            return

        key = _task_key(task)
        if key is None:
            await self.async_refresh()
            return

        existing = self._task_lookup.get(key)
        cached_match = existing is not None
        tasks_snapshot = None
        if not cached_match and self.data:
            for candidate in self.data.tasks:
                if _task_key(candidate) == key:
                    existing = candidate
                    cached_match = True
                    break

        if self.data:
            tasks_snapshot = list(self.data.tasks)

        if tasks_snapshot is not None:
            if cached_match:
                for index, current in enumerate(tasks_snapshot):
                    if _task_key(current) == key:
                        tasks_snapshot[index] = task
                        break
                else:
                    tasks_snapshot.append(task)
            else:
                # Task not previously cached; add or remove based on completion flag.
                if getattr(task, "is_deleted", False):
                    tasks_snapshot = [t for t in tasks_snapshot if _task_key(t) != key]
                else:
                    tasks_snapshot.append(task)

            self._task_lookup[key] = task
            self.async_set_updated_data(
                TodoistData(
                    tasks=tasks_snapshot,
                    projects=self.data.projects,
                    labels=self.data.labels,
                    last_update=dt_util.utcnow().timestamp(),
                )
            )
        else:
            self._task_lookup[key] = task
            await self.async_refresh()
            self._log_timing("async_refresh_task", started, task_id=task_id, cache_hit=cached_match)
            return

        self._log_timing("async_refresh_task", started, task_id=task_id, cache_hit=cached_match)

    def get_cached_task(self, task_id: str) -> Any | None:
        """Return the cached Todoist task, if available."""

        return self._task_lookup.get(str(task_id))
