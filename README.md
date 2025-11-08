# Home Assistant Tray Widget

A simple PyQt-based system tray widget for Linux (tested with Hyprland-compatible compositors) that lets you toggle Home Assistant entities directly from the tray menu. The widget also provides a configuration dialog for updating the Home Assistant connection details and choosing which entities appear in the menu.

## Features

- Runs as a Windows/Linux (hyprland/gnome/xfce/kde/lxde and so on) system tray (StatusNotifier/AppIndicator) application
- Configurable Home Assistant instance URL and long-lived access token
- Pick which entities show up in the tray menu via the settings dialog
- Quickly toggle the configured entities by selecting them from the tray menu

## Roadmap
- Display notifications from your Home Assistant instance
- Notifications with image support (e.g. motion detect on camera displays notification with a camera screenshot)
- Notifications with actions (e.g. open garage door/close garage door)
- Work as a home assistant agent so that you can perform actions for this device from your home assistant device, if enabled, of course

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

## Home Assistant Setup

1. Create a [long-lived access token](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token) in your Home Assistant profile.
2. Launch the tray widget and open **Settings…** from the tray menu.
3. Enter your Home Assistant instance URL and token, then click **Refresh from Home Assistant** to load entities.
4. Select the desired entities and use the **Add →** button to include them in the tray.
5. Save the settings. The tray menu will update immediately.

Selecting an entity from the tray will call the Home Assistant `toggle` service for that entity.
