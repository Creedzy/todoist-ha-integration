# Todoist Sync Integration Modernization Plan

## Validation Summary
- Specification aligns with Home Assistant architectural guidelines and leverages a dedicated `TodoistSyncClient` for the Sync v1 endpoint, removing the dependency on `todoist-api-python`.
- Coordinator-centric design already centralizes task, project, and label retrieval with resilient delta handling and timing instrumentation.
- Expanded service layer (e.g., `todoist_sync.update_task`, `todoist_sync.get_task`) is implemented via Home Assistant service schemas, enabling fine-grained task management and event-based responses.
- HACS packaging requirements (manifest versioning, `hacs.json`, semantic releases) are compatible with the repository layout and ensure distributable builds.
- Automation examples rely on newly exposed task attributes; the enriched data model supports these use cases without breaking existing entities when defaults are preserved.

## Phase 1 – Environment & Baseline
- Maintain a fork of the core `homeassistant/components/todoist` integration in `custom_components/todoist_sync` for development parity while preserving an independent domain.
- Add `.devcontainer` configuration (optional but recommended) and document restart workflow for local Home Assistant instances.
- Keep `manifest.json` aligned with Sync-only requirements (no external SDK), explicit `version`, and `iot_class: cloud_polling`.
- Maintain foundational constants (`DOMAIN`, service names, option keys) in `const.py` to support new modules.

## Phase 2 – API Client Integration
- Continue evolving the `TodoistSyncClient` with structured error handling for authentication, throttling, token resets, and retryable failures surfaced via custom exceptions.
- Expand dataclass parsing helpers (`SyncTask`, `SyncProject`, `SyncLabel`) to cover additional fields surfaced by Sync deltas while keeping coordinator consumers stable.

## Phase 3 – DataUpdateCoordinator Core
- Maintain the `TodoistDataUpdateCoordinator` delta workflow with 60-second polling, incremental sync tokens, and precise cache merge logic.
- Track task, project, and label payloads keyed by ID; continue exposing metadata like timing logs and last update timestamps for diagnostics.
- Extend helper methods on the coordinator for CRUD operations (create/update/close task) that reconcile using command deltas without forcing full refreshes.

## Phase 4 – Entity Refactors
- Keep `todo.py`, `calendar.py`, and `sensor.py` aligned with the coordinator payload, ensuring localised due date/datetime handling and consistent attribute exposure.
- Evaluate adding diagnostics support to export cached Sync payloads for troubleshooting.

## Phase 5 – Services & Schema Enhancements
- Maintain `services.yaml` coverage for optional task fields (description, due datetime, labels, priority, assignment).
- Enhance service handlers in `services.py` with additional validation or response metadata as new coordinator features are introduced.
- Ensure existing service signatures remain functional; default to minimal updates unless advanced parameters supplied.

## Phase 6 – Options Flow & Configuration
- Extend `config_flow.py` as needed to capture additional options (project/label filters, response verbosity) while keeping advanced mode and include archived toggles.
- Persist options, wire them into coordinator initialization, and expose reconfigure flow for adjustments.
- Keep translations in `strings.json` synchronised with any new options or validation errors.

## Phase 7 – Testing & QA
- Add unit tests covering coordinator fetch logic, service handlers, and entity attribute serialization using captured Sync payload fixtures.
- Mock Sync API responses for recurring tasks, sections, assignments, and error cases (token reset, rate limiting, network retries).
- Validate that default configuration reproduces existing behavior; advanced mode tests should confirm enriched payload availability and service flexibility.

## Phase 8 – Documentation & Distribution
- Keep `README.md` and companion docs updated with Sync behaviour, setup, options, services, and automation examples.
- Maintain `hacs.json`, outline release workflow, and follow semantic versioning for GitHub releases.
- Provide migration notes for users upgrading from the core integration, including instructions for removing or disabling the stock component before enabling `todoist_sync`.

## Phase 9 – Post-Implementation Checklist
- Manual QA in a test Home Assistant instance verifying entity updates, calendar accuracy, and service responses.
- Monitor Todoist API quota usage; adjust coordinator interval or implement backoff if necessary.
- Gather user feedback via issues/discussions; triage for upstream PR preparation once stabilized.
