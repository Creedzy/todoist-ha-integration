"""Services for the Todoist component."""
from __future__ import annotations

import logging
import time

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


_LOGGER = logging.getLogger(__name__)


def async_register_services(hass: HomeAssistant) -> None:
    """Register the services for the Todoist component."""

    async def async_new_task(call: ServiceCall) -> None:
        """Create a new task."""
        started = time.perf_counter()
        _LOGGER.info("[Service] %s invoked", SERVICE_NEW_TASK)
        coordinator: TodoistDataUpdateCoordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.async_add_task(call.data)
        _LOGGER.info(
            "[Service] %s completed in %.2f ms",
            SERVICE_NEW_TASK,
            (time.perf_counter() - started) * 1000,
        )

    async def async_update_task(call: ServiceCall) -> None:
        """Update a task."""
        started = time.perf_counter()
        _LOGGER.info("[Service] %s invoked", SERVICE_UPDATE_TASK)
        coordinator: TodoistDataUpdateCoordinator = next(iter(hass.data[DOMAIN].values()))
        task_id = call.data["task_id"]
        if not any(task.id == task_id for task in coordinator.data.tasks):
            raise HomeAssistantError(f"Task with id '{task_id}' not found.")
        payload = {key: value for key, value in call.data.items() if key != "task_id"}
        await coordinator.async_update_task(task_id, payload)
        _LOGGER.info(
            "[Service] %s completed in %.2f ms (task_id=%s)",
            SERVICE_UPDATE_TASK,
            (time.perf_counter() - started) * 1000,
            task_id,
        )

    async def async_get_task(call: ServiceCall) -> None:
        """Get a task."""
        started = time.perf_counter()
        _LOGGER.info("[Service] %s invoked", SERVICE_GET_TASK)
        coordinator: TodoistDataUpdateCoordinator = next(iter(hass.data[DOMAIN].values()))
        task_id = call.data["task_id"]
        task = next((task for task in coordinator.data.tasks if task.id == task_id), None)
        if not task:
            raise HomeAssistantError(f"Task with id '{task_id}' not found.")
        hass.bus.async_fire(
            f"{DOMAIN}_{SERVICE_GET_TASK}_response", {"task": task.to_dict()}
        )
        _LOGGER.info(
            "[Service] %s completed in %.2f ms (task_id=%s)",
            SERVICE_GET_TASK,
            (time.perf_counter() - started) * 1000,
            task_id,
        )

    async def async_get_all_tasks(call: ServiceCall) -> None:
        """Get all tasks."""
        started = time.perf_counter()
        _LOGGER.info("[Service] %s invoked", SERVICE_GET_ALL_TASKS)
        coordinator: TodoistDataUpdateCoordinator = next(iter(hass.data[DOMAIN].values()))
        tasks = [task.to_dict() for task in coordinator.data.tasks]
        hass.bus.async_fire(f"{DOMAIN}_{SERVICE_GET_ALL_TASKS}_response", {"tasks": tasks})
        _LOGGER.info(
            "[Service] %s completed in %.2f ms (count=%d)",
            SERVICE_GET_ALL_TASKS,
            (time.perf_counter() - started) * 1000,
            len(tasks),
        )

    hass.services.async_register(DOMAIN, SERVICE_NEW_TASK, async_new_task)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_TASK, async_update_task)
    hass.services.async_register(DOMAIN, SERVICE_GET_TASK, async_get_task)
    hass.services.async_register(DOMAIN, SERVICE_GET_ALL_TASKS, async_get_all_tasks)
