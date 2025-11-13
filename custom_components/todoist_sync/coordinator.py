"""DataUpdateCoordinator for the Todoist Sync component."""

from datetime import date, datetime, timedelta
import logging
import time
import uuid
from typing import Any, Iterable, Sequence

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .sync_api import (
    CommandResult,
    SyncDue,
    SyncResponse,
    SyncTask,
    TodoistSyncAuthError,
    TodoistSyncClient,
    TodoistSyncError,
    TodoistSyncRateLimitError,
    TodoistSyncRequestError,
    TodoistSyncTokenReset,
)
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
    ) -> None:
        """Initialize the Todoist Sync coordinator."""
        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self._session = async_get_clientsession(hass)
        self._token = entry.data.get(CONF_TOKEN)
        if not self._token:
            raise HomeAssistantError("Todoist token missing from config entry")
        self._task_lookup: dict[str, Any] = {}
        self._sync_client = TodoistSyncClient(
            self._session,
            self._token,
            logger=logger,
        )
        self._sync_resources: tuple[str, ...] = ("items", "projects", "labels")
        self._sync_token: str = "*"

    def _log_timing(self, operation: str, started: float, **context: Any) -> None:
        """Emit a timing message for coordinator operations."""

        elapsed = (time.perf_counter() - started) * 1000
        extras = [f"{key}={value}" for key, value in context.items() if value is not None]
        suffix = f" ({', '.join(extras)})" if extras else ""
        self.logger.info("[TodoistCoordinator] %s in %.2f ms%s", operation, elapsed, suffix)

    def _rebuild_task_lookup(self, tasks: Iterable[Any]) -> None:
        """Recreate the fast task lookup mapping."""

        self._task_lookup = {}
        for task in tasks:
            key = _task_key(task)
            if key is not None:
                self._task_lookup[key] = task

    async def _async_update_data(self) -> TodoistData:
        """Fetch data from the Todoist API via the Sync endpoint."""
        started = time.perf_counter()
        task_count = project_count = label_count = 0
        try:
            response = await self._perform_sync()
            data = self._apply_sync_response(response)
            task_count = len(data.tasks)
            project_count = len(data.projects)
            label_count = len(data.labels)
            self._sync_token = response.sync_token
            self._rebuild_task_lookup(data.tasks)
            self._log_sync_response(response, task_count, project_count, label_count)
            return data
        except TodoistSyncRateLimitError as err:
            raise UpdateFailed("Todoist Sync API rate limited") from err
        except TodoistSyncAuthError as err:
            raise UpdateFailed("Todoist Sync API authentication failed") from err
        except TodoistSyncTokenReset as err:
            raise UpdateFailed("Todoist Sync token reset loop detected") from err
        except (TodoistSyncError, TodoistSyncRequestError) as err:
            raise UpdateFailed(f"Error communicating with Todoist Sync API: {err}") from err
        finally:
            self._log_timing(
                "_async_update_data",
                started,
                tasks=task_count,
                projects=project_count,
                labels=label_count,
                sync_token=self._sync_token,
                transport="sync",
            )

    async def async_add_task(self, data: dict, *, refresh: bool = True) -> Any:
        """Add a task."""
        started = time.perf_counter()
        temp_id = uuid.uuid4().hex
        args = self._prepare_item_args(data)
        command_uuid = uuid.uuid4().hex
        command = {
            "type": "item_add",
            "uuid": command_uuid,
            "temp_id": temp_id,
            "args": args,
        }
        result = await self._execute_commands((command,))
        real_id = result.temp_id_mapping.get(temp_id)
        if real_id is None and result.sync.tasks:
            real_id = result.sync.tasks[-1].id
        self._log_timing(
            "async_add_task",
            started,
            task_id=real_id,
            refresh=refresh,
            transport="sync",
        )
        return self._task_lookup.get(str(real_id)) if real_id else None

    async def async_update_task(
        self,
        task_id: str,
        data: dict,
        *,
        close: bool = False,
        reopen: bool = False,
    ) -> CommandResult | None:
        """Update (and optionally close/reopen) a task via Sync commands."""

        if close and reopen:
            raise HomeAssistantError("A task cannot be closed and reopened in the same command")

        started = time.perf_counter()
        payload = {key: value for key, value in data.items() if key != "task_id"}
        update_args = self._prepare_item_args(payload, task_id=task_id)
        body_without_id = {key: value for key, value in update_args.items() if key != "id"}

        commands: list[dict[str, Any]] = []
        if body_without_id:
            commands.append({
                "type": "item_update",
                "args": update_args,
            })
        if close:
            commands.append({
                "type": "item_complete",
                "args": {"id": str(task_id)},
            })
        if reopen:
            commands.append({
                "type": "item_uncomplete",
                "args": {"id": str(task_id)},
            })

        if not commands:
            self._log_timing(
                "async_update_task",
                started,
                task_id=task_id,
                close=close,
                reopen=reopen,
                updated=False,
                transport="sync",
            )
            return None

        result = await self._execute_commands(commands, resource_types=("items",))
        delta_tasks = sum(1 for task in result.sync.tasks if _task_key(task))
        self._log_timing(
            "async_update_task",
            started,
            task_id=task_id,
            close=close,
            reopen=reopen,
            updated=bool(body_without_id),
            command_count=len(commands),
            delta_tasks=delta_tasks,
            transport="sync",
        )
        return result

    async def async_close_task(self, task_id: str, *, refresh: bool = True) -> bool:
        """Close a task."""
        started = time.perf_counter()
        await self._execute_commands(({
            "type": "item_complete",
            "args": {"id": str(task_id)},
        },), resource_types=("items",))
        self._log_timing(
            "async_close_task",
            started,
            task_id=task_id,
            refresh=refresh,
            transport="sync",
        )
        return True

    async def async_reopen_task(self, task_id: str, *, refresh: bool = True) -> bool:
        """Reopen a task."""
        started = time.perf_counter()
        await self._execute_commands(({
            "type": "item_uncomplete",
            "args": {"id": str(task_id)},
        },), resource_types=("items",))
        self._log_timing(
            "async_reopen_task",
            started,
            task_id=task_id,
            refresh=refresh,
            transport="sync",
        )
        return True

    async def async_delete_task(self, task_id: str, *, refresh: bool = True) -> bool:
        """Delete a task."""
        started = time.perf_counter()
        await self._execute_commands(({
            "type": "item_delete",
            "args": {"id": str(task_id)},
        },), resource_types=("items",))
        self._log_timing(
            "async_delete_task",
            started,
            task_id=task_id,
            refresh=refresh,
            transport="sync",
        )
        return True

    async def async_refresh_task(self, task_id: str) -> None:
        """Fetch a single task and update local state."""
        started = time.perf_counter()
        task_id_str = str(task_id)
        try:
            response = await self._perform_sync(resources=("items",))
            data = self._apply_sync_response(response)
            self._sync_token = response.sync_token
            self._rebuild_task_lookup(data.tasks)
            self.async_set_updated_data(data)
            cache_hit = any(task.id == task_id_str for task in response.tasks)
            self._log_timing(
                "async_refresh_task",
                started,
                task_id=task_id,
                cache_hit=cache_hit,
                delta=len(response.tasks),
                transport="sync-delta",
            )
            if not cache_hit and self.get_cached_task(task_id) is None:
                fallback_started = time.perf_counter()
                await self.async_refresh()
                self._log_timing(
                    "async_refresh_task_full",
                    fallback_started,
                    task_id=task_id,
                    transport="sync-full",
                )
        except TodoistSyncRateLimitError as err:
            self.logger.warning(
                "Todoist Sync rate limited while refreshing task %s: %s", task_id, err
            )
            fallback_started = time.perf_counter()
            await self.async_refresh()
            self._log_timing(
                "async_refresh_task_full",
                fallback_started,
                task_id=task_id,
                transport="sync-full",
                reason="rate_limited",
            )
        except TodoistSyncTokenReset:
            self.logger.warning(
                "Todoist Sync token reset while refreshing task %s; forcing full sync", task_id
            )
            self._sync_token = "*"
            fallback_started = time.perf_counter()
            await self.async_refresh()
            self._log_timing(
                "async_refresh_task_full",
                fallback_started,
                task_id=task_id,
                transport="sync-full",
                reason="token_reset",
            )
        except (TodoistSyncError, TodoistSyncRequestError, TodoistSyncAuthError) as err:
            self.logger.warning(
                "Todoist Sync refresh failed for task %s (%s); falling back to full refresh",
                task_id,
                err,
            )
            fallback_started = time.perf_counter()
            await self.async_refresh()
            self._log_timing(
                "async_refresh_task_full",
                fallback_started,
                task_id=task_id,
                transport="sync-full",
                reason="error",
            )

    def get_cached_task(self, task_id: str) -> Any | None:
        """Return the cached Todoist task, if available."""

        return self._task_lookup.get(str(task_id))

    async def _perform_sync(
        self,
        resources: Iterable[str] | None = None,
        *,
        sync_token: str | None = None,
    ) -> SyncResponse:
        """Call the Sync API and handle token reset retries."""

        token = (sync_token if sync_token is not None else self._sync_token) or "*"
        resource_types = tuple(resources or self._sync_resources)
        try:
            return await self._sync_client.sync(resource_types, sync_token=token)
        except TodoistSyncTokenReset:
            self.logger.warning("Todoist Sync token reset requested; performing full sync")
            self._sync_token = "*"
            return await self._sync_client.sync(resource_types, sync_token="*")

    async def _execute_commands(
        self,
        commands: Sequence[dict[str, Any]],
        *,
        resource_types: Iterable[str] | None = None,
    ) -> CommandResult:
        """Execute Sync commands and merge the resulting delta."""

        if not commands:
            raise HomeAssistantError("No Todoist commands provided")

        resources = tuple(resource_types or self._sync_resources)
        token = self._sync_token or "*"
        started = time.perf_counter()
        try:
            result = await self._sync_client.execute_commands(
                list(commands),
                sync_token=token,
                resource_types=resources,
            )
        except TodoistSyncTokenReset:
            self.logger.warning(
                "Todoist Sync token reset during command execution; retrying with full sync"
            )
            self._sync_token = "*"
            result = await self._sync_client.execute_commands(
                list(commands),
                sync_token="*",
                resource_types=resources,
            )
        except TodoistSyncRateLimitError as err:
            raise HomeAssistantError("Todoist Sync API rate limited") from err
        except TodoistSyncAuthError as err:
            raise HomeAssistantError("Todoist Sync API authentication failed") from err
        except (TodoistSyncError, TodoistSyncRequestError) as err:
            raise HomeAssistantError(f"Todoist command failed: {err}") from err

        data = self._apply_sync_response(result.sync)
        self._sync_token = result.sync.sync_token
        self._rebuild_task_lookup(data.tasks)
        self.async_set_updated_data(data)
        self._log_sync_response(
            result.sync,
            len(data.tasks),
            len(data.projects),
            len(data.labels),
        )

        if result.failed:
            errors = ", ".join(
                f"{failure.command_uuid}:{failure.error or failure.error_code}"
                for failure in result.failed
            )
            raise HomeAssistantError(f"Todoist command(s) failed: {errors}")

        self._log_timing(
            "sync_commands",
            started,
            command_count=len(commands),
            delta_tasks=len(result.sync.tasks),
            resources=resources,
            transport="sync",
        )

        return result

    def _prepare_item_args(self, payload: dict[str, Any], *, task_id: str | None = None) -> dict[str, Any]:
        """Normalise task payload for Sync commands."""

        args: dict[str, Any] = {}
        if task_id is not None:
            args["id"] = str(task_id)

        for key, value in payload.items():
            if value is None:
                continue

            if key in {"due_datetime", "due_date"}:
                if isinstance(value, datetime):
                    dt_value = value
                    if dt_value.tzinfo is None:
                        dt_value = dt_value.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                    dt_value = dt_util.as_utc(dt_value)
                    args[key] = dt_value.isoformat().replace("+00:00", "Z")
                elif isinstance(value, date):
                    args[key] = value.isoformat()
                else:
                    args[key] = str(value)
                continue

            if key in {"project_id", "parent_id"}:
                args[key] = str(value)
                continue

            if key == "label_ids":
                args[key] = [str(label) for label in value]
                continue

            if key == "priority":
                try:
                    args[key] = int(value)
                except (TypeError, ValueError):
                    continue
                continue

            args[key] = value

        return args

    def _apply_sync_response(self, response: SyncResponse) -> TodoistData:
        """Merge the Sync response with the cached state."""

        if response.full_sync or self.data is None:
            tasks = self._filter_tasks(response.tasks)
            projects = self._filter_projects(response.projects)
            labels = self._filter_labels(response.labels)
        else:
            tasks = self._merge_tasks(self.data.tasks, response.tasks)
            projects = self._merge_projects(self.data.projects, response.projects)
            labels = self._merge_labels(self.data.labels, response.labels)

        return TodoistData(
            tasks=tasks,
            projects=projects,
            labels=labels,
            last_update=dt_util.utcnow().timestamp(),
        )

    def _filter_tasks(self, tasks: Iterable[Any]) -> list[Any]:
        return sorted(
            [
                task
                for task in tasks
                if not getattr(task, "is_deleted", False)
                and not getattr(task, "is_archived", False)
            ],
            key=lambda task: (
                getattr(task, "project_id", "") or "",
                getattr(task, "order", 0) or 0,
                getattr(task, "id", ""),
            ),
        )

    def _merge_tasks(self, existing: Iterable[Any], updates: Iterable[Any]) -> list[Any]:
        task_map: dict[str, Any] = {}
        for task in existing:
            key = _task_key(task)
            if key is not None and not getattr(task, "is_deleted", False):
                task_map[key] = task
        for update in updates:
            key = _task_key(update)
            if key is None:
                continue
            if getattr(update, "is_deleted", False) or getattr(update, "is_archived", False):
                task_map.pop(key, None)
                continue
            task_map[key] = update
        return self._filter_tasks(task_map.values())

    def _filter_projects(self, projects: Iterable[Any]) -> list[Any]:
        return sorted(
            [
                project
                for project in projects
                if not getattr(project, "is_deleted", False)
                and not getattr(project, "is_archived", False)
            ],
            key=lambda project: (
                getattr(project, "order", 0) or 0,
                getattr(project, "name", ""),
            ),
        )

    def _merge_projects(self, existing: Iterable[Any], updates: Iterable[Any]) -> list[Any]:
        project_map: dict[str, Any] = {}
        for project in existing:
            key = _task_key(project) or getattr(project, "id", None)
            if key is not None and not getattr(project, "is_deleted", False):
                project_map[str(key)] = project
        for update in updates:
            key = _task_key(update) or getattr(update, "id", None)
            if key is None:
                continue
            str_key = str(key)
            if getattr(update, "is_deleted", False) or getattr(update, "is_archived", False):
                project_map.pop(str_key, None)
                continue
            project_map[str_key] = update
        return self._filter_projects(project_map.values())

    def _filter_labels(self, labels: Iterable[Any]) -> list[Any]:
        return sorted(
            [label for label in labels if not getattr(label, "is_deleted", False)],
            key=lambda label: (
                getattr(label, "order", 0) or 0,
                getattr(label, "name", ""),
            ),
        )

    def _merge_labels(self, existing: Iterable[Any], updates: Iterable[Any]) -> list[Any]:
        label_map: dict[str, Any] = {}
        for label in existing:
            key = getattr(label, "id", None)
            if key is not None and not getattr(label, "is_deleted", False):
                label_map[str(key)] = label
        for update in updates:
            key = getattr(update, "id", None)
            if key is None:
                continue
            str_key = str(key)
            if getattr(update, "is_deleted", False):
                label_map.pop(str_key, None)
                continue
            label_map[str_key] = update
        return self._filter_labels(label_map.values())

    def _log_sync_response(
        self,
        response: SyncResponse,
        task_count: int,
        project_count: int,
        label_count: int,
    ) -> None:
        """Emit debug logging for Sync responses."""

        token_suffix = (
            response.sync_token[-8:] if len(response.sync_token) >= 8 else response.sync_token
        )
        self.logger.debug(
            "Sync delta applied | full_sync=%s updates=(tasks=%d, projects=%d, labels=%d) totals=(tasks=%d, projects=%d, labels=%d) token_suffix=%s",
            response.full_sync,
            len(response.tasks),
            len(response.projects),
            len(response.labels),
            task_count,
            project_count,
            label_count,
            token_suffix,
        )

    def _convert_task_from_rest(self, task: Any) -> SyncTask:
        """Translate a REST SDK task into the Sync model."""

        if isinstance(task, SyncTask):
            return task

        due_obj = getattr(task, "due", None)
        due = None
        if due_obj is not None:
            due = SyncDue(
                date=getattr(due_obj, "date", None),
                datetime=getattr(due_obj, "datetime", None),
                string=getattr(due_obj, "string", None),
                timezone=getattr(due_obj, "timezone", None),
                is_recurring=getattr(due_obj, "is_recurring", None),
            )

        labels_raw = getattr(task, "label_ids", None)
        if labels_raw is None:
            labels_raw = getattr(task, "labels", None)
        label_ids = tuple(str(label) for label in (labels_raw or []))

        priority = getattr(task, "priority", None)
        try:
            priority = int(priority) if priority is not None else None
        except (TypeError, ValueError):
            priority = None

        order = getattr(task, "item_order", None)
        if order is None:
            order = getattr(task, "order", None)
        try:
            order = int(order) if order is not None else None
        except (TypeError, ValueError):
            order = None

        is_completed = getattr(task, "is_completed", None)
        if is_completed is None:
            is_completed = getattr(task, "completed", False)

        parent_id = getattr(task, "parent_id", None)
        project_id = getattr(task, "project_id", None)

        return SyncTask(
            id=str(getattr(task, "id")),
            project_id=str(project_id) if project_id is not None else None,
            content=getattr(task, "content", "") or "",
            description=getattr(task, "description", None),
            is_completed=bool(is_completed),
            parent_id=str(parent_id) if parent_id is not None else None,
            label_ids=label_ids,
            priority=priority,
            order=order,
            due=due,
            is_deleted=bool(getattr(task, "is_deleted", False)),
            is_archived=bool(getattr(task, "is_archived", False)),
        )
