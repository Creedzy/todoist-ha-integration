"""Sensor platform for Todoist."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TodoistDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: TodoistDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    projects = coordinator.data.projects
    async_add_entities(
        TodoistProjectSensor(coordinator, project.id, project.name)
        for project in projects
    )


class TodoistProjectSensor(
    CoordinatorEntity[TodoistDataUpdateCoordinator], SensorEntity
):
    """A sensor for a Todoist project."""

    def __init__(
        self,
        coordinator: TodoistDataUpdateCoordinator,
        project_id: str,
        project_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._project_id = project_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}-{project_id}-sensor"
        self._attr_name = project_name
        self._update_attrs()

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return len(self._attr_extra_state_attributes["tasks"])

    def _update_attrs(self) -> None:
        """Update the sensor's attributes."""
        tasks: list[dict] = []
        labels: list[dict[str, str]] = []
        label_lookup: dict[str, str] = {}
        project_payload: dict[str, str] | None = None

        if self.coordinator.data:
            tasks = [
                task.to_dict()
                for task in self.coordinator.data.tasks
                if task.project_id == self._project_id
            ]

            labels = [
                {"id": str(label.id), "name": label.name}
                for label in self.coordinator.data.labels
                if getattr(label, "name", None) is not None
            ]
            label_lookup = {item["id"]: item["name"] for item in labels}

            project = next(
                (
                    project
                    for project in self.coordinator.data.projects
                    if project.id == self._project_id
                ),
                None,
            )
            if project is not None:
                project_payload = (
                    project.to_dict()
                    if hasattr(project, "to_dict")
                    else {"id": project.id, "name": project.name}
                )

        extra_attrs: dict[str, object] = {"tasks": tasks, "project_id": self._project_id}

        if project_payload is not None:
            extra_attrs["project"] = project_payload
        if labels:
            extra_attrs["label_options"] = labels
        if label_lookup:
            extra_attrs["labels_by_id"] = label_lookup

        self._attr_extra_state_attributes = extra_attrs

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attrs()
        super()._handle_coordinator_update()
