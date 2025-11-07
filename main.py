"""Entry point for the Home Assistant system tray widget."""
from __future__ import annotations

import signal
import sys

from PyQt6 import QtWidgets

from hass_widget.config import load_config
from hass_widget.tray import TrayIcon


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    config = load_config()
    tray = TrayIcon(config, app)
    tray.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
