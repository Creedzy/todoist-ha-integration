"""Support for Todoist calendars."""
from __future__ import annotations

import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import TodoistDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Todoist calendar platform config entry."""
    coordinator: TodoistDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    projects = coordinator.data.projects
    async_add_entities(
        TodoistCalendarEntity(coordinator, project.id, project.name)
        for project in projects
    )


class TodoistCalendarEntity(
    CoordinatorEntity[TodoistDataUpdateCoordinator], CalendarEntity
):
    """A calendar entity for a Todoist project."""

    def __init__(
        self,
        coordinator: TodoistDataUpdateCoordinator,
        project_id: str,
        project_name: str,
    ) -> None:
        """Initialize the Todoist calendar entity."""
        super().__init__(coordinator=coordinator)
        self._project_id = project_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}-{project_id}"
        self._attr_name = project_name
        self._event: CalendarEvent | None = None

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        return self._event

    def _compute_event_window(
        self, task
    ) -> tuple[datetime.datetime, datetime.datetime] | None:
        """Derive local start/end datetimes for a task's due information."""
        due = task.due
        if not due:
            return None

        due_datetime = getattr(due, "datetime", None)
        if due_datetime:
            if isinstance(due_datetime, datetime.datetime):
                start = dt_util.as_local(due_datetime)
            else:
                parsed_datetime = dt_util.parse_datetime(due_datetime)
                if parsed_datetime is None:
                    return None
                start = dt_util.as_local(parsed_datetime)
            end = start + datetime.timedelta(hours=1)
            return start, end

        due_date = getattr(due, "date", None)
        if due_date:
            if isinstance(due_date, datetime.date):
                parsed_date = due_date
            else:
                parsed_date = dt_util.parse_date(due_date)
            if parsed_date is None:
                return None
            start = dt_util.start_of_local_day(parsed_date)
            end = start + datetime.timedelta(days=1)
            return start, end

        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime.datetime, end_date: datetime.datetime
    ) -> list[CalendarEvent]:
        """Get all events in a specific time frame."""
        events = []
        for task in self.coordinator.data.tasks:
            if task.project_id != self._project_id:
                continue
            window = self._compute_event_window(task)
            if not window:
                continue
            start, end = window
            if start_date < start < end_date:
                event = CalendarEvent(
                    summary=task.content,
                    start=start,
                    end=end,
                    description=task.description,
                    uid=task.id,
                )
                events.append(event)
        return events

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the entity."""
        next_event = None
        for task in self.coordinator.data.tasks:
            if task.project_id != self._project_id:
                continue
            window = self._compute_event_window(task)
            if not window:
                continue
            start, end = window
            if not next_event or start < next_event.start:
                next_event = CalendarEvent(
                    summary=task.content,
                    start=start,
                    end=end,
                    description=task.description,
                    uid=task.id,
                )
        self._event = next_event
        super()._handle_coordinator_update()
