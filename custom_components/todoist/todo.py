"""A todo platform for Todoist."""
import asyncio
import datetime
import logging
import time
from typing import Any, cast

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.util import dt as dt_util


def _parse_due_datetime(due_obj: Any) -> datetime.datetime | None:
    """Return a timezone-aware datetime for a Todoist due entry."""

    raw_datetime = getattr(due_obj, "datetime", None)
    if not raw_datetime:
        raw_date = getattr(due_obj, "date", None)
        if isinstance(raw_date, str) and "T" in raw_date:
            raw_datetime = raw_date

    if not raw_datetime:
        return None

    parsed = dt_util.parse_datetime(raw_datetime)
    if parsed is None:
        try:
            parsed = datetime.datetime.fromisoformat(raw_datetime)
        except (TypeError, ValueError):
            return None

    if parsed.tzinfo is None:
        timezone = getattr(due_obj, "timezone", None)
        tzinfo = dt_util.get_time_zone(timezone) if timezone else dt_util.DEFAULT_TIME_ZONE
        parsed = parsed.replace(tzinfo=tzinfo)

    return parsed


def _parse_due_date(due_obj: Any) -> datetime.date | None:
    """Return a date object for a Todoist due entry."""

    raw_date = getattr(due_obj, "date", None)
    if raw_date is None:
        return None

    if isinstance(raw_date, datetime.date):
        return raw_date

    if isinstance(raw_date, str):
        raw_value = raw_date.split("T")[0]
        parsed = dt_util.parse_date(raw_value)
        if parsed is not None:
            return parsed
        try:
            return datetime.date.fromisoformat(raw_value)
        except ValueError:
            return None

    return None

from .const import DOMAIN
from .coordinator import TodoistDataUpdateCoordinator
from .types import TodoistData


_LOGGER = logging.getLogger(__name__)


def _payload_requires_update(task: Any | None, payload: dict[str, Any]) -> bool:
    """Return True if the Todoist payload differs from the cached task."""

    if task is None:
        return True

    content = payload.get("content")
    if content is not None and getattr(task, "content", None) != content:
        return True

    description = payload.get("description")
    if description is not None and getattr(task, "description", None) != description:
        return True

    due_info = getattr(task, "due", None)
    if "due_datetime" in payload:
        due_dt = payload["due_datetime"]
        existing_iso = getattr(due_info, "datetime", None)
        if existing_iso is None:
            return True

        def _normalise_datetime(value: Any) -> datetime.datetime | None:
            candidate = value
            if not isinstance(candidate, datetime.datetime):
                parsed = dt_util.parse_datetime(str(candidate))
                if parsed is None:
                    try:
                        parsed = datetime.datetime.fromisoformat(str(candidate))
                    except (TypeError, ValueError):
                        return None
                candidate = parsed
            if candidate.tzinfo is None:
                candidate = candidate.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            return dt_util.as_utc(candidate)

        desired_dt = _normalise_datetime(due_dt)
        existing_dt = _normalise_datetime(existing_iso)
        if desired_dt is None or existing_dt is None:
            return True
        if desired_dt != existing_dt:
            return True

    if "due_date" in payload:
        due_date = payload["due_date"]
        due_date_str = due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date)
        existing_date = getattr(due_info, "date", None)
        if existing_date != due_date_str:
            return True

    if "due_string" in payload:
        due_string = payload["due_string"]
        existing_string = getattr(due_info, "string", None)
        if due_string == "no date" and not existing_string and due_info is None:
            pass
        elif due_info is None or existing_string != due_string:
            return True

    # No relevant differences detected.
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Todoist todo platform config entry."""
    coordinator: TodoistDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    projects = coordinator.data.projects
    async_add_entities(
        TodoistTodoListEntity(coordinator, project.id, project.name)
        for project in projects
    )


def _task_api_data(item: TodoItem, api_data: Any | None = None) -> dict[str, Any]:
    """Convert a TodoItem to the set of add or update arguments."""
    item_data: dict[str, Any] = {"content": item.summary}
    if item.description is not None:
        item_data["description"] = item.description
    if item.due is not None:
        if isinstance(item.due, datetime.datetime):
            due_dt = item.due
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            item_data["due_datetime"] = due_dt
        elif isinstance(item.due, datetime.date):
            item_data["due_date"] = item.due
        else:
            item_data["due_string"] = str(item.due)
        if api_data and getattr(api_data, "due", None):
            # Preserve Todoist's natural language string when we know it.
            due_string = getattr(api_data.due, "string", None)
            if due_string:
                item_data.setdefault("due_string", due_string)
    elif api_data and getattr(api_data, "due", None):
        # Only clear the due date if the source task actually has one.
        item_data["due_string"] = "no date"
    return item_data


class TodoistTodoListEntity(
    CoordinatorEntity[TodoistDataUpdateCoordinator], TodoListEntity
):
    """A Todoist TodoListEntity."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(
        self,
        coordinator: TodoistDataUpdateCoordinator,
        project_id: str,
        project_name: str,
    ) -> None:
        """Initialize TodoistTodoListEntity."""
        super().__init__(coordinator=coordinator)
        self._project_id = project_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}-{project_id}"
        self._attr_name = project_name

    def _log_timing(self, label: str, started: float, **context: Any) -> None:
        """Log the elapsed time for a given label."""

        elapsed = (time.perf_counter() - started) * 1000
        context_items = [f"{key}={value}" for key, value in context.items() if value is not None]
        suffix = f" ({', '.join(context_items)})" if context_items else ""
        _LOGGER.info("[TodoEntity:%s] %s in %.2f ms%s", self._attr_name, label, elapsed, suffix)

    def _log_debug(self, message: str, **context: Any) -> None:
        """Emit a structured debug log for this entity."""

        context_items = {key: value for key, value in context.items() if value is not None}
        _LOGGER.debug("[TodoEntity:%s] %s | %s", self._attr_name, message, context_items)

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Get the current set of To-do items."""
        started = time.perf_counter()
        self._log_debug("Building todo_items snapshot", project_id=self._project_id)
        if self.coordinator.data is None:
            self._log_timing("todo_items", started, status="no-data")
            return None
        items = []
        for task in self.coordinator.data.tasks:
            if task.project_id != self._project_id:
                continue
            if task.parent_id is not None:
                continue
            status = (
                TodoItemStatus.COMPLETED
                if task.is_completed
                else TodoItemStatus.NEEDS_ACTION
            )
            due: datetime.date | datetime.datetime | None = None
            if task.due:
                due_datetime = _parse_due_datetime(task.due)
                if due_datetime is not None:
                    due = dt_util.as_local(due_datetime)
                else:
                    due_date = _parse_due_date(task.due)
                    if due_date is not None:
                        due = dt_util.start_of_local_day(due_date)
            items.append(
                TodoItem(
                    summary=task.content,
                    uid=task.id,
                    status=status,
                    due=due,
                    description=task.description,
                )
            )
        self._log_timing("todo_items", started, count=len(items))
        return items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a To-do item."""
        started = time.perf_counter()
        payload = {**_task_api_data(item), "project_id": self._project_id}
        self._log_debug("Creating Todoist task", payload=payload)
        result_task = await self.coordinator.async_add_task(payload)
        transport = "sync"
        if result_task is None:
            transport = "sync-fallback"
            self._schedule_full_refresh()
        self._log_timing(
            "async_create_todo_item",
            started,
            project_id=self._project_id,
            transport=transport,
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update a To-do item."""
        uid: str = cast(str, item.uid)
        status = item.status
        cached_task = self.coordinator.get_cached_task(uid)
        payload = _task_api_data(item, cached_task)
        needs_update = _payload_requires_update(cached_task, payload)
        started = time.perf_counter()
        self._log_debug(
            "Updating Todoist task",
            uid=uid,
            status=status,
            needs_update=needs_update,
            payload=payload,
        )

        update_payload = payload if needs_update else {}

        def _command_updated_task(result: Any | None) -> bool:
            return bool(
                result
                and getattr(result, "sync", None)
                and any(getattr(task, "id", None) == uid for task in result.sync.tasks)
            )

        if status == TodoItemStatus.COMPLETED:
            result = await self.coordinator.async_update_task(uid, update_payload, close=True)
            fallback = not _command_updated_task(result)
            if fallback:
                self._schedule_task_refresh(uid)
            self._log_timing(
                "async_update_todo_item",
                started,
                uid=uid,
                status="completed",
                updated=needs_update,
                transport="sync" if not fallback else "sync-fallback",
            )
            return

        if status == TodoItemStatus.NEEDS_ACTION:
            result = await self.coordinator.async_update_task(uid, update_payload, reopen=True)
            fallback = not _command_updated_task(result)
            if fallback:
                self._schedule_task_refresh(uid)
            self._log_timing(
                "async_update_todo_item",
                started,
                uid=uid,
                status="reopened",
                updated=needs_update,
                transport="sync" if not fallback else "sync-fallback",
            )
            return

        transport = "sync"
        if update_payload:
            result = await self.coordinator.async_update_task(uid, update_payload)
            if not _command_updated_task(result):
                transport = "sync-fallback"
                self._schedule_task_refresh(uid)
        self._log_timing(
            "async_update_todo_item",
            started,
            uid=uid,
            status="needs_action",
            updated=needs_update,
            transport=transport,
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete a To-do item."""
        if not uids:
            return

        started = time.perf_counter()
        self._log_debug("Deleting Todoist tasks", uids=uids)
        *leading, final = uids
        for uid in leading:
            await self.coordinator.async_delete_task(uid, refresh=False)
        await self.coordinator.async_delete_task(final, refresh=False)
        self._schedule_full_refresh()
        self._log_timing(
            "async_delete_todo_items",
            started,
            count=len(uids),
            transport="sync",
        )

    def _schedule_task_refresh(self, task_id: str) -> None:
        """Refresh a single task in the background."""

        if not task_id or self.hass is None:
            return
        self.hass.async_create_task(self.coordinator.async_refresh_task(task_id))

    def _schedule_full_refresh(self) -> None:
        """Trigger a full coordinator refresh without blocking."""

        if self.hass is None:
            return
        self.hass.async_create_task(self.coordinator.async_refresh())
