"""Field gain-point zones and energy-rune rule data for the 2-D validator.

The rulebook's cropped text version does not include the field-geometry pages,
so these rectangles are a 2-D approximation anchored to the official PGM and
the visible field layout.  They are deliberately data-only: changing a zone
does not change the ROS/behaviour-tree interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .field_geometry import (
    BLUE_ASSEMBLY,
    BLUE_BASE_GAIN,
    BLUE_FLY_SLOPE,
    BLUE_FORT,
    BLUE_FORT_POLYGON,
    BLUE_OUTPOST_GAIN,
    BLUE_ROAD,
    BLUE_ROAD_CROSSING_CARDS,
    BLUE_SUPPLY_ZONE,
    BLUE_TERRAIN_HIGHLAND,
    BLUE_TRAPEZOID_HIGHLAND,
    BLUE_TUNNEL,
    CENTRAL_HIGHLAND,
    RED_ASSEMBLY,
    RED_BASE_GAIN,
    RED_FLY_SLOPE,
    RED_FORT,
    RED_FORT_POLYGON,
    RED_OUTPOST_GAIN,
    RED_ROAD,
    RED_ROAD_CROSSING_CARDS,
    RED_SUPPLY_ZONE,
    RED_TERRAIN_HIGHLAND,
    RED_TRAPEZOID_HIGHLAND,
    RED_TUNNEL,
    RUNE_POSITIONS,
)


ROAD_CROSSING_CARDS = {
    "red": RED_ROAD_CROSSING_CARDS,
    "blue": BLUE_ROAD_CROSSING_CARDS,
}
ROAD_CARD_HALF_EXTENT = 0.18
ROAD_CROSSING_WINDOW = 3.0


@dataclass(frozen=True)
class FieldZone:
    """2-D gain region with its rule effects and optional polygon boundary."""

    name: str
    kind: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    team: str | None = None
    buffs: tuple[tuple[str, float, float], ...] = ()
    mode: str = "continuous"
    cooldown: float = 0.0
    color: tuple[int, int, int] = (120, 180, 220)
    label: str = ""
    polygon: tuple[tuple[float, float], ...] = ()

    def contains(self, x: float, y: float) -> bool:
        if not (self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y):
            return False
        if not self.polygon:
            return True

        inside = False
        previous_x, previous_y = self.polygon[-1]
        for current_x, current_y in self.polygon:
            cross = (x - previous_x) * (current_y - previous_y) - (
                y - previous_y
            ) * (current_x - previous_x)
            on_edge = (
                abs(cross) <= 1e-9
                and min(previous_x, current_x) - 1e-9 <= x <= max(previous_x, current_x) + 1e-9
                and min(previous_y, current_y) - 1e-9 <= y <= max(previous_y, current_y) + 1e-9
            )
            if on_edge:
                return True
            if (current_y > y) != (previous_y > y):
                edge_x = previous_x + (y - previous_y) * (
                    current_x - previous_x
                ) / (current_y - previous_y)
                if x < edge_x:
                    inside = not inside
            previous_x, previous_y = current_x, current_y
        return inside


FIELD_ZONES: tuple[FieldZone, ...] = (
    FieldZone(
        "red_supply", "supply", RED_SUPPLY_ZONE[0], RED_SUPPLY_ZONE[2], RED_SUPPLY_ZONE[1], RED_SUPPLY_ZONE[3], "red",
        color=(45, 174, 99), label="己方补给区",
    ),
    FieldZone(
        "blue_supply", "supply", BLUE_SUPPLY_ZONE[0], BLUE_SUPPLY_ZONE[2], BLUE_SUPPLY_ZONE[1], BLUE_SUPPLY_ZONE[3], "blue",
        color=(45, 130, 220), label="敌方补给区",
    ),
    FieldZone(
        "red_base_gain", "base_gain", RED_BASE_GAIN[0], RED_BASE_GAIN[2], RED_BASE_GAIN[1], RED_BASE_GAIN[3], "red",
        buffs=(("defence", 0.50, 0.5),),
        color=(74, 145, 222), label="己方基地增益",
    ),
    FieldZone(
        "blue_base_gain", "base_gain", BLUE_BASE_GAIN[0], BLUE_BASE_GAIN[2], BLUE_BASE_GAIN[1], BLUE_BASE_GAIN[3], "blue",
        buffs=(("defence", 0.50, 0.5),),
        color=(74, 145, 222), label="敌方基地增益",
    ),
    FieldZone(
        "central_highland", "central_highland", CENTRAL_HIGHLAND[0], CENTRAL_HIGHLAND[2], CENTRAL_HIGHLAND[1], CENTRAL_HIGHLAND[3], None,
        buffs=(("defence", 0.25, 0.5),),
        color=(160, 110, 220), label="中央高地",
    ),
    FieldZone(
        "red_trapezoid", "trapezoid_highland", RED_TRAPEZOID_HIGHLAND[0], RED_TRAPEZOID_HIGHLAND[2], RED_TRAPEZOID_HIGHLAND[1], RED_TRAPEZOID_HIGHLAND[3], "red",
        buffs=(("defence", 0.50, 0.5),),
        color=(222, 148, 62), label="己方梯形高地",
    ),
    FieldZone(
        "blue_trapezoid", "trapezoid_highland", BLUE_TRAPEZOID_HIGHLAND[0], BLUE_TRAPEZOID_HIGHLAND[2], BLUE_TRAPEZOID_HIGHLAND[1], BLUE_TRAPEZOID_HIGHLAND[3], "blue",
        buffs=(("defence", 0.50, 0.5),),
        color=(222, 148, 62), label="敌方梯形高地",
    ),
    FieldZone(
        "red_road", "terrain_road", RED_ROAD[0], RED_ROAD[2], RED_ROAD[1], RED_ROAD[3], "red",
        buffs=(("defence", 0.25, 5.0),), mode="trigger", cooldown=15.0,
        color=(176, 132, 82), label="公路",
    ),
    FieldZone(
        "blue_road", "terrain_road", BLUE_ROAD[0], BLUE_ROAD[2], BLUE_ROAD[1], BLUE_ROAD[3], "blue",
        buffs=(("defence", 0.25, 5.0),), mode="trigger", cooldown=15.0,
        color=(176, 132, 82), label="公路",
    ),
    FieldZone(
        "red_terrain_highland", "terrain_highland", RED_TERRAIN_HIGHLAND[0], RED_TERRAIN_HIGHLAND[2], RED_TERRAIN_HIGHLAND[1], RED_TERRAIN_HIGHLAND[3], "red",
        buffs=(("defence", 0.25, 30.0),), mode="trigger", cooldown=30.0,
        color=(190, 120, 70), label="高地跨越",
    ),
    FieldZone(
        "blue_terrain_highland", "terrain_highland", BLUE_TERRAIN_HIGHLAND[0], BLUE_TERRAIN_HIGHLAND[2], BLUE_TERRAIN_HIGHLAND[1], BLUE_TERRAIN_HIGHLAND[3], "blue",
        buffs=(("defence", 0.25, 30.0),), mode="trigger", cooldown=30.0,
        color=(190, 120, 70), label="高地跨越",
    ),
    FieldZone(
        "red_fly_slope", "terrain_fly_slope", RED_FLY_SLOPE[0], RED_FLY_SLOPE[2], RED_FLY_SLOPE[1], RED_FLY_SLOPE[3], "red",
        buffs=(("defence", 0.25, 30.0),), mode="trigger", cooldown=30.0,
        color=(120, 190, 160), label="飞坡",
    ),
    FieldZone(
        "blue_fly_slope", "terrain_fly_slope", BLUE_FLY_SLOPE[0], BLUE_FLY_SLOPE[2], BLUE_FLY_SLOPE[1], BLUE_FLY_SLOPE[3], "blue",
        buffs=(("defence", 0.25, 30.0),), mode="trigger", cooldown=30.0,
        color=(120, 190, 160), label="飞坡",
    ),
    FieldZone(
        "red_tunnel", "terrain_tunnel", RED_TUNNEL[0], RED_TUNNEL[2], RED_TUNNEL[1], RED_TUNNEL[3], "red",
        buffs=(("defence", 0.50, 10.0), ("heat_cooling", 2.0, 120.0)),
        mode="trigger", cooldown=120.0,
        color=(110, 130, 170), label="隧道",
    ),
    FieldZone(
        "blue_tunnel", "terrain_tunnel", BLUE_TUNNEL[0], BLUE_TUNNEL[2], BLUE_TUNNEL[1], BLUE_TUNNEL[3], "blue",
        buffs=(("defence", 0.50, 10.0), ("heat_cooling", 2.0, 120.0)),
        mode="trigger", cooldown=120.0,
        color=(110, 130, 170), label="隧道",
    ),
    FieldZone(
        "red_outpost_gain", "outpost_gain", RED_OUTPOST_GAIN[0], RED_OUTPOST_GAIN[2], RED_OUTPOST_GAIN[1], RED_OUTPOST_GAIN[3], "red",
        buffs=(("defence", 0.25, 0.5),),
        color=(205, 75, 82), label="己方前哨增益",
    ),
    FieldZone(
        "blue_outpost_gain", "outpost_gain", BLUE_OUTPOST_GAIN[0], BLUE_OUTPOST_GAIN[2], BLUE_OUTPOST_GAIN[1], BLUE_OUTPOST_GAIN[3], "blue",
        buffs=(("defence", 0.25, 0.5),),
        color=(57, 124, 210), label="敌方前哨增益",
    ),
    FieldZone(
        "red_assembly", "assembly", RED_ASSEMBLY[0], RED_ASSEMBLY[2], RED_ASSEMBLY[1], RED_ASSEMBLY[3], "red",
        color=(150, 150, 160), label="装配区",
    ),
    FieldZone(
        "blue_assembly", "assembly", BLUE_ASSEMBLY[0], BLUE_ASSEMBLY[2], BLUE_ASSEMBLY[1], BLUE_ASSEMBLY[3], "blue",
        color=(150, 150, 160), label="装配区",
    ),
    FieldZone(
        "red_fort", "fort", RED_FORT[0], RED_FORT[2], RED_FORT[1], RED_FORT[3], "red",
        buffs=(("defence", 0.50, 0.5), ("heat_cooling", 2.0, 0.5)),
        color=(210, 180, 70), label="己方堡垒",
        polygon=RED_FORT_POLYGON,
    ),
    FieldZone(
        "blue_fort", "fort", BLUE_FORT[0], BLUE_FORT[2], BLUE_FORT[1], BLUE_FORT[3], "blue",
        buffs=(("defence", 0.50, 0.5), ("heat_cooling", 2.0, 0.5)),
        color=(210, 180, 70), label="敌方堡垒",
        polygon=BLUE_FORT_POLYGON,
    ),
)


def zones_for_team(team: str = "red") -> tuple[FieldZone, ...]:
    return tuple(
        zone for zone in FIELD_ZONES if zone.team is None or zone.team == team
    )


# Rulebook 5.5.2 / table 5-17 / table 5-18.
SMALL_RUNE_DEFENCE = 0.25
SMALL_RUNE_DURATION = 45.0
SMALL_RUNE_ACTIVATION_WINDOW = 20.0
LARGE_RUNE_ACTIVATION_WINDOW = 20.0
def large_rune_profile(
    ring_average: float,
    arm_count: int,
) -> tuple[tuple[str, float, float], ...]:
    """Return the rulebook large-rune buff set for a 2-D activation."""
    if ring_average <= 3.0:
        attack, defence, cooling = 1.50, 0.25, 1.0
    elif ring_average <= 7.0:
        attack, defence, cooling = 1.50, 0.25, 2.0
    elif ring_average <= 8.0:
        attack, defence, cooling = 2.00, 0.25, 2.0
    elif ring_average <= 9.0:
        attack, defence, cooling = 2.00, 0.25, 3.0
    else:
        attack, defence, cooling = 3.00, 0.50, 5.0
    duration = max(30.0, min(60.0, 5.0 * arm_count + 5.0))
    buffs: list[tuple[str, float, float]] = [
        ("attack", attack, duration),
        ("defence", defence, duration),
    ]
    if cooling > 1.0:
        buffs.append(("heat_cooling", cooling, duration))
    return tuple(buffs)


def rune_distance_to(position: tuple[float, float], team: str = "red") -> float:
    rune = RUNE_POSITIONS.get(team, RUNE_POSITIONS["red"])
    return math.hypot(position[0] - rune[0], position[1] - rune[1])
