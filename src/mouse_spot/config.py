
from __future__ import annotations

import os
from dataclasses import dataclass, field

__all__ = ["CameraConfig", "DisplayServerConfig", "GestureConfig", "SmootherConfig"]


def _env_int(key: str, default: int) -> int:
    """Read an integer from the environment, falling back to *default*."""
    return int(os.environ.get(key, str(default)))


def _env_float(key: str, default: float) -> float:
    """Read a float from the environment, falling back to *default*."""
    return float(os.environ.get(key, str(default)))


def _env_str(key: str, default: str) -> str:
    """Read a string from the environment, falling back to *default*."""
    return os.environ.get(key, default)


@dataclass(frozen=True, slots=True)
class CameraConfig:
    """Webcam capture parameters."""

    device_index: int = field(default_factory=lambda: _env_int("HM_CAMERA_INDEX", 0))
    width: int = field(default_factory=lambda: _env_int("HM_CAMERA_WIDTH", 640))
    height: int = field(default_factory=lambda: _env_int("HM_CAMERA_HEIGHT", 480))
    fps: int = field(default_factory=lambda: _env_int("HM_CAMERA_FPS", 30))


@dataclass(frozen=True, slots=True)
class DisplayServerConfig:
    """OS-level input backend configuration."""

    backend: str = field(
        default_factory=lambda: _env_str("HAND_MOUSE_BACKEND", "auto")
    )


@dataclass(frozen=True, slots=True)
class GestureConfig:
    """Gesture-detection thresholds and timing."""

    pinch_threshold: float = field(
        default_factory=lambda: _env_float("HM_PINCH_THRESHOLD", 0.05)
    )
    click_cooldown_ms: int = field(
        default_factory=lambda: _env_int("HM_CLICK_COOLDOWN_MS", 600)
    )
    scroll_speed: int = field(
        default_factory=lambda: _env_int("HM_SCROLL_SPEED", 1)
    )
    double_click_window_ms: int = field(
        default_factory=lambda: _env_int("HM_DOUBLE_CLICK_WINDOW_MS", 400)
    )
    frame_margin: int = field(
        default_factory=lambda: _env_int("HM_FRAME_MARGIN", 150)
    )


@dataclass(frozen=True, slots=True)
class SmootherConfig:
    """Exponential-moving-average (EMA) smoothing parameters."""

    alpha: float = field(
        default_factory=lambda: _env_float("HM_SMOOTHER_ALPHA", 0.2)
    )
    deadzone_px: int = field(
        default_factory=lambda: _env_int("HM_DEADZONE_PX", 4)
    )
