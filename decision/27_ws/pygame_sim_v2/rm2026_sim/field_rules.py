"""Map annotation types and the independent energy-rune rule helpers.

The field annotations are deliberately geometry-only for now.  Their future
effects are represented by empty ``FieldZone`` shells and are not applied by
the task simulator until the user supplies the final polygons and attributes.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .field_geometry import RUNE_POSITIONS


# These are the only area annotation slots exposed by the map editor.  The six
# gain-point families that exist on both sides of the field have explicit red
# and blue slots.  The two tunnel entries remain separate because the source
# figure labels the two tunnel gain points independently.
REGION_TYPES = (
    ("region_01_supply_red", "补给区增益点（红方）"),
    ("region_01_supply_blue", "补给区增益点（蓝方）"),
    ("region_02_road", "地形跨越增益点（公路）"),
    ("region_03_tunnel", "地形跨越增益点（隧道）"),
    ("region_04_fly_slope", "地形跨越增益点（飞坡）"),
    ("region_05_trapezoid_highland_red", "梯形高地增益点（红方）"),
    ("region_05_trapezoid_highland_blue", "梯形高地增益点（蓝方）"),
    ("region_06_base_red", "基地增益点（红方）"),
    ("region_06_base_blue", "基地增益点（蓝方）"),
    ("region_07_fort_red", "堡垒增益点（红方）"),
    ("region_07_fort_blue", "堡垒增益点（蓝方）"),
    ("region_08_highland", "地形跨越增益点（高地）"),
    ("region_09_outpost_red", "前哨站增益点（红方）"),
    ("region_09_outpost_blue", "前哨站增益点（蓝方）"),
    ("region_10_tunnel", "地形跨越增益点（隧道）"),
    ("region_11_central_highland", "中央高地增益点兼地形跨越增益点（高地）"),
    ("region_12_assembly_red", "装配区增益点（红方）"),
    ("region_12_assembly_blue", "装配区增益点（蓝方）"),
)

# Snapshots created before side-specific slots were introduced used one id for
# each pair.  Treat those ids as the red-side slot when loading old data; new
# saves only emit the explicit ids above.
REGION_ID_ALIASES = {
    "region_01_supply": "region_01_supply_red",
    "region_05_trapezoid_highland": "region_05_trapezoid_highland_red",
    "region_06_base": "region_06_base_red",
    "region_07_fort": "region_07_fort_red",
    "region_09_outpost": "region_09_outpost_red",
    "region_12_assembly": "region_12_assembly_red",
}


def canonical_region_id(identifier: object) -> str:
    """Return the current slot id for a persisted or UI region identifier."""
    value = str(identifier)
    return REGION_ID_ALIASES.get(value, value)


@dataclass(frozen=True)
class FieldZone:
    """Geometry-only placeholder for one numbered annotation slot."""

    name: str
    kind: str
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0
    team: str | None = None
    buffs: tuple[tuple[str, float, float], ...] = ()
    mode: str = "annotation"
    cooldown: float = 0.0
    color: tuple[int, int, int] = (120, 180, 220)
    label: str = ""
    polygon: tuple[tuple[float, float], ...] = ()

    def contains(self, x: float, y: float) -> bool:
        if len(self.polygon) < 3:
            return False
        if not (self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y):
            return False
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


REGION_COLORS = (
    (45, 174, 99),
    (45, 130, 220),
    (176, 132, 82),
    (110, 130, 170),
    (120, 190, 160),
    (222, 148, 62),
    (222, 148, 62),
    (74, 145, 222),
    (74, 145, 222),
    (210, 180, 70),
    (210, 180, 70),
    (190, 120, 70),
    (205, 75, 82),
    (57, 124, 210),
    (110, 130, 170),
    (160, 110, 220),
    (150, 150, 160),
    (150, 150, 160),
)


REGION_DEFINITIONS: tuple[FieldZone, ...] = tuple(
    FieldZone(
        name=identifier,
        kind=identifier,
        color=REGION_COLORS[index],
        label=label,
        team=(
            "red" if identifier.endswith("_red")
            else "blue" if identifier.endswith("_blue")
            else None
        ),
    )
    for index, (identifier, label) in enumerate(REGION_TYPES)
)

# Kept as an empty compatibility collection: no area currently has a rule
# effect or a default geometry.  The task simulator must not infer regions
# from old hard-coded field rectangles.
FIELD_ZONES: tuple[FieldZone, ...] = ()


def zones_for_team(team: str = "red") -> tuple[FieldZone, ...]:
    """Return active rule zones; annotation slots are intentionally inactive."""
    return ()


# Rulebook energy-rune helpers are independent from map-area annotations.
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


# Legacy crossing constants are intentionally empty.  They remain importable
# for old integrations but no terrain crossing effect is evaluated.
ROAD_CROSSING_CARDS: dict[str, tuple] = {"red": (), "blue": ()}
ROAD_CARD_HALF_EXTENT = 0.0
ROAD_CROSSING_WINDOW = 0.0
