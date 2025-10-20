"""A todo platform for Todoist."""
import asyncio
import datetime
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
from todoist_api_python.models import Task

from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import TodoistDataUpdateCoordinator
from .types import TodoistData


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


def _task_api_data(item: TodoItem, api_data: Task | None = None) -> dict[str, Any]:
    """Convert a TodoItem to the set of add or update arguments."""
    item_data: dict[str, Any] = {"content": item.summary}
    if item.description is not None:
        item_data["description"] = item.description
    if item.due is not None:
        if isinstance(item.due, datetime.datetime):
            item_data["due_datetime"] = item.due.isoformat()
        else:
            item_data["due_date"] = item.due.isoformat()
        if api_data and api_data.due:
            item_data["due_string"] = api_data.due.string
    else:
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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        return {"tasks": [task.to_dict() for task in self.coordinator.data.tasks]}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data is None:
            self._attr_todo_items = None
        else:
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
                    if task.due.datetime:
                        due = dt_util.as_local(
                            datetime.datetime.fromisoformat(task.due.datetime)
                        )
                    else:
                        due = datetime.date.fromisoformat(task.due.date)
                items.append(
                    TodoItem(
                        summary=task.content,
                        uid=task.id,
                        status=status,
                        due=due,
                        description=task.description,
                    )
                )
            self._attr_todo_items = items
        super()._handle_coordinator_update()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a To-do item."""
        await self.coordinator.async_add_task(
            {**_task_api_data(item), "project_id": self._project_id}
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update a To-do item."""
        uid: str = cast(str, item.uid)
        await self.coordinator.async_update_task(uid, _task_api_data(item))
        if item.status is not None:
            if item.status == TodoItemStatus.COMPLETED:
                await self.coordinator.async_close_task(uid)
            else:
                await self.coordinator.async_reopen_task(uid)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete a To-do item."""
        await asyncio.gather(
            *[self.coordinator.async_delete_task(uid) for uid in uids]
        )
