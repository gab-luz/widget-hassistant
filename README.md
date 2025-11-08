# Home Assistant Tray Widget

A PyQt-based system tray widget for Linux (tested with Hyprland-compatible compositors) that lets you interact with your Home Assistant instance from the desktop. The widget provides quick entity toggles, rich notifications, and a configuration dialog for tailoring the experience to your environment.

## Features

- Runs as a Linux system tray (StatusNotifier/AppIndicator) application with light/dark/auto tray icon themes
- Configurable Home Assistant instance URL, access token, and proxy settings
- Pick which entities show up in the tray menu, complete with Home Assistant-provided icons or cached fallbacks
- Quickly toggle the configured entities by selecting them from the tray menu
- Global entity cache that refreshes on a configurable cadence and powers both the tray menu and the entity panel without repeatedly downloading data
- Left-click the tray icon to open an always-on-top floating entities panel (with fade-in/out animations) that lists every entity, includes a search bar, displays icons, and lets you control entities directly
- Receive Home Assistant admin notifications on the desktop with a one-click test notification option
- Optional Home Assistant agent mode that exposes device telemetry (disk, memory, GPU, uptime, etc.) back to Home Assistant for use in automations

## Requirements

- Python 3.10+
- A desktop environment/compositor that supports the system tray (tested on Hyprland via `waybar`/`trayer`)
- Dependencies listed in `requirements.txt`

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

The application stores its configuration in `${XDG_CONFIG_HOME:-~/.config}/hassistant-widget/config.json`.

## Usage Highlights

### Managing Entities and Appearance

Open **Settings…** from the tray menu to configure the widget:

1. Enter your Home Assistant instance URL and long-lived access token.
2. Optionally provide HTTP/HTTPS proxy addresses.
3. Choose your preferred tray icon theme (auto/light/dark).
4. Use **Refresh from Home Assistant** to load entities; search within the available list to find what you need.
5. Select entities to include in the tray menu; they will display with their friendly name, entity ID, and icon.
6. Adjust the panel refresh interval (in minutes) to control how often the full entity cache updates.

### Entity Panel

- Left-click the tray icon to open the entities panel.
- The panel shows all Home Assistant entities with icons, friendly names, entity IDs, and search filtering.
- The window stays on top, requests floating behavior on Hyprland, and supports fade-in/fade-out animations.
- A close button quickly hides the panel; the cached data avoids redundant API calls between refresh intervals.

### Notifications

- Enable **Receive admin notifications** in settings to mirror Home Assistant’s admin notifications on the desktop.
- Use **Send test notification** to verify connectivity; the widget will trigger a Home Assistant notification and display it locally.

### Home Assistant Agent Mode

- Enable **Use this widget as a Home Assistant agent** to let the widget expose local device telemetry back to Home Assistant.
- Provide a friendly name for the device so it’s easy to reference in automations.
- On the **Agent data** tab, select which metrics (disk usage, memory usage, GPU load, uptime, etc.) should be published.

## Home Assistant Setup

1. Create a [long-lived access token](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token) in your Home Assistant profile.
2. Launch the tray widget and open **Settings…** from the tray menu.
3. Enter your Home Assistant instance URL and token, then click **Refresh from Home Assistant** to load entities.
4. Select the desired entities and use the **Add →** button to include them in the tray.
5. Save the settings. The tray menu and entities panel will update immediately.

Selecting an entity from the tray or panel will call the corresponding Home Assistant service (e.g. `toggle` for switches/lights).
