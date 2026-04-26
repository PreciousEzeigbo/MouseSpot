
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Protocol

import cv2
import numpy as np

try:
    from mediapipe.python.solutions import (  # type: ignore[import-untyped]
        drawing_utils as mp_drawing,
    )
    from mediapipe.python.solutions import (
        hands as mp_hands_module,
    )
except ImportError as exc:
    raise RuntimeError(
        "mediapipe is not installed correctly - run: uv sync"
    ) from exc

from mouse_spot.config import CameraConfig, GestureConfig, SmootherConfig
from mouse_spot.controller import MouseController
from mouse_spot.gesture import Gesture, GestureClassifier, LandmarkPoint
from mouse_spot.smoother import ExponentialMovingSmoother

if TYPE_CHECKING:
    from mouse_spot.overlay import OverlayWindow

__all__ = ["CameraTracker", "FrameCallback"]

log = logging.getLogger(__name__)

class FrameCallback(Protocol):
    """Signature for the optional per-frame callback."""

    def __call__(
        self,
        gesture: Gesture,
        screen_x: int,
        screen_y: int,
    ) -> None: ...


_MAX_BACKOFF_S = 30.0
_INITIAL_BACKOFF_S = 0.5


class CameraTracker:
    """Processes webcam frames in a daemon thread.

    Parameters
    ----------
    camera_cfg:
        Webcam capture settings.
    gesture_cfg:
        Gesture classification thresholds.
    smoother_cfg:
        EMA smoothing parameters.
    on_frame:
        Optional callback invoked after every processed frame.
    overlay:
        Optional :class:`OverlayWindow` instance. When provided,
        annotated frames are pushed to its queue for display.
    """

    def __init__(
        self,
        camera_cfg: CameraConfig | None = None,
        gesture_cfg: GestureConfig | None = None,
        smoother_cfg: SmootherConfig | None = None,
        on_frame: FrameCallback | None = None,
        overlay: OverlayWindow | None = None,
    ) -> None:
        self._cam_cfg = camera_cfg or CameraConfig()
        self._gesture_cfg = gesture_cfg or GestureConfig()
        self._smoother_cfg = smoother_cfg or SmootherConfig()
        self._on_frame = on_frame
        self._overlay = overlay

        self._classifier = GestureClassifier(self._gesture_cfg)
        self._smoother = ExponentialMovingSmoother(self._smoother_cfg)
        self._controller = MouseController(self._gesture_cfg)

        # Instantiate MediaPipe Hands once, not per-loop iteration.
        self._hands = mp_hands_module.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()  # set = paused

        self._prev_index_y: float | None = None

    def start(self) -> None:
        """Start the tracking loop in a daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            log.warning("Tracker already running.")
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="mousespot-tracker", daemon=True
        )
        self._thread.start()
        log.info("Tracker started.")

    def stop(self) -> None:
        """Signal the tracking thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._smoother.reset()
        self._prev_index_y = None
        self._hands.close()
        log.info("Tracker stopped.")

    def pause(self) -> None:
        """Pause frame processing (camera stays open)."""
        self._pause_event.set()
        log.info("Tracker paused.")

    def resume(self) -> None:
        """Resume frame processing."""
        self._pause_event.clear()
        self._smoother.reset()
        self._prev_index_y = None
        log.info("Tracker resumed.")

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def _loop(self) -> None:
        """Run the capture -> detect -> act pipeline."""
        cap: cv2.VideoCapture | None = None
        backoff = _INITIAL_BACKOFF_S

        try:
            while not self._stop_event.is_set():
                if cap is None or not cap.isOpened():
                    cap = self._open_camera()
                    if cap is None:
                        log.warning(
                            "Camera unavailable, retrying in %.1fs...",
                            backoff,
                        )
                        self._stop_event.wait(backoff)
                        backoff = min(backoff * 2, _MAX_BACKOFF_S)
                        continue
                    backoff = _INITIAL_BACKOFF_S

                if self._pause_event.is_set():
                    self._stop_event.wait(0.1)
                    continue

                ok, frame = cap.read()
                if not ok:
                    log.warning("Frame read failed, re-opening camera.")
                    cap.release()
                    cap = None
                    continue

                frame = cv2.flip(frame, 1)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self._hands.process(rgb)

                hand_detected = bool(results.multi_hand_landmarks)
                gesture = Gesture.FREEZE
                sx, sy = 0, 0

                if hand_detected:
                    hand_lms = results.multi_hand_landmarks[0]
                    confidence: float = 1.0
                    if results.multi_handedness:
                        confidence = results.multi_handedness[0].classification[
                            0
                        ].score

                    landmarks = [
                        LandmarkPoint(lm.x, lm.y, lm.z)
                        for lm in hand_lms.landmark
                    ]

                    gesture = self._classifier.classify(
                        landmarks,
                        confidence=confidence,
                        prev_index_y=self._prev_index_y,
                    )
                    self._prev_index_y = landmarks[8].y  # index tip

                    screen_w, screen_h = self._controller.screen_size
                    cam_w, cam_h = self._cam_cfg.width, self._cam_cfg.height
                    margin = self._gesture_cfg.frame_margin

                    px = landmarks[8].x * cam_w
                    py = landmarks[8].y * cam_h

                    raw_x = np.interp(px, (margin, cam_w - margin), (0, screen_w))
                    raw_y = np.interp(py, (margin, cam_h - margin), (0, screen_h))

                    sx, sy = self._smoother.update(int(raw_x), int(raw_y))

                    if gesture is Gesture.MOVE:
                        self._controller.move(sx, sy)
                    elif gesture is Gesture.LEFT_CLICK:
                        self._controller.move(sx, sy)
                        self._controller.click("left")
                    elif gesture is Gesture.RIGHT_CLICK:
                        self._controller.move(sx, sy)
                        self._controller.click("right")
                    elif gesture is Gesture.DOUBLE_CLICK:
                        self._controller.move(sx, sy)
                        self._controller.click("left", double=True)
                    elif gesture is Gesture.SCROLL_UP:
                        self._controller.scroll(1)
                    elif gesture is Gesture.SCROLL_DOWN:
                        self._controller.scroll(-1)
                    if self._overlay is not None:
                        mp_drawing.draw_landmarks(
                            frame,
                            hand_lms,
                            mp_hands_module.HAND_CONNECTIONS,
                        )
                else:
                    self._prev_index_y = None

                if self._overlay is not None:
                    self._overlay.push_frame(frame, gesture, hand_detected)

        finally:
            if cap is not None:
                cap.release()
            log.info("Camera released.")

    # ── Helpers ───────────────────────────────────────────────────────

    def _open_camera(self) -> cv2.VideoCapture | None:
        """Try to open the configured camera device."""
        cap = cv2.VideoCapture(self._cam_cfg.device_index)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cam_cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cam_cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self._cam_cfg.fps)
        log.info(
            "Camera %d opened (%dx%d @%dfps).",
            self._cam_cfg.device_index,
            self._cam_cfg.width,
            self._cam_cfg.height,
            self._cam_cfg.fps,
        )
        return cap
