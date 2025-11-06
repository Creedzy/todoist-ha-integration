# Todoist Integration for Home Assistant

This is a custom component for Home Assistant that integrates with [Todoist](https://todoist.com). It is a modernized version of the core Todoist integration, with a number of improvements and new features.

## Installation

### HACS

The easiest way to install this integration is with [HACS](https://hacs.xyz/).

1.  Open HACS.
2.  Go to "Integrations".
3.  Click the three dots in the top right corner and select "Custom repositories".
4.  Enter `https://github.com/Creedzy/todoist-ha-integration.git` as the repository and `integration` as the category.
5.  Click "Add".
6.  The "Todoist" integration will now be available to install.

### Manual Installation

1.  Copy the `custom_components/todoist` directory to your Home Assistant `custom_components` directory.
2.  Restart Home Assistant.

## Migration from Core Integration

If you are using the core Todoist integration, you will need to disable it before enabling this custom component.

1.  Go to "Configuration" -> "Integrations".
2.  Find the "Todoist" integration and click the three dots.
3.  Select "Disable".
4.  Restart Home Assistant.
5.  You can now enable the custom component by following the installation instructions above.

## Configuration

Configuration is done through the Home Assistant UI.

1.  Go to "Configuration" -> "Integrations".
2.  Click the "+" button and search for "Todoist".
3.  Enter your Todoist API token.

### Options

After the integration has been configured, you can adjust the following options:

*   **Include archived projects**: If enabled, projects that have been archived in Todoist will be included in Home Assistant.
*   **Enable advanced mode**: If enabled, additional attributes will be available on the entities.

## Services

This integration provides the following services:

*   `todoist.new_task`: Create a new task.
*   `todoist.update_task`: Update an existing task.
*   `todoist.get_task`: Get information about a task.

## Automation Examples

```yaml
- alias: "Add a new task"
  trigger:
    - platform: state
      entity_id: "input_boolean.add_task"
      to: "on"
  action:
    - service: "todoist.new_task"
      data:
        content: "My new task"
        project: "Inbox"

- alias: "Update a task"
  trigger:
    - platform: state
      entity_id: "input_boolean.update_task"
      to: "on"
  action:
    - service: "todoist.update_task"
      data:
        task_id: "12345678"
        content: "My updated task"
```
