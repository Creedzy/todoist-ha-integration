"""Types for the Todoist Sync component."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TodoistData:
    """Data snapshot for the Todoist Sync integration."""

    tasks: list[Any]
    projects: list[Any]
    labels: list[Any]
    last_update: float
