
from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path
from typing import Any

from PIL import Image
from pystray import Icon, Menu, MenuItem  # type: ignore[import-untyped]

from mouse_spot.config import CameraConfig, GestureConfig, SmootherConfig
from mouse_spot.controller import check_dependencies
from mouse_spot.overlay import OverlayWindow
from mouse_spot.tracker import CameraTracker

__all__ = ["main"]

log = logging.getLogger("mouse_spot")

_LOG_FILE = _LOG_DIR / "app.log"


def _setup_logging() -> None:
    """Configure root logger -> stdout + file."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


def _load_icon() -> Image.Image:
    """Load the tray icon from ``assets/icon.png``, or generate a
    simple fallback if the file is missing / empty.
    """
    icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
    try:
        if icon_path.exists() and icon_path.stat().st_size > 0:
            return Image.open(icon_path)
    except Exception:
        pass

    # Generate a tiny coloured square as fallback.
    img = Image.new("RGB", (64, 64), color=(0, 170, 255))
    return img


class _App:
    """Internal application state wired to the tray icon."""

    def __init__(self) -> None:
        self._overlay = OverlayWindow()
        self._tracker = CameraTracker(
            camera_cfg=CameraConfig(),
            gesture_cfg=GestureConfig(),
            smoother_cfg=SmootherConfig(),
            overlay=self._overlay,
        )
        self._icon: Icon | None = None

    def _on_toggle_pause(self, icon: Icon, item: MenuItem) -> None:
        if self._tracker.is_paused:
            self._tracker.resume()
            log.info("Resumed via tray menu.")
        else:
            self._tracker.pause()
            log.info("Paused via tray menu.")
        icon.update_menu()

    def _pause_text(self, item: MenuItem) -> str:
        return "Resume" if self._tracker.is_paused else "Pause"

    def _on_toggle_overlay(self, icon: Icon, item: MenuItem) -> None:
        self._overlay.toggle()

    def _overlay_text(self, item: MenuItem) -> str:
        return "Hide Monitor" if self._overlay.is_visible else "Show Monitor"

    def _on_quit(self, icon: Icon, item: MenuItem) -> None:
        log.info("Quit requested.")
        self._shutdown()

    def _shutdown(self) -> None:
        self._tracker.stop()
        self._overlay.stop()
        if self._icon is not None:
            self._icon.stop()

    def run(self) -> None:
        """Start tracker + overlay + tray icon (blocks on the tray event loop)."""
        self._overlay.start()
        self._tracker.start()

        menu = Menu(
            MenuItem("Hand Mouse - Running", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(self._pause_text, self._on_toggle_pause),
            MenuItem(self._overlay_text, self._on_toggle_overlay),
            MenuItem("Quit", self._on_quit),
        )
        self._icon = Icon("mousespot", _load_icon(), "Hand Mouse", menu)

        def _handle_signal(signum: int, frame: Any) -> None:
            log.info("Signal %s received, shutting down...", signum)
            self._shutdown()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        log.info("Hand Mouse started.  Tray icon active.")
        self._icon.run()


def main() -> None:
    """Launch Hand Mouse."""
    _setup_logging()
    check_dependencies()
    app = _App()
    app.run()


if __name__ == "__main__":
    main()
