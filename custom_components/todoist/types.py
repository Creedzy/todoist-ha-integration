"""Types for the Todoist component."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TodoistData:
    """Data for the Todoist integration."""

    tasks: list[Any]
    projects: list[Any]
    labels: list[Any]
    last_update: float
