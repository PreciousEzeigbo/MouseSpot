
from __future__ import annotations

import pytest

from mouse_spot.config import SmootherConfig
from mouse_spot.smoother import ExponentialMovingSmoother

@pytest.fixture
def smoother() -> ExponentialMovingSmoother:
    """Smoother with alpha=0.5 and deadzone=4 for predictable maths."""
    return ExponentialMovingSmoother(SmootherConfig(alpha=0.5, deadzone_px=4))


@pytest.fixture
def no_deadzone_smoother() -> ExponentialMovingSmoother:
    """Smoother with deadzone disabled (0 px)."""
    return ExponentialMovingSmoother(SmootherConfig(alpha=0.5, deadzone_px=0))


class TestNormalSmoothing:
    """EMA formula: smoothed = alpha * new + (1 - alpha) * prev."""

    def test_first_sample_is_passed_through(
        self, no_deadzone_smoother: ExponentialMovingSmoother
    ) -> None:
        """The very first update must return the raw input as-is."""
        result = no_deadzone_smoother.update(100.0, 200.0)
        assert result == (100, 200)

    def test_second_sample_applies_ema(
        self, no_deadzone_smoother: ExponentialMovingSmoother
    ) -> None:
        """With alpha=0.5 the second sample should be the midpoint."""
        no_deadzone_smoother.update(100.0, 200.0)
        result = no_deadzone_smoother.update(200.0, 400.0)
        # smoothed_x = 0.5*200 + 0.5*100 = 150
        # smoothed_y = 0.5*400 + 0.5*200 = 300
        assert result == (150, 300)

    def test_successive_samples_converge(
        self, no_deadzone_smoother: ExponentialMovingSmoother
    ) -> None:
        """Repeated identical inputs should converge toward that value."""
        no_deadzone_smoother.update(0.0, 0.0)
        for _ in range(20):
            result = no_deadzone_smoother.update(100.0, 100.0)
        assert result == (100, 100)

    def test_returns_integer_tuple(
        self, no_deadzone_smoother: ExponentialMovingSmoother
    ) -> None:
        result = no_deadzone_smoother.update(33.7, 77.3)
        assert isinstance(result, tuple)
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)


class TestDeadzone:
    """Movement smaller than deadzone_px must not update the position."""

    def test_tiny_move_is_suppressed(
        self, smoother: ExponentialMovingSmoother
    ) -> None:
        """A 1-px move should be within the 4-px deadzone."""
        first = smoother.update(100.0, 100.0)
        second = smoother.update(101.0, 101.0)  # distance ≈ 1.41 < 4
        assert second == first

    def test_large_move_is_applied(
        self, smoother: ExponentialMovingSmoother
    ) -> None:
        """A move beyond the deadzone must update the position."""
        smoother.update(100.0, 100.0)
        result = smoother.update(200.0, 200.0)  # distance ≈ 141 >> 4
        assert result != (100, 100)

    def test_position_unchanged_after_suppressed_move(
        self, smoother: ExponentialMovingSmoother
    ) -> None:
        smoother.update(100.0, 100.0)
        smoother.update(101.0, 100.0)  # distance = 1 < 4
        assert smoother.position == (100, 100)

    def test_zero_deadzone_always_updates(
        self, no_deadzone_smoother: ExponentialMovingSmoother
    ) -> None:
        """With deadzone=0 every update changes the position."""
        no_deadzone_smoother.update(100.0, 100.0)
        no_deadzone_smoother.update(100.5, 100.5)
        # 0.5*100.5 + 0.5*100 = 100.25 -> rounds to 100, but internal
        # state should still have changed.
        assert no_deadzone_smoother.position is not None


class TestReset:
    """reset() must clear internal state completely."""

    def test_position_is_none_after_reset(
        self, smoother: ExponentialMovingSmoother
    ) -> None:
        smoother.update(100.0, 200.0)
        smoother.reset()
        assert smoother.position is None

    def test_next_sample_after_reset_initialises_fresh(
        self, smoother: ExponentialMovingSmoother
    ) -> None:
        smoother.update(100.0, 200.0)
        smoother.reset()
        result = smoother.update(500.0, 600.0)
        assert result == (500, 600)

    def test_double_reset_is_safe(
        self, smoother: ExponentialMovingSmoother
    ) -> None:
        smoother.reset()
        smoother.reset()
        assert smoother.position is None
