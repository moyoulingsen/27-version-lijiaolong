from __future__ import annotations

from rl.replay.pygame_player import HoldSeekController


def test_short_press_does_not_seek() -> None:
    controller = HoldSeekController()
    controller.press(1)
    assert controller.update(0.20, 30.0) == 0
    assert controller.release(1) is False


def test_long_press_seeks_and_accelerates() -> None:
    controller = HoldSeekController()
    controller.press(1)
    assert controller.update(0.28, 30.0) == 0
    first = controller.update(0.20, 30.0)
    later = controller.update(1.00, 30.0)
    assert first > 0
    assert later > first
    assert controller.release(1) is True


def test_reverse_hold_returns_negative_frames() -> None:
    controller = HoldSeekController()
    controller.press(-1)
    assert controller.update(0.50, 30.0) < 0
    assert controller.release(-1) is True
