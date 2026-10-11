"""Pygame-independent arena coordinates and sentry state."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Arena:
    """RMUC 2026 field dimensions and source-map metadata, in metres."""

    width: float = 28.0
    height: float = 15.0
    map_resolution: float = 0.05
    map_origin_x: float = -0.55
    map_origin_y: float = 0.0

    def clamp(self, x: float, y: float) -> tuple[float, float]:
        return min(max(x, 0.0), self.width), min(max(y, 0.0), self.height)

    def map_crop(self, source_width: int, source_height: int) -> tuple[int, int, int, int]:
        """Return the PGM crop corresponding to world [0, 28] x [0, 15]."""
        left = round((0.0 - self.map_origin_x) / self.map_resolution)
        top = round(source_height - (self.height - self.map_origin_y) / self.map_resolution)
        width = round(self.width / self.map_resolution)
        height = round(self.height / self.map_resolution)
        if left < 0 or top < 0 or left + width > source_width or top + height > source_height:
            raise ValueError("RMUC 2026 world bounds are outside the source map")
        return left, top, width, height


@dataclass(frozen=True)
class Viewport:
    """A letterboxed screen rectangle preserving the 28:15 arena ratio."""

    left: float
    top: float
    width: float
    height: float
    arena: Arena

    @classmethod
    def fit(
        cls,
        window_width: int,
        window_height: int,
        arena: Arena,
        *,
        header_height: int = 84,
        footer_height: int = 32,
        horizontal_margin: int = 42,
        vertical_margin: int = 16,
    ) -> "Viewport":
        available_width = max(1, window_width - 2 * horizontal_margin)
        available_height = max(
            1,
            window_height - header_height - footer_height - 2 * vertical_margin,
        )
        scale = min(available_width / arena.width, available_height / arena.height)
        width = arena.width * scale
        height = arena.height * scale
        left = (window_width - width) / 2.0
        top = header_height + vertical_margin + (available_height - height) / 2.0
        return cls(left, top, width, height, arena)

    @property
    def scale(self) -> float:
        return self.width / self.arena.width

    def world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        return self.left + x * self.scale, self.top + (self.arena.height - y) * self.scale

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.left) / self.scale, self.arena.height - (y - self.top) / self.scale

    def contains(self, x: float, y: float) -> bool:
        return (
            self.left <= x <= self.left + self.width
            and self.top <= y <= self.top + self.height
        )


def normalize_angle(angle: float) -> float:
    return (angle + math.pi) % math.tau - math.pi


@dataclass
class SentryState:
    """State updated by either decision control or temporary manual control."""

    x: float = 4.971
    y: float = 7.5
    manual_control: bool = False
    movement_speed: float = 3.0
    spin_angle: float = 0.0
    spin_speed: float = math.radians(150.0)
    turret_angle: float = 0.0
    turret_speed: float = math.radians(210.0)

    def enable_manual_control(self) -> None:
        self.manual_control = True

    def cancel_manual_control(self) -> None:
        self.manual_control = False

    def update(
        self,
        elapsed_seconds: float,
        move_x: float,
        move_y: float,
        arena: Arena,
        *,
        spin_enabled: bool = True,
        spin_speed_scale: float = 1.0,
        turret_enabled: bool = True,
    ) -> None:
        if elapsed_seconds < 0.0:
            raise ValueError("elapsed_seconds must be non-negative")
        if spin_speed_scale < 0.0:
            raise ValueError("spin_speed_scale must be non-negative")

        if spin_enabled:
            self.spin_angle = normalize_angle(
                self.spin_angle + self.spin_speed * spin_speed_scale * elapsed_seconds
            )
        if turret_enabled:
            self.turret_angle = normalize_angle(
                self.turret_angle + self.turret_speed * elapsed_seconds
            )

        if not self.manual_control:
            return

        length = math.hypot(move_x, move_y)
        if length > 1.0:
            move_x /= length
            move_y /= length
        self.x, self.y = arena.clamp(
            self.x + move_x * self.movement_speed * elapsed_seconds,
            self.y + move_y * self.movement_speed * elapsed_seconds,
        )
