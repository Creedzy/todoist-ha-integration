"""Services for the Todoist component."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    SERVICE_GET_ALL_TASKS,
    SERVICE_GET_TASK,
    SERVICE_NEW_TASK,
    SERVICE_UPDATE_TASK,
)
from .coordinator import TodoistDataUpdateCoordinator


def async_register_services(hass: HomeAssistant) -> None:
    """Register the services for the Todoist component."""

    async def async_new_task(call: ServiceCall) -> None:
        """Create a new task."""
        coordinator: TodoistDataUpdateCoordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.async_add_task(call.data)

    async def async_update_task(call: ServiceCall) -> None:
        """Update a task."""
        coordinator: TodoistDataUpdateCoordinator = next(iter(hass.data[DOMAIN].values()))
        task_id = call.data["task_id"]
        if not any(task.id == task_id for task in coordinator.data.tasks):
            raise HomeAssistantError(f"Task with id '{task_id}' not found.")
        payload = {key: value for key, value in call.data.items() if key != "task_id"}
        await coordinator.async_update_task(task_id, payload)

    async def async_get_task(call: ServiceCall) -> None:
        """Get a task."""
        coordinator: TodoistDataUpdateCoordinator = next(iter(hass.data[DOMAIN].values()))
        task_id = call.data["task_id"]
        task = next((task for task in coordinator.data.tasks if task.id == task_id), None)
        if not task:
            raise HomeAssistantError(f"Task with id '{task_id}' not found.")
        hass.bus.async_fire(
            f"{DOMAIN}_{SERVICE_GET_TASK}_response", {"task": task.to_dict()}
        )

    async def async_get_all_tasks(call: ServiceCall) -> None:
        """Get all tasks."""
        coordinator: TodoistDataUpdateCoordinator = next(iter(hass.data[DOMAIN].values()))
        tasks = [task.to_dict() for task in coordinator.data.tasks]
        hass.bus.async_fire(f"{DOMAIN}_{SERVICE_GET_ALL_TASKS}_response", {"tasks": tasks})

    hass.services.async_register(DOMAIN, SERVICE_NEW_TASK, async_new_task)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_TASK, async_update_task)
    hass.services.async_register(DOMAIN, SERVICE_GET_TASK, async_get_task)
    hass.services.async_register(DOMAIN, SERVICE_GET_ALL_TASKS, async_get_all_tasks)
