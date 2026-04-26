
from __future__ import annotations

import collections
import contextlib
import logging
import queue
import threading
import time

import cv2
import numpy as np

from mouse_spot.gesture import Gesture

__all__ = ["OverlayWindow"]

log = logging.getLogger(__name__)

_WINDOW_NAME = "HandMouse Monitor"
_FPS_WINDOW = 30  # rolling average over N frames

_WHITE = (255, 255, 255)
_BLACK = (0, 0, 0)
_GREEN = (0, 200, 0)
_RED = (0, 0, 220)


class _FramePacket:
    """Container for data pushed from the tracker thread."""

    __slots__ = ("frame", "gesture", "hand_detected")

    def __init__(
        self,
        frame: np.ndarray,
        gesture: Gesture,
        hand_detected: bool,
    ) -> None:
        self.frame = frame
        self.gesture = gesture
        self.hand_detected = hand_detected


class OverlayWindow:
    """Displays annotated camera frames in a resizable OpenCV window.

    Parameters
    ----------
    maxsize:
        Maximum queue depth. When the queue is full the oldest frame
        is discarded so the tracker thread is never blocked.
    """

    def __init__(self, maxsize: int = 2) -> None:
        self._queue: queue.Queue[_FramePacket] = queue.Queue(maxsize=maxsize)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._visible = threading.Event()
        self._visible.set()  # visible by default

        self._fps_times: collections.deque[float] = collections.deque(
            maxlen=_FPS_WINDOW
        )

    def push_frame(
        self,
        frame: np.ndarray,
        gesture: Gesture,
        hand_detected: bool,
    ) -> None:
        """Enqueue a frame for display (non-blocking, drops oldest)."""
        packet = _FramePacket(frame, gesture, hand_detected)
        try:
            self._queue.put_nowait(packet)
        except queue.Full:
            # Drop the oldest frame to make room.
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait(packet)

    def start(self) -> None:
        """Launch the overlay display thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="mousespot-overlay", daemon=True
        )
        self._thread.start()
        log.info("Overlay window started.")

    def stop(self) -> None:
        """Signal the overlay thread to stop and clean up."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        log.info("Overlay window stopped.")

    def toggle(self) -> None:
        """Toggle visibility of the overlay window."""
        if self._visible.is_set():
            self._visible.clear()
            log.info("Overlay hidden.")
        else:
            self._visible.set()
            log.info("Overlay shown.")

    @property
    def is_visible(self) -> bool:
        return self._visible.is_set()

    def _loop(self) -> None:
        """Consume frames from the queue and display them."""
        cv2.namedWindow(_WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
        cv2.resizeWindow(_WINDOW_NAME, 640, 480)

        try:
            while not self._stop_event.is_set():
                if not self._visible.is_set():
                    cv2.waitKey(50)
                    continue

                try:
                    packet = self._queue.get(timeout=0.1)
                except queue.Empty:
                    cv2.waitKey(1)
                    continue

                frame = packet.frame
                self._fps_times.append(time.monotonic())

                cv2.imshow(_WINDOW_NAME, frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

        finally:
            cv2.destroyWindow(_WINDOW_NAME)

    @staticmethod
    def _draw_gesture_label(frame: np.ndarray, gesture: Gesture) -> None:
        """Render the gesture name at the top-left with black outline."""
        text = gesture.name
        pos = (16, 32)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.8
        thickness = 2
        cv2.putText(frame, text, pos, font, scale, _BLACK, thickness + 2, cv2.LINE_AA)
        cv2.putText(frame, text, pos, font, scale, _WHITE, thickness, cv2.LINE_AA)

    @staticmethod
    def _draw_status_pill(frame: np.ndarray, hand_detected: bool) -> None:
        """Draw a coloured circle + label at the top-right."""
        _h, w = frame.shape[:2]
        colour = _GREEN if hand_detected else _RED
        label = "TRACKING" if hand_detected else "NO HAND"

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.55
        thickness = 2
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)

        cx = w - tw - 36
        cy = 24
        cv2.circle(frame, (cx, cy), 8, colour, -1, cv2.LINE_AA)

        tx = cx + 14
        ty = cy + th // 2
        cv2.putText(frame, label, (tx, ty), font, scale, colour, thickness, cv2.LINE_AA)

    def _draw_fps(self, frame: np.ndarray) -> None:
        """Render FPS as a rolling average at the bottom-left."""
        if len(self._fps_times) < 2:
            return
        elapsed = self._fps_times[-1] - self._fps_times[0]
        if elapsed <= 0:
            return
        fps = (len(self._fps_times) - 1) / elapsed

        h = frame.shape[0]
        text = f"FPS: {fps:.1f}"
        pos = (16, h - 16)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.6
        cv2.putText(frame, text, pos, font, scale, _BLACK, 3, cv2.LINE_AA)
        cv2.putText(frame, text, pos, font, scale, _GREEN, 1, cv2.LINE_AA)
