
from __future__ import annotations

import time
from unittest import mock

import pytest

from mouse_spot.config import GestureConfig
from mouse_spot.gesture import Gesture, GestureClassifier, LandmarkPoint

# 21 neutral landmarks - all at (0.5, 0.5) with tips *above* PIPs
# (fingers extended by default).  Tests override specific landmarks.

_NEUTRAL: list[LandmarkPoint] = [LandmarkPoint(0.5, 0.5, 0.0)] * 21


def _landmarks(overrides: dict[int, tuple[float, float]]) -> list[LandmarkPoint]:
    """Return a copy of neutral landmarks with specific indices overridden."""
    lms = list(_NEUTRAL)
    for idx, (x, y) in overrides.items():
        lms[idx] = LandmarkPoint(x, y)
    return lms


def _curled_hand() -> list[LandmarkPoint]:
    """All finger tips *below* their PIP joints (closed fist).

    Wrist at (0.5, 0.8), MCP9 at (0.5, 0.5) → hand scale = 0.3.
    Each tip.y > pip.y so ``_is_finger_extended`` returns False.
    """
    lms = list(_NEUTRAL)
    lms[0] = LandmarkPoint(0.5, 0.8)     # wrist
    lms[9] = LandmarkPoint(0.5, 0.5)     # middle MCP
    # Thumb - for curled hand we just need tip ≠ near index/middle tips
    lms[4] = LandmarkPoint(0.45, 0.65)   # thumb tip
    # Index: PIP above tip
    lms[6] = LandmarkPoint(0.5, 0.55)    # index PIP
    lms[8] = LandmarkPoint(0.5, 0.60)    # index tip (below PIP → curled)
    # Middle
    lms[10] = LandmarkPoint(0.5, 0.55)   # middle PIP
    lms[12] = LandmarkPoint(0.5, 0.60)   # middle tip
    # Ring
    lms[14] = LandmarkPoint(0.5, 0.55)   # ring PIP
    lms[16] = LandmarkPoint(0.5, 0.60)   # ring tip
    # Pinky
    lms[18] = LandmarkPoint(0.5, 0.55)   # pinky PIP
    lms[20] = LandmarkPoint(0.5, 0.60)   # pinky tip
    return lms


def _index_only_hand() -> list[LandmarkPoint]:
    """Index finger extended, all others curled - should yield MOVE.

    Wrist at (0.5, 0.8), MCP9 at (0.5, 0.5) → scale = 0.3.
    """
    lms = _curled_hand()
    # Extend index finger: tip above PIP
    lms[6] = LandmarkPoint(0.5, 0.50)    # index PIP
    lms[8] = LandmarkPoint(0.5, 0.35)    # index tip (above PIP → extended)
    return lms


def _scroll_hand(index_y: float = 0.35) -> list[LandmarkPoint]:
    """Index + middle extended, ring + pinky curled."""
    lms = _curled_hand()
    # Index extended
    lms[6] = LandmarkPoint(0.5, 0.50)
    lms[8] = LandmarkPoint(0.5, index_y)
    # Middle extended
    lms[10] = LandmarkPoint(0.5, 0.50)
    lms[12] = LandmarkPoint(0.5, 0.35)
    return lms


@pytest.fixture
def classifier() -> GestureClassifier:
    return GestureClassifier(GestureConfig(pinch_threshold=0.05))


class TestConfidence:
    """Low confidence must always return FREEZE."""

    def test_low_confidence_returns_freeze(
        self, classifier: GestureClassifier
    ) -> None:
        result = classifier.classify(_index_only_hand(), confidence=0.5)
        assert result is Gesture.FREEZE

    def test_exact_threshold_returns_freeze(
        self, classifier: GestureClassifier
    ) -> None:
        # 0.8 is < boundary (strict inequality)
        result = classifier.classify(_index_only_hand(), confidence=0.79)
        assert result is Gesture.FREEZE

    def test_high_confidence_does_not_freeze(
        self, classifier: GestureClassifier
    ) -> None:
        result = classifier.classify(_index_only_hand(), confidence=0.95)
        assert result is not Gesture.FREEZE


class TestMoveGesture:
    """Index finger extended, others curled → MOVE."""

    def test_index_only_is_move(self, classifier: GestureClassifier) -> None:
        result = classifier.classify(_index_only_hand(), confidence=0.95)
        assert result is Gesture.MOVE


class TestLeftClick:
    """Pinch between thumb tip (lm4) and index tip (lm8)."""

    def test_thumb_index_pinch(self, classifier: GestureClassifier) -> None:
        lms = _index_only_hand()
        # Place thumb tip and index tip very close together
        lms[4] = LandmarkPoint(0.500, 0.350)
        lms[8] = LandmarkPoint(0.501, 0.351)
        # Ensure it returns LEFT_CLICK and not DOUBLE_CLICK
        with mock.patch.object(time, "monotonic", return_value=100.0):
            result = classifier.classify(lms, confidence=0.95)
        assert result is Gesture.LEFT_CLICK

    def test_no_pinch_when_far(self, classifier: GestureClassifier) -> None:
        lms = _index_only_hand()
        lms[4] = LandmarkPoint(0.2, 0.2)
        lms[8] = LandmarkPoint(0.8, 0.8)
        result = classifier.classify(lms, confidence=0.95)
        assert result is not Gesture.LEFT_CLICK


class TestDoubleClick:
    """Two LEFT_CLICKs in rapid succession within window."""

    def test_double_click_triggered(self, classifier: GestureClassifier) -> None:
        lms = _index_only_hand()
        lms[4] = LandmarkPoint(0.500, 0.350)
        lms[8] = LandmarkPoint(0.501, 0.351)

        # First click at t=100s
        with mock.patch.object(time, "monotonic", return_value=100.0):
            res1 = classifier.classify(lms, confidence=0.95)

        # Second click at t=100.2s (< 400ms window)
        with mock.patch.object(time, "monotonic", return_value=100.2):
            res2 = classifier.classify(lms, confidence=0.95)

        assert res1 is Gesture.LEFT_CLICK
        assert res2 is Gesture.DOUBLE_CLICK

    def test_double_click_outside_window(self, classifier: GestureClassifier) -> None:
        lms = _index_only_hand()
        lms[4] = LandmarkPoint(0.500, 0.350)
        lms[8] = LandmarkPoint(0.501, 0.351)

        # First click at t=100s
        with mock.patch.object(time, "monotonic", return_value=100.0):
            res1 = classifier.classify(lms, confidence=0.95)

        # Second click at t=101.0s (> 400ms window)
        with mock.patch.object(time, "monotonic", return_value=101.0):
            res2 = classifier.classify(lms, confidence=0.95)

        assert res1 is Gesture.LEFT_CLICK
        assert res2 is Gesture.LEFT_CLICK


class TestRightClick:
    """Pinch between thumb tip (lm4) and middle tip (lm12)."""

    def test_thumb_middle_pinch(self, classifier: GestureClassifier) -> None:
        lms = _curled_hand()
        # Place thumb tip and middle tip very close
        lms[4] = LandmarkPoint(0.500, 0.500)
        lms[12] = LandmarkPoint(0.501, 0.501)
        result = classifier.classify(lms, confidence=0.95)
        assert result is Gesture.RIGHT_CLICK


class TestScroll:
    """Index + middle extended, direction from prev_index_y."""

    def test_scroll_up(self, classifier: GestureClassifier) -> None:
        lms = _scroll_hand(index_y=0.30)
        result = classifier.classify(lms, confidence=0.95, prev_index_y=0.40)
        assert result is Gesture.SCROLL_UP

    def test_scroll_down(self, classifier: GestureClassifier) -> None:
        lms = _scroll_hand(index_y=0.45)  # tip still above PIP (0.50) → extended
        result = classifier.classify(lms, confidence=0.95, prev_index_y=0.30)
        assert result is Gesture.SCROLL_DOWN

    def test_no_prev_y_falls_back_to_move(
        self, classifier: GestureClassifier
    ) -> None:
        lms = _scroll_hand()
        result = classifier.classify(lms, confidence=0.95, prev_index_y=None)
        assert result is Gesture.MOVE


class TestFreeze:
    """All fingers curled → FREEZE."""

    def test_closed_fist_is_freeze(self, classifier: GestureClassifier) -> None:
        result = classifier.classify(_curled_hand(), confidence=0.95)
        assert result is Gesture.FREEZE
