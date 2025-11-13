# Todoist Sync Integration for Home Assistant

This is a custom component for Home Assistant that integrates with [Todoist](https://todoist.com). It replaces the legacy REST-based integration with a Sync API implementation that keeps entities up-to-date with deltas, supports command batching, and exposes detailed timing telemetry.

If you're building a full chore-tracking experience, this integration works out-of-the-box with the [Todoist Choreboard add-on](https://github.com/Creedzy/Todoist-ha-chore-ui). Pairing them lets you surface Todoist tasks in the companion UI while relying on this integration for data access and automation hooks inside Home Assistant.

## Installation

### HACS

The easiest way to install this integration is with [HACS](https://hacs.xyz/).

1.  Open HACS.
2.  Go to "Integrations".
3.  Click the three dots in the top right corner and select "Custom repositories".
4.  Enter `https://github.com/Creedzy/todoist-ha-integration.git` as the repository and `integration` as the category.
5.  Click "Add".
6.  The "Todoist Sync" integration will now be available to install.

### Manual Installation

1.  Copy the `custom_components/todoist_sync` directory to your Home Assistant `custom_components` directory.
2.  Restart Home Assistant.

## Migration from Core Integration

If you are using the core Todoist integration (`todoist` domain), you will need to disable it before enabling this custom component. Home Assistant treats `todoist_sync` as a separate domain, so you can migrate without conflicting entities.

1.  Go to "Configuration" -> "Integrations".
2.  Find the "Todoist" integration and click the three dots.
3.  Select "Disable".
4.  Restart Home Assistant.
5.  You can now enable the custom component by following the installation instructions above.

## Configuration

Configuration is done through the Home Assistant UI.

1.  Go to "Configuration" -> "Integrations".
2.  Click the "+" button and search for "Todoist Sync".
3.  Enter your Todoist API token.

### Options

After the integration has been configured, you can adjust the following options:

*   **Include archived projects**: If enabled, projects that have been archived in Todoist will be included in Home Assistant.
*   **Enable advanced mode**: If enabled, additional attributes will be available on the entities.

## Services

This integration provides the following services:

*   `todoist_sync.new_task`: Create a new task and update the coordinator cache via Sync delta responses.
*   `todoist_sync.update_task`: Update an existing task, close/reopen it, and refresh the coordinator from the command delta.
*   `todoist_sync.get_task`: Emit an event with a single task payload.
*   `todoist_sync.get_all_tasks`: Emit an event containing the full task payload list held by the coordinator.

## Automation Examples

```yaml
- alias: "Add a new task"
  trigger:
    - platform: state
      entity_id: "input_boolean.add_task"
      to: "on"
  action:
  - service: "todoist_sync.new_task"
      data:
        content: "My new task"
        project: "Inbox"

- alias: "Update a task"
  trigger:
    - platform: state
      entity_id: "input_boolean.update_task"
      to: "on"
  action:
  - service: "todoist_sync.update_task"
      data:
        task_id: "12345678"
        content: "My updated task"
```
