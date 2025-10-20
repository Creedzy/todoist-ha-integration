"""Types for the Todoist component."""
from __future__ import annotations

from dataclasses import dataclass

from todoist_api_python.models import Label, Project, Task


@dataclass
class TodoistData:
    """Data for the Todoist integration."""

    tasks: list[Task]
    projects: list[Project]
    labels: list[Label]
