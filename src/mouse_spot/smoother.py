
from __future__ import annotations

import math
import threading

from mouse_spot.config import SmootherConfig

__all__ = ["ExponentialMovingSmoother"]


class ExponentialMovingSmoother:
    """Thread-safe EMA smoother with deadzone suppression.

    Parameters
    ----------
    config:
        A :class:`SmootherConfig` instance that provides *alpha* and
        *deadzone_px* values.  When omitted the defaults are used.
    """

    def __init__(self, config: SmootherConfig | None = None) -> None:
        cfg = config or SmootherConfig()
        self._alpha: float = cfg.alpha
        self._deadzone: int = cfg.deadzone_px
        self._lock: threading.Lock = threading.Lock()

        self._x: float | None = None
        self._y: float | None = None

    def update(self, raw_x: float, raw_y: float) -> tuple[int, int]:
        """Apply EMA smoothing and return integer screen coordinates.

        If the Euclidean distance between the incoming point and the
        current smoothed position is smaller than *deadzone_px*, the
        smoothed position is **not** updated and the previous value is
        returned.

        Parameters
        ----------
        raw_x:
            Raw (unsmoothed) x-coordinate.
        raw_y:
            Raw (unsmoothed) y-coordinate.

        Returns
        -------
        tuple[int, int]
            Smoothed ``(x, y)`` screen coordinates.
        """
        with self._lock:
            if self._x is None or self._y is None:
                self._x = raw_x
                self._y = raw_y
                return (round(self._x), round(self._y))

            dx = raw_x - self._x
            dy = raw_y - self._y
            distance = math.hypot(dx, dy)
            if distance < self._deadzone:
                return (round(self._x), round(self._y))

            self._x = self._alpha * raw_x + (1 - self._alpha) * self._x
            self._y = self._alpha * raw_y + (1 - self._alpha) * self._y

            return (round(self._x), round(self._y))

    def reset(self) -> None:
        """Clear the internal state so the next sample initialises fresh."""
        with self._lock:
            self._x = None
            self._y = None

    @property
    def position(self) -> tuple[int, int] | None:
        """Return the last smoothed position, or ``None`` if unset."""
        with self._lock:
            if self._x is None or self._y is None:
                return None
            return (round(self._x), round(self._y))
