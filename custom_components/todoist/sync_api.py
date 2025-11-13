"""Sync API helper for Todoist."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from aiohttp import ClientError, ClientSession

# See https://developer.todoist.com/api/v1/#tag/Sync
SYNC_BASE_URL = "https://api.todoist.com/api/v1/sync"
_LOGGER = logging.getLogger(__name__)


class TodoistSyncError(Exception):
    """Base exception for Sync API failures."""


class TodoistSyncAuthError(TodoistSyncError):
    """Authentication failure for Sync API calls."""


class TodoistSyncRateLimitError(TodoistSyncError):
    """Raised when the Sync API returns HTTP 429."""

    def __init__(self, retry_after: float | None) -> None:
        super().__init__("Todoist Sync API rate limited")
        self.retry_after = retry_after


class TodoistSyncTokenReset(TodoistSyncError):
    """Raised when the Sync API instructs us to restart with a fresh token."""


class TodoistSyncRequestError(TodoistSyncError):
    """Raised for transport level issues after retries are exhausted."""


@dataclass(slots=True)
class SyncDue:
    """Represents the due struct returned by the Sync API."""

    date: str | None = None
    datetime: str | None = None
    string: str | None = None
    timezone: str | None = None
    is_recurring: bool | None = None

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> SyncDue | None:
        if not data:
            return None
        return cls(
            date=data.get("date"),
            datetime=data.get("datetime"),
            string=data.get("string"),
            timezone=data.get("timezone"),
            is_recurring=data.get("is_recurring"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in (
                ("date", self.date),
                ("datetime", self.datetime),
                ("string", self.string),
                ("timezone", self.timezone),
                ("is_recurring", self.is_recurring),
            )
            if value is not None
        }


@dataclass(slots=True)
class SyncTask:
    """Todoist task payload returned via Sync (items)."""

    id: str
    project_id: str | None
    content: str
    description: str | None
    is_completed: bool
    parent_id: str | None
    label_ids: tuple[str, ...]
    priority: int | None
    order: int | None
    due: SyncDue | None
    is_deleted: bool
    is_archived: bool

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SyncTask:
        due = SyncDue.from_json(data.get("due"))
        label_ids_raw = data.get("label_ids") or []
        label_ids: tuple[str, ...] = tuple(str(value) for value in label_ids_raw if value is not None)
        checked = data.get("checked")
        completed = data.get("completed")
        is_completed = bool(completed) or bool(checked)
        return cls(
            id=str(data["id"]),
            project_id=str(data["project_id"]) if data.get("project_id") is not None else None,
            content=data.get("content") or "",
            description=data.get("description"),
            is_completed=is_completed,
            parent_id=str(data["parent_id"]) if data.get("parent_id") is not None else None,
            label_ids=label_ids,
            priority=int(data["priority"]) if data.get("priority") is not None else None,
            order=int(data["item_order"]) if data.get("item_order") is not None else None,
            due=due,
            is_deleted=bool(data.get("is_deleted")),
            is_archived=bool(data.get("is_archived")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "content": self.content,
            "description": self.description,
            "is_completed": self.is_completed,
            "parent_id": self.parent_id,
            "label_ids": list(self.label_ids),
            "priority": self.priority,
            "order": self.order,
            "due": self.due.to_dict() if self.due else None,
            "is_deleted": self.is_deleted,
            "is_archived": self.is_archived,
        }


@dataclass(slots=True)
class SyncProject:
    """Todoist project payload."""

    id: str
    name: str
    parent_id: str | None
    is_archived: bool
    is_deleted: bool
    color: str | None
    order: int | None

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SyncProject:
        return cls(
            id=str(data["id"]),
            name=data.get("name") or "",
            parent_id=str(data["parent_id"]) if data.get("parent_id") is not None else None,
            is_archived=bool(data.get("is_archived")),
            is_deleted=bool(data.get("is_deleted")),
            color=data.get("color"),
            order=int(data["order"]) if data.get("order") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "is_archived": self.is_archived,
            "is_deleted": self.is_deleted,
            "color": self.color,
            "order": self.order,
        }


@dataclass(slots=True)
class SyncLabel:
    """Todoist label payload."""

    id: str
    name: str
    color: str | None
    is_deleted: bool
    is_favorite: bool
    order: int | None

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SyncLabel:
        return cls(
            id=str(data["id"]),
            name=data.get("name") or "",
            color=data.get("color"),
            is_deleted=bool(data.get("is_deleted")),
            is_favorite=bool(data.get("is_favorite")),
            order=int(data["item_order"]) if data.get("item_order") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "is_deleted": self.is_deleted,
            "is_favorite": self.is_favorite,
            "order": self.order,
        }


@dataclass(slots=True)
class SyncResponse:
    """Structured response from the Sync endpoint."""

    sync_token: str
    full_sync: bool
    tasks: list[SyncTask]
    projects: list[SyncProject]
    labels: list[SyncLabel]
    raw: dict[str, Any]


@dataclass(slots=True)
class CommandError:
    """Represents a failing Todoist command."""

    command_uuid: str
    error: str | None
    error_code: int | None
    details: Any


@dataclass(slots=True)
class CommandResult:
    """Outcome of issuing one or more commands."""

    sync: SyncResponse
    succeeded: list[str]
    failed: list[CommandError]
    temp_id_mapping: dict[str, str]


class TodoistSyncClient:
    """Client for Todoist Sync API minimal surface area."""

    def __init__(
        self,
        session: ClientSession,
        token: str,
        *,
        logger: logging.Logger | None = None,
        max_retries: int = 3,
        request_timeout: int = 15,
    ) -> None:
        self._session = session
        self._token = token
        self._logger = logger or _LOGGER
        self._max_retries = max(1, max_retries)
        self._timeout = request_timeout
        self._lock = asyncio.Lock()

    async def sync(
        self,
        resource_types: Iterable[str],
        *,
        sync_token: str = "*",
    ) -> SyncResponse:
        """Fetch data from the Sync API for the provided resources."""

        payload = {
            "sync_token": sync_token,
            "resource_types": list(resource_types),
        }
        response = await self._request(payload)
        return self._parse_sync_response(response)

    async def execute_commands(
        self,
        commands: Sequence[MutableMapping[str, Any]],
        *,
        sync_token: str = "*",
        resource_types: Iterable[str] | None = None,
    ) -> CommandResult:
        """Submit commands and return their outcome along with updated resources."""

        normalized: list[dict[str, Any]] = []
        for original in commands:
            command = dict(original)
            if "type" not in command:
                raise TodoistSyncError("Todoist command missing type")
            if "uuid" not in command:
                command["uuid"] = uuid.uuid4().hex
            normalized.append(command)

        payload = {
            "sync_token": sync_token,
            "commands": normalized,
            "resource_types": list(resource_types or []),
        }
        response = await self._request(payload)
        sync = self._parse_sync_response(response)
        status = response.get("sync_status") or {}
        succeeded: list[str] = []
        failed: list[CommandError] = []
        for command_uuid, result in status.items():
            if isinstance(result, Mapping):
                failed.append(
                    CommandError(
                        command_uuid=command_uuid,
                        error=result.get("error"),
                        error_code=result.get("error_code"),
                        details=result,
                    )
                )
            elif result == "ok":
                succeeded.append(command_uuid)
            else:
                failed.append(
                    CommandError(
                        command_uuid=command_uuid,
                        error=str(result),
                        error_code=None,
                        details=result,
                    )
                )
        temp_id_mapping = {
            str(temp_id): str(real_id)
            for temp_id, real_id in (response.get("temp_id_mapping") or {}).items()
        }
        return CommandResult(
            sync=sync,
            succeeded=succeeded,
            failed=failed,
            temp_id_mapping=temp_id_mapping,
        )

    async def _request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Issue a POST to the Sync endpoint with retries and backoff."""

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        attempt = 0
        delay = 1.0
        last_error: Exception | None = None
        async with self._lock:
            while attempt < self._max_retries:
                attempt += 1
                try:
                    async with self._session.post(
                        SYNC_BASE_URL,
                        json=payload,
                        headers=headers,
                        timeout=self._timeout,
                    ) as response:
                        if response.status == 401:
                            raise TodoistSyncAuthError("Unauthorized")
                        if response.status == 429:
                            retry_after_header = response.headers.get("Retry-After")
                            retry_after = (
                                float(retry_after_header)
                                if retry_after_header is not None
                                else None
                            )
                            raise TodoistSyncRateLimitError(retry_after)
                        if response.status >= 400:
                            body = await response.text()
                            raise TodoistSyncError(
                                f"Todoist Sync API HTTP {response.status}: {body}"
                            )
                        body = await response.text()
                        if not body:
                            raise TodoistSyncError("Empty response from Sync API")
                        payload_json = json.loads(body)
                        if payload_json.get("sync_token") == "RESET":
                            raise TodoistSyncTokenReset("Sync token reset required")
                        if payload_json.get("error_code"):
                            raise TodoistSyncError(
                                f"Todoist Sync error {payload_json.get('error_code')}: {payload_json.get('error')}"
                            )
                        return payload_json
                except TodoistSyncRateLimitError as err:
                    last_error = err
                    wait_time = err.retry_after or delay
                    self._logger.warning(
                        "Todoist Sync API rate limited, retrying in %.1f seconds", wait_time
                    )
                    await asyncio.sleep(wait_time)
                    delay *= 2
                except (ClientError, asyncio.TimeoutError) as err:
                    last_error = err
                    if attempt >= self._max_retries:
                        break
                    self._logger.warning(
                        "Todoist Sync request failed (%s), retrying in %.1f seconds",
                        err,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                except TodoistSyncError as err:
                    raise err
                except Exception as err:  # pylint: disable=broad-except
                    last_error = err
                    if attempt >= self._max_retries:
                        break
                    self._logger.exception(
                        "Unexpected Todoist Sync error, retrying in %.1f seconds",
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
        raise TodoistSyncRequestError(last_error or Exception("Sync request failed"))

    def _parse_sync_response(self, response: Mapping[str, Any]) -> SyncResponse:
        """Translate the JSON response into typed objects."""

        tasks_raw = response.get("items") or []
        projects_raw = response.get("projects") or []
        labels_raw = response.get("labels") or []
        tasks = [SyncTask.from_json(task) for task in tasks_raw if task]
        projects = [SyncProject.from_json(project) for project in projects_raw if project]
        labels = [SyncLabel.from_json(label) for label in labels_raw if label]
        sync_token = response.get("sync_token")
        if not isinstance(sync_token, str):
            raise TodoistSyncError("Sync response missing sync_token")
        full_sync = bool(response.get("full_sync"))
        return SyncResponse(
            sync_token=sync_token,
            full_sync=full_sync,
            tasks=tasks,
            projects=projects,
            labels=labels,
            raw=dict(response),
        )
