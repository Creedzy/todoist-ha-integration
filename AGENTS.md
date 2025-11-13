# Todoist Integration Enhancement Plan

## Objective
Expand the Home Assistant Todoist Sync integration so automations and blueprints can interact with richer task metadata, leverage newer API options, and optionally return complete task payloads.

## Key Changes Needed
1. **API surface enrichment**
	- Continue iterating on the custom Sync client in `custom_components/todoist_sync/sync_api.py` to expose additional fields supplied by delta payloads (labels, assignee, editor, section, recurring schedule, etc.).
	- Normalize field names in `types.py` (or equivalent data classes) to match the Sync payload for round-trip serialization.
2. **Coordinator & data model updates**
	- Extend the `TodoistDataUpdateCoordinator` to request expanded task objects (pass `include_history`, `lang`, and other supported query params when beneficial).
	- Cache full task objects in coordinator data and adjust the entity/trigger layers to consume the enriched payload.
3. **Service layer improvements**
	- Update `services.yaml` and handlers in `todo.py` to accept and validate new optional parameters (priority, labels, section, due_datetime vs. due_date, reminders, comments).
	- Ensure service calls continue returning the full task dictionary via Sync delta events when configured.
4. **Options & config flow**
	- Add UI options for users to opt-in to advanced fields (filtering by project/label, include archived, response shape).
	- Persist options in `config_flow.py` and feed them into coordinator refresh logic.
5. **Backward compatibility & testing**
	- Maintain current defaults so existing setups work unchanged (keep minimal field set unless advanced mode enabled).
	- Expand unit tests for coordinator/service functions to cover new paths and schema validation.

## Implementation Notes
- Review the upstream core integration (`homeassistant/components/todoist`) for recent patterns, especially around config entries, diagnostics, and device info registration. Mirror core style to ease future upstreaming.
- Reuse SDK models directly where possible instead of duplicating schemas; add thin translation layers only when Home Assistant conventions require it.
- Where Home Assistant core cannot yet accept richer structures (e.g., `TodoItem` entity attributes), provide fallbacks while storing raw payloads in coordinator data to expose via sensors, events, or diagnostics.
- Update `manifest.json` if additional dependencies or minimum versions of `todoist_api_python` are required.
- Include docstrings or inline docs highlighting any behavior that diverges from the upstream core integration.

## Deployment Strategy
- Distribute as a `custom_components/todoist_sync` integration so it can live alongside the core `todoist` domain during migration. Provide instructions for disabling the stock integration before enabling the custom one.
- Prepare the repo structure and metadata (`hacs.json`, release workflow) for a potential future HACS submission, keeping codebase close to Home Assistant standards.
- Document migration steps for future PR back to Home Assistant core (changelog, breaking-change analysis, config upgrade flow).

## References
- Home Assistant architecture guidelines: https://developers.home-assistant.io/docs/architecture_index/
- Core Todoist integration: https://github.com/home-assistant/core/tree/2025.10.3/homeassistant/components/todoist
- Todoist Python SDK async docs: https://doist.github.io/todoist-api-python/api_async/
- Todoist SDK models reference: https://doist.github.io/todoist-api-python/models/
