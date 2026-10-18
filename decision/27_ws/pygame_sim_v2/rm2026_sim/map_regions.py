"""Editable map-region geometry helpers.

The editor stores points in arena/world coordinates so a scenario remains
stable when the Pygame window is resized or the map is letterboxed differently.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
import math
import json
from pathlib import Path
import shutil

from .field_rules import REGION_TYPES, canonical_region_id


Point = tuple[float, float]
PATROL_ROUTE_KEYS = ("conservative", "aggressive")


def normalize_points(
    points: Sequence[Sequence[float]] | None,
    *,
    width: float = 28.0,
    height: float = 15.0,
) -> tuple[Point, ...]:
    """Return finite, clamped world-coordinate points suitable for drawing."""
    normalized: list[Point] = []
    for point in points or ():
        try:
            if len(point) < 2:
                continue
        except TypeError:
            continue
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        normalized.append((min(max(x, 0.0), width), min(max(y, 0.0), height)))
    return tuple(normalized)


def polygon_area(points: Sequence[Point]) -> float:
    """Return the signed area of a polygon using the shoelace formula."""
    if len(points) < 3:
        return 0.0
    return 0.5 * sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def validate_polygon(points: Sequence[Point]) -> str | None:
    """Return a user-facing validation error, or ``None`` when valid."""
    if len(points) < 3:
        return "至少需要 3 个点"
    if abs(polygon_area(points)) <= 1e-5:
        return "点不能共线"
    return None


def rect_to_polygon(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> tuple[Point, ...]:
    """Convert an axis-aligned field-zone rectangle into a world polygon."""
    return (
        (float(min_x), float(max_y)),
        (float(max_x), float(max_y)),
        (float(max_x), float(min_y)),
        (float(min_x), float(min_y)),
    )


def nearest_segment_index(point: Point, polygon: Sequence[Point]) -> int:
    """Return the edge after which ``point`` should be inserted."""
    if len(polygon) < 2:
        return max(0, len(polygon) - 1)
    best_index = 0
    best_distance = float("inf")
    px, py = point
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared <= 1e-12:
            projection = start
        else:
            ratio = ((px - start[0]) * dx + (py - start[1]) * dy) / length_squared
            ratio = min(1.0, max(0.0, ratio))
            projection = (start[0] + ratio * dx, start[1] + ratio * dy)
        distance = math.hypot(px - projection[0], py - projection[1])
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index


def geometry_payload(
    zone_overrides: dict[str, Sequence[Point]],
    custom_polygons: Sequence[dict],
    patrol_routes: dict[str, Sequence[Point]] | None = None,
) -> dict:
    """Build the JSON-safe map-geometry portion of a scenario snapshot."""
    payload = {
        "zone_overrides": {
            canonical_region_id(name): [[float(x), float(y)] for x, y in points]
            for name, points in zone_overrides.items()
        },
        "custom_polygons": [
            {
                "id": str(item.get("id", "")),
                "kind": canonical_region_id(item.get("kind") or REGION_TYPES[0][0]),
                "name": str(item.get("name", "自定义区域")),
                "points": [
                    [float(x), float(y)]
                    for x, y in normalize_points(item.get("points"))
                ],
                "color": [int(value) for value in item.get("color", (230, 160, 70))[:3]],
                "visible": bool(item.get("visible", False)),
            }
            for item in custom_polygons
            if (
                isinstance(item, dict)
                and validate_polygon(normalize_points(item.get("points"))) is None
            )
        ],
    }
    if patrol_routes is not None:
        payload["patrol_routes"] = {
            key: [[float(x), float(y)] for x, y in normalize_points(patrol_routes.get(key))]
            for key in PATROL_ROUTE_KEYS
            if len(normalize_points(patrol_routes.get(key))) >= 2
        }
    return payload


def restore_geometry_payload(payload: dict | None) -> tuple[dict[str, tuple[Point, ...]], list[dict]]:
    """Normalize persisted geometry, tolerating old or malformed snapshots."""
    payload = payload if isinstance(payload, dict) else {}
    overrides: dict[str, tuple[Point, ...]] = {}
    raw_overrides = payload.get("zone_overrides")
    if isinstance(raw_overrides, dict):
        allowed = {identifier for identifier, _ in REGION_TYPES}
        for name, points in raw_overrides.items():
            name = canonical_region_id(name)
            if name in allowed:
                overrides[name] = normalize_points(points)

    custom: list[dict] = []
    raw_custom = payload.get("custom_polygons")
    if isinstance(raw_custom, list):
        for index, item in enumerate(raw_custom, start=1):
            if not isinstance(item, dict):
                continue
            points = normalize_points(item.get("points"))
            if validate_polygon(points) is not None:
                continue
            identifier = str(item.get("id") or f"custom_{index}")
            color = item.get("color", (230, 160, 70))
            if not isinstance(color, (list, tuple)) or len(color) < 3:
                color = (230, 160, 70)
            kind = canonical_region_id(item.get("kind") or REGION_TYPES[0][0])
            if kind not in {identifier for identifier, _ in REGION_TYPES}:
                kind = REGION_TYPES[0][0]
            custom.append({
                "id": identifier,
                "kind": kind,
                "name": str(item.get("name") or f"自定义区域 {index}"),
                "points": [[x, y] for x, y in points],
                "color": [max(0, min(255, int(value))) for value in color[:3]],
                "visible": bool(item.get("visible", False)),
            })
    return overrides, custom


def load_geometry_file(path: Path) -> tuple[dict[str, tuple[Point, ...]], list[dict]]:
    """Load the independent, permanent map annotation configuration."""
    if not path.is_file():
        return {}, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, []
    return restore_geometry_payload(payload)


def restore_patrol_routes(
    payload: dict | None,
    defaults: dict[str, Sequence[Point]],
) -> dict[str, tuple[Point, ...]]:
    """Restore two ordered patrol loops, falling back route-by-route."""
    payload = payload if isinstance(payload, dict) else {}
    raw_routes = payload.get("patrol_routes")
    raw_routes = raw_routes if isinstance(raw_routes, dict) else {}
    routes: dict[str, tuple[Point, ...]] = {}
    for key in PATROL_ROUTE_KEYS:
        points = normalize_points(raw_routes.get(key))
        if len(points) < 2:
            points = normalize_points(defaults.get(key))
        routes[key] = points
    return routes


def load_patrol_routes_file(
    path: Path,
    defaults: dict[str, Sequence[Point]],
) -> dict[str, tuple[Point, ...]]:
    """Load ordered patrol loops from the shared permanent map file."""
    if not path.is_file():
        return restore_patrol_routes({}, defaults)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    return restore_patrol_routes(payload, defaults)


def save_geometry_file(
    path: Path,
    zone_overrides: dict[str, Sequence[Point]],
    custom_polygons: Sequence[dict],
    *,
    patrol_routes: dict[str, Sequence[Point]] | None = None,
    backup_limit: int = 30,
) -> None:
    """Atomically save map annotations and retain rotating write backups."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        geometry_payload(zone_overrides, custom_polygons, patrol_routes),
        ensure_ascii=False,
        indent=2,
    )
    try:
        current = path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeDecodeError):
        current = None
    if current == serialized:
        return

    if path.is_file():
        backup_directory = path.parent / f"{path.stem}_backups"
        backup_directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = backup_directory / f"{path.stem}.{stamp}{path.suffix}"
        shutil.copy2(path, backup_path)
        backups = sorted(
            backup_directory.glob(f"{path.stem}.*{path.suffix}"),
            key=lambda candidate: candidate.stat().st_mtime_ns,
            reverse=True,
        )
        for expired in backups[max(1, int(backup_limit)):]:
            expired.unlink(missing_ok=True)

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)
