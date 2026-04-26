
from __future__ import annotations

import enum
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass

from mouse_spot.config import GestureConfig

__all__ = ["Gesture", "GestureClassifier", "LandmarkPoint"]


# ── Data types ────────────────────────────────────────────────────────


class Gesture(enum.Enum):
    """Recognised hand gestures."""

    MOVE = "move"
    LEFT_CLICK = "left_click"
    RIGHT_CLICK = "right_click"
    DOUBLE_CLICK = "double_click"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    FREEZE = "freeze"


@dataclass(frozen=True, slots=True)
class LandmarkPoint:
    """Minimal (x, y, z) landmark used by the classifier.

    Consumers should convert MediaPipe ``NormalizedLandmark`` instances
    into this type before calling :meth:`GestureClassifier.classify`.
    """

    x: float
    y: float
    z: float = 0.0


# ── Landmark indices (MediaPipe convention) ───────────────────────────

_WRIST = 0
_THUMB_TIP = 4
_INDEX_MCP = 5
_INDEX_PIP = 6
_INDEX_TIP = 8
_MIDDLE_MCP = 9
_MIDDLE_PIP = 10
_MIDDLE_TIP = 12
_RING_PIP = 14
_RING_TIP = 16
_PINKY_PIP = 18
_PINKY_TIP = 20


# ── Pure helpers ──────────────────────────────────────────────────────


def _euclidean(a: LandmarkPoint, b: LandmarkPoint) -> float:
    """Euclidean distance between two landmarks (2-D, x/y only)."""
    return math.hypot(a.x - b.x, a.y - b.y)


def _hand_scale(landmarks: Sequence[LandmarkPoint]) -> float:
    """Reference length: wrist → middle-finger MCP.

    All distance comparisons are normalised by this value so that
    thresholds work regardless of the hand's distance from the camera.
    Returns a small epsilon if the distance is zero to avoid division
    errors.
    """
    d = _euclidean(landmarks[_WRIST], landmarks[_MIDDLE_MCP])
    return d if d > 1e-9 else 1e-9


def _normalised_distance(
    landmarks: Sequence[LandmarkPoint],
    idx_a: int,
    idx_b: int,
) -> float:
    """Euclidean distance between two landmarks, normalised to hand scale."""
    return _euclidean(landmarks[idx_a], landmarks[idx_b]) / _hand_scale(landmarks)


def _is_finger_extended(
    landmarks: Sequence[LandmarkPoint],
    tip_idx: int,
    pip_idx: int,
) -> bool:
    """True when a finger tip is *above* (lower y) its PIP joint.

    In MediaPipe's coordinate system y increases downward, so an
    extended finger has ``tip.y < pip.y``.
    """
    return landmarks[tip_idx].y < landmarks[pip_idx].y


# ── Classifier ────────────────────────────────────────────────────────


class GestureClassifier:
    """Stateless gesture classifier.

    Parameters
    ----------
    config:
        A :class:`GestureConfig` providing ``pinch_threshold`` and
        related tuning values.
    """

    def __init__(self, config: GestureConfig | None = None) -> None:
        cfg = config or GestureConfig()
        self._pinch_threshold: float = cfg.pinch_threshold
        self._double_click_window_s: float = cfg.double_click_window_ms / 1000.0
        self._last_left_click_time: float = 0.0

    # ── public API ────────────────────────────────────────────────────

    def classify(
        self,
        landmarks: Sequence[LandmarkPoint],
        confidence: float,
        prev_index_y: float | None = None,
    ) -> Gesture:
        """Return the :class:`Gesture` for the given hand landmarks.

        Parameters
        ----------
        landmarks:
            21 MediaPipe hand landmarks converted to
            :class:`LandmarkPoint`.
        confidence:
            Detection confidence in ``[0, 1]``.
        prev_index_y:
            The ``y`` coordinate of the index-finger tip in the
            previous frame, used for scroll direction detection.
            ``None`` on the first frame.

        Returns
        -------
        Gesture
        """
        if confidence < 0.8:
            return Gesture.FREEZE

        left_pinch = _normalised_distance(
            landmarks, _THUMB_TIP, _INDEX_TIP
        )
        if left_pinch < self._pinch_threshold:
            now = time.monotonic()
            if now - self._last_left_click_time < self._double_click_window_s:
                self._last_left_click_time = 0.0
                return Gesture.DOUBLE_CLICK

            self._last_left_click_time = now
            return Gesture.LEFT_CLICK

        right_pinch = _normalised_distance(
            landmarks, _THUMB_TIP, _MIDDLE_TIP
        )
        if right_pinch < self._pinch_threshold:
            return Gesture.RIGHT_CLICK

        index_ext = _is_finger_extended(landmarks, _INDEX_TIP, _INDEX_PIP)
        middle_ext = _is_finger_extended(landmarks, _MIDDLE_TIP, _MIDDLE_PIP)
        ring_ext = _is_finger_extended(landmarks, _RING_TIP, _RING_PIP)
        pinky_ext = _is_finger_extended(landmarks, _PINKY_TIP, _PINKY_PIP)

        if index_ext and middle_ext and not ring_ext and not pinky_ext:
            if prev_index_y is not None:
                dy = landmarks[_INDEX_TIP].y - prev_index_y
                if dy < 0:
                    return Gesture.SCROLL_UP
                if dy > 0:
                    return Gesture.SCROLL_DOWN
            return Gesture.MOVE

        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            return Gesture.MOVE

        if not index_ext and not middle_ext and not ring_ext and not pinky_ext:
            return Gesture.FREEZE

        return Gesture.FREEZE
