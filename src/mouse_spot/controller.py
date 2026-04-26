
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Protocol

from pynput.mouse import Button  # type: ignore[import-untyped]
from pynput.mouse import Controller as _PynputController

from mouse_spot.config import DisplayServerConfig, GestureConfig

__all__ = ["MouseController", "check_dependencies"]

log = logging.getLogger(__name__)


# ── Dependency Check ──────────────────────────────────────────────────


def check_dependencies() -> None:
    """Verify that required OS tools are installed.

    If missing, exit immediately with clear apt instructions.
    """
    cfg = DisplayServerConfig()
    backend_req = cfg.backend.lower()

    if backend_req == "auto":
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        backend_req = "ydotool" if session == "wayland" else "xdotool"

    if backend_req == "evdev":
        try:
            __import__("evdev")
        except ImportError:
            print(
                "ERROR: evdev library is required for native Wayland support.",
                file=sys.stderr,
            )
            sys.exit(1)

    elif backend_req == "ydotool":
        if shutil.which("ydotool") is None:
            print("ERROR: ydotool is required for Wayland support.", file=sys.stderr)
            print("Please install and enable it:", file=sys.stderr)
            print("  sudo apt install ydotool", file=sys.stderr)
            print("  sudo systemctl enable ydotool", file=sys.stderr)
            sys.exit(1)
    elif backend_req == "xdotool" and shutil.which("xdotool") is None:
            print("ERROR: xdotool is required for X11 support.", file=sys.stderr)
            print("Please install it:", file=sys.stderr)
            print("  sudo apt install xdotool", file=sys.stderr)
            sys.exit(1)


# ── Backend Protocol ──────────────────────────────────────────────────


class BackendProtocol(Protocol):
    """Unified interface for mouse control backends."""

    def move(self, x: int, y: int) -> None: ...
    def click(self, button: str, double: bool = False) -> None: ...
    def scroll(self, dy: int) -> None: ...

    @property
    def screen_size(self) -> tuple[int, int]: ...


# ── Screen Size Helper ────────────────────────────────────────────────


def _get_screen_size() -> tuple[int, int]:
    """Return ``(width, height)`` of the primary monitor.

    We try Xlib first (Linux), then fall back to a sensible default.
    """
    try:  # Linux / X11
        from Xlib import display as _xdisplay  # type: ignore[import-untyped]

        d = _xdisplay.Display()
        screen = d.screen()
        return (screen.width_in_pixels, screen.height_in_pixels)
    except Exception:
        pass

    try:  # macOS / generic Tk fallback
        import tkinter as _tk

        root = _tk.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return (w, h)
    except Exception:
        pass

    return (1920, 1080)  # safe default


# ── Backends ──────────────────────────────────────────────────────────


class PynputBackend:
    """Fallback backend using pynput (restricted to in-app often)."""

    def __init__(self) -> None:
        log.warning("Using pynput backend. System-wide clicks may fail.")
        self._mouse = _PynputController()
        self._screen_w, self._screen_h = _get_screen_size()

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self._screen_w, self._screen_h)

    def move(self, x: int, y: int) -> None:
        self._mouse.position = (x, y)

    def click(self, button: str, double: bool = False) -> None:
        btn = Button.left if button == "left" else Button.right
        self._mouse.click(btn, 2 if double else 1)

    def scroll(self, dy: int) -> None:
        self._mouse.scroll(0, dy)


class XdotoolBackend:
    """X11 backend using xdotool."""

    def __init__(self) -> None:
        log.info("Initialising xdotool backend (X11).")
        self._screen_w, self._screen_h = _get_screen_size()

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self._screen_w, self._screen_h)

    def move(self, x: int, y: int) -> None:
        # Non-blocking for high-frequency moves
        subprocess.Popen(
            ["xdotool", "mousemove", str(x), str(y)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def click(self, button: str, double: bool = False) -> None:
        btn_code = "3" if button == "right" else "1"
        args = ["xdotool", "click"]
        if double:
            args.extend(["--repeat", "2"])
        args.append(btn_code)

        # Blocking for clicks to ensure ordering
        subprocess.run(args, check=False)

    def scroll(self, dy: int) -> None:
        btn_code = "4" if dy > 0 else "5"
        # We might want to scroll multiple times if dy > 1
        args = ["xdotool", "click", "--repeat", str(abs(dy)), btn_code]
        subprocess.run(args, check=False)


class EvdevBackend:
    """Wayland backend using direct /dev/uinput (requires input group)."""

    def __init__(self) -> None:
        log.info("Initialising evdev backend (Wayland default).")
        self._screen_w, self._screen_h = _get_screen_size()

        import evdev

        cap = {
            evdev.ecodes.EV_ABS: [
                (
                    evdev.ecodes.ABS_X,
                    evdev.AbsInfo(
                        value=0, min=0, max=self._screen_w, fuzz=0, flat=0, resolution=0
                    ),
                ),
                (
                    evdev.ecodes.ABS_Y,
                    evdev.AbsInfo(
                        value=0, min=0, max=self._screen_h, fuzz=0, flat=0, resolution=0
                    ),
                ),
            ],
            evdev.ecodes.EV_KEY: [
                evdev.ecodes.BTN_LEFT,
                evdev.ecodes.BTN_RIGHT,
                evdev.ecodes.BTN_MIDDLE
            ],
            evdev.ecodes.EV_REL: [
                evdev.ecodes.REL_WHEEL
            ]
        }
        self._ui = evdev.UInput(
            cap, name="Hand-Mouse Virtual Tablet", version=0x3  # type: ignore[arg-type]
        )
        self._ecodes = evdev.ecodes

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self._screen_w, self._screen_h)

    def move(self, x: int, y: int) -> None:
        self._ui.write(self._ecodes.EV_ABS, self._ecodes.ABS_X, x)
        self._ui.write(self._ecodes.EV_ABS, self._ecodes.ABS_Y, y)
        self._ui.syn()  # type: ignore[no-untyped-call]

    def click(self, button: str, double: bool = False) -> None:
        btn = self._ecodes.BTN_RIGHT if button == "right" else self._ecodes.BTN_LEFT

        def _single() -> None:
            self._ui.write(self._ecodes.EV_KEY, btn, 1)
            self._ui.syn()  # type: ignore[no-untyped-call]
            time.sleep(0.02)
            self._ui.write(self._ecodes.EV_KEY, btn, 0)
            self._ui.syn()  # type: ignore[no-untyped-call]

        _single()
        if double:
            time.sleep(0.05)
            _single()

    def scroll(self, dy: int) -> None:
        # Some wheels expect positive to go up, some down.
        # Usually positive is up/forward
        self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_WHEEL, dy)
        self._ui.syn()  # type: ignore[no-untyped-call]


class YdotoolBackend:
    """Wayland backend using ydotool."""

    def __init__(self) -> None:
        log.info("Initialising ydotool backend (Wayland).")
        self._screen_w, self._screen_h = _get_screen_size()

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self._screen_w, self._screen_h)

    def move(self, x: int, y: int) -> None:
        # Non-blocking
        subprocess.Popen(
            ["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def click(self, button: str, double: bool = False) -> None:
        btn_code = "0x01" if button == "right" else "0x00"

        # ydotool lacks a double-click repeat arg, so we issue two clicks
        subprocess.run(["ydotool", "click", btn_code], check=False)
        if double:
            subprocess.run(["ydotool", "click", btn_code], check=False)

    def scroll(self, dy: int) -> None:
        # ydotool scroll <dy>
        # Check docs to see if we need a positive or negative dy
        subprocess.run(["ydotool", "scroll", "--", "0", str(dy)], check=False)


# ── Factory ──────────────────────────────────────────────────────────


def _create_backend(config: DisplayServerConfig | None = None) -> BackendProtocol:
    """Instantiate the appropriate display server backend."""
    cfg = config or DisplayServerConfig()
    backend_req = cfg.backend.lower()

    if backend_req == "auto":
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session == "wayland":
            # Prefer evdev if writable, else ydotool
            backend_req = "evdev" if os.access("/dev/uinput", os.W_OK) else "ydotool"
        elif session in ("x11", "tty"): # fallback to x11
            backend_req = "xdotool"
        else:
            backend_req = "xdotool"

    if backend_req == "evdev":
        try:
            __import__("evdev")
            return EvdevBackend()
        except ImportError:
            log.warning("evdev requested but not installed. Falling back to pynput.")
            return PynputBackend()

    if backend_req == "ydotool":
        if shutil.which("ydotool"):
            return YdotoolBackend()
        log.warning("ydotool requested but not installed. Falling back to pynput.")
        return PynputBackend()

    if backend_req == "xdotool":
        if shutil.which("xdotool"):
            return XdotoolBackend()
        log.warning("xdotool requested but not installed. Falling back to pynput.")
        return PynputBackend()

    return PynputBackend()


# ── High Level Controller ─────────────────────────────────────────────


class MouseController:
    """High-level mouse controller backed by system tools.

    Parameters
    ----------
    config:
        A :class:`GestureConfig` providing ``click_cooldown_ms`` and
        ``scroll_speed``.
    backend_cfg:
        A :class:`DisplayServerConfig` to override default auto-detection.
    """

    def __init__(
        self,
        config: GestureConfig | None = None,
        backend_cfg: DisplayServerConfig | None = None,
    ) -> None:
        cfg = config or GestureConfig()
        self._backend = _create_backend(backend_cfg)
        self._screen_w, self._screen_h = self._backend.screen_size
        self._cooldown_s: float = cfg.click_cooldown_ms / 1000.0
        self._scroll_speed: int = cfg.scroll_speed

        # Per-action cooldown timestamps (monotonic).
        self._last_action: dict[str, float] = {}

    # ── Public API ────────────────────────────────────────────────────

    def move(self, x: int, y: int) -> None:
        """Move the cursor to *(x, y)*, clamped to screen bounds."""
        cx = max(0, min(x, self._screen_w - 1))
        cy = max(0, min(y, self._screen_h - 1))
        self._backend.move(cx, cy)

    def click(self, button: str = "left", double: bool = False) -> None:
        """Perform a click if the per-button cooldown has elapsed.

        Parameters
        ----------
        button:
            ``"left"`` or ``"right"``.
        double:
            True forces a double click event (ignores normal cooldown
            rules but has its own cooldown key).
        """
        now = time.monotonic()
        btn_key = f"{button}_double" if double else button
        last = self._last_action.get(btn_key, 0.0)

        if now - last < self._cooldown_s:
            return  # cooldown not yet expired

        self._backend.click(button, double=double)
        self._last_action[btn_key] = now

    def scroll(self, dy: int) -> None:
        """Scroll vertically by *dy* steps (positive = up)."""
        now = time.monotonic()
        last = self._last_action.get("scroll", 0.0)

        # Max 10 scroll events per second avoiding hyperspeed
        if now - last < 0.1:
            return

        self._backend.scroll(dy * self._scroll_speed)
        self._last_action["scroll"] = now

    # ── Introspection ─────────────────────────────────────────────────

    @property
    def screen_size(self) -> tuple[int, int]:
        """Return ``(width, height)`` of the detected screen."""
        return (self._screen_w, self._screen_h)

