# Todoist Sync API Migration Task List

## Phase 1 – Foundation
- [x] Establish lightweight Sync client module (`custom_components/todoist/sync_api.py`) with shared HTTP session, auth token handling, and exponential backoff helpers.
- [x] Implement `sync(resource_types, sync_token)` call returning parsed models for tasks, projects, labels.
- [x] Design UUID command helper that accepts a list of command dicts and normalises responses (success map, error list, new sync token).
- [x] Create dataclasses for `SyncTask`, `SyncProject`, and `SyncLabel` with `from_json`/`to_dict` helpers aligned to existing coordinator consumers.
- [x] Mirror Todoist REST error shapes and raise integration-specific exceptions (429 handling, token reset).

## Phase 2 – Coordinator Refactor
- [x] Inject Sync client into `TodoistDataUpdateCoordinator` and migrate `_async_update_data` to call `sync(['items','projects','labels'], sync_token='*')` on startup.
- [x] Persist latest `sync_token` in coordinator state and reuse for incremental polls.
- [x] Replace 15‑minute polling with delta-based refresh: schedule periodic `sync_delta()` and update coordinator data with returned diffs.
- [x] Update cache merge logic to handle `full_sync` responses and item deletions (remove tasks when `is_deleted` or `is_archived`).
- [x] Expose metrics/logs for sync duration, payload counts, and token resets.

## Phase 3 – Mutation Paths
- [x] Swap `async_add_task` to emit Sync command `item_add` and reconcile response via delta sync (without forcing full refresh).
- [x] Update `async_update_task` to send either `item_update` or combined commands when closing/completing.
- [x] Implement `async_close_task` and `async_reopen_task` via `item_complete` / `item_uncomplete` commands, batching with prior updates when necessary.
- [x] Replace REST delete path with `item_delete` command and ensure cache removal happens from command response.
- [x] Adjust `_task_lookup` maintenance to rely on sync deltas; add guard rails if command response omits requested entity.

## Phase 4 – Targeted Refresh & Edge Cases
- [x] Introduce `async_refresh_task` variant that triggers `sync(['items'], resource_ids=[task_id])` or local cache lookup when command echoed in response.
- [x] Handle `sync_token == "RESET"` fallback by forcing `'*'` sync and logging rate-limit guidance.
- [x] Support command retry on temporary failures (HTTP 50x, network) with capped exponential backoff.
- [x] Validate completed task visibility rules (Todoist hides archived/completed) and ensure UI receives expected list.

## Phase 5 – Testing & Tooling
- [ ] Build unit tests for Sync client using captured API fixtures (success, rate-limited, token reset, partial failure).
- [ ] Add integration tests or Home Assistant dev server script to simulate command + delta pipeline.
- [ ] Instrument timing logs to compare REST vs Sync end-to-end latency.
- [x] Instrument timing logs to compare REST vs Sync end-to-end latency.
- [ ] Document manual testing checklist (complete/reopen/add/delete tasks, multi-account scenario placeholder).

## Phase 6 – Documentation & Rollout
- [ ] Update `README.md` and `docs/` to describe Sync requirements and behaviour differences.
- [ ] Provide migration notes for existing users (no action expected, fallback env var/option to revert to REST).
- [ ] Add config option or experimental flag to toggle Sync until GA.
- [ ] Monitor logs post-deployment; prepare rollback plan if Sync endpoints degrade.
