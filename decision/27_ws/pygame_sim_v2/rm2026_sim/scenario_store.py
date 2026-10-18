"""Persistent scenario snapshots for the Pygame verification tool."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .core import SentryState
from .field_rules import REGION_TYPES, canonical_region_id
from .task_state import ActiveBuff, TaskScenario


def capture_snapshot(
    name: str,
    task: TaskScenario,
    sentry: SentryState,
    controlled_robot_id: int | None,
    controlled_robot_team: str | None = None,
    map_geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_data = asdict(task)
    task_data["zone_inside"] = sorted(task.zone_inside)
    task_data["assembly_completed"] = sorted(task.assembly_completed)
    return {
        "name": name,
        "task": task_data,
        "sentry": asdict(sentry),
        "controlled_robot_id": controlled_robot_id,
        "controlled_robot_team": controlled_robot_team,
        "map_geometry": map_geometry or {},
    }


def restore_snapshot(
    snapshot: dict[str, Any],
) -> tuple[TaskScenario, SentryState, int | None]:
    task_data = dict(snapshot.get("task") or {})
    sentry_data = dict(snapshot.get("sentry") or {})
    if not task_data or not sentry_data:
        raise ValueError("snapshot is missing task or sentry state")
    if "robot_positions" in task_data:
        task_data["robot_positions"] = {
            int(target_id): [float(position[0]), float(position[1])]
            for target_id, position in (
                task_data.get("robot_positions") or {}
            ).items()
        }
    if "robot_hp" in task_data:
        task_data["robot_hp"] = {
            int(target_id): float(health)
            for target_id, health in (task_data.get("robot_hp") or {}).items()
        }
    if "robot_ammo" in task_data:
        task_data["robot_ammo"] = {
            int(target_id): int(ammo)
            for target_id, ammo in (task_data.get("robot_ammo") or {}).items()
        }
    if "own_robot_positions" in task_data:
        task_data["own_robot_positions"] = {
            int(target_id): [float(position[0]), float(position[1])]
            for target_id, position in (
                task_data.get("own_robot_positions") or {}
            ).items()
        }
    if "own_robot_hp" in task_data:
        task_data["own_robot_hp"] = {
            int(target_id): float(health)
            for target_id, health in (task_data.get("own_robot_hp") or {}).items()
        }
    if "own_robot_ammo" in task_data:
        task_data["own_robot_ammo"] = {
            int(target_id): int(ammo)
            for target_id, ammo in (task_data.get("own_robot_ammo") or {}).items()
        }
    for resource_name in (
        "robot_heat",
        "own_robot_heat",
        "robot_power",
        "own_robot_power",
        "robot_invincible_remaining",
        "own_robot_invincible_remaining",
        "robot_out_of_combat_seconds",
        "own_robot_out_of_combat_seconds",
        "robot_revive_progress",
        "own_robot_revive_progress",
        "robot_revive_required",
        "own_robot_revive_required",
    ):
        if resource_name in task_data:
            task_data[resource_name] = {
                int(target_id): float(value)
                for target_id, value in (task_data.get(resource_name) or {}).items()
            }
    for flag_name in (
        "robot_weak_state",
        "own_robot_weak_state",
        "robot_heat_locked",
        "own_robot_heat_locked",
        "robot_heat_permanent_lock",
        "own_robot_heat_permanent_lock",
    ):
        if flag_name in task_data:
            task_data[flag_name] = {
                int(target_id): bool(value)
                for target_id, value in (task_data.get(flag_name) or {}).items()
            }
    for source_name in (
        "robot_revive_invincibility_source",
        "own_robot_revive_invincibility_source",
    ):
        if source_name in task_data:
            task_data[source_name] = {
                int(target_id): str(value)
                for target_id, value in (task_data.get(source_name) or {}).items()
            }
    for timer_name in ("robot_death_elapsed", "own_robot_death_elapsed"):
        if timer_name in task_data:
            task_data[timer_name] = {
                int(target_id): (None if value is None else float(value))
                for target_id, value in (task_data.get(timer_name) or {}).items()
            }
    for shot_name in (
        "robot_shots_17mm",
        "robot_shots_42mm",
        "own_robot_shots_17mm",
        "own_robot_shots_42mm",
    ):
        if shot_name in task_data:
            task_data[shot_name] = {
                int(target_id): (None if value is None else int(value))
                for target_id, value in (task_data.get(shot_name) or {}).items()
            }
    for level_name in ("robot_level", "own_robot_level"):
        if level_name in task_data:
            task_data[level_name] = {
                int(target_id): int(value)
                for target_id, value in (task_data.get(level_name) or {}).items()
            }
    for exp_name in (
        "robot_exp",
        "own_robot_exp",
        "posture_time",
        "reinforced_time",
    ):
        if exp_name in task_data:
            task_data[exp_name] = {
                int(target_id): float(value)
                for target_id, value in (task_data.get(exp_name) or {}).items()
            }
    if "zone_inside" in task_data:
        task_data["zone_inside"] = set(task_data.get("zone_inside") or [])
    for occupant_name in (
        "base_gain_occupants",
        "trapezoid_gain_occupants",
        "central_highland_occupants",
        "outpost_gain_occupants",
        "assembly_gain_occupants",
        "supply_gain_occupants",
        "fort_own_occupants",
        "fort_enemy_occupants",
    ):
        if occupant_name not in task_data:
            continue
        restored_occupants = {
            team: [int(target_id) for target_id in (target_ids or [])]
            for team, target_ids in (task_data.get(occupant_name) or {}).items()
            if team in ("red", "blue")
        }
        task_data[occupant_name] = {
            "red": restored_occupants.get("red", []),
            "blue": restored_occupants.get("blue", []),
        }
    if "central_highland_owners" in task_data:
        task_data["central_highland_owners"] = {
            str(zone_id): str(owner)
            for zone_id, owner in (task_data.get("central_highland_owners") or {}).items()
            if owner in ("red", "blue")
        }
    for grace_name in ("central_highland_exit_grace", "gain_exit_grace"):
        if grace_name not in task_data:
            continue
        restored_grace: dict[str, dict[str, dict[int, float]]] = {}
        for zone_id, teams in (task_data.get(grace_name) or {}).items():
            if not isinstance(teams, dict):
                continue
            restored_grace[str(zone_id)] = {
                team: {
                    int(target_id): max(0.0, float(value))
                    for target_id, value in (teams.get(team) or {}).items()
                }
                for team in ("red", "blue")
            }
        task_data[grace_name] = restored_grace
    if "outpost_rebuild_progress" in task_data:
        values = task_data.get("outpost_rebuild_progress") or {}
        task_data["outpost_rebuild_progress"] = {
            team: {
                target_id: max(
                    0.0,
                    float(
                        (values.get(team) or {}).get(
                            str(target_id),
                            (values.get(team) or {}).get(target_id, 0.0),
                        )
                    ),
                )
                for target_id in (1, 2, 3, 4, 8)
            }
            for team in ("red", "blue")
        }
    if "base_hp_damage_taken" in task_data:
        values = task_data.get("base_hp_damage_taken") or {}
        task_data["base_hp_damage_taken"] = {
            team: max(0.0, float(values.get(team, 0.0)))
            for team in ("red", "blue")
        }
    if "outpost_rebuild_chances" in task_data:
        values = task_data.get("outpost_rebuild_chances") or {}
        task_data["outpost_rebuild_chances"] = {
            team: max(0, int(values.get(team, 0)))
            for team in ("red", "blue")
        }
    for fort_value_name in ("fort_reserve_ammo", "fort_reserve_capacity"):
        if fort_value_name in task_data:
            values = task_data.get(fort_value_name) or {}
            task_data[fort_value_name] = {
                "red": max(0, int(values.get("red", 0))),
                "blue": max(0, int(values.get("blue", 0))),
            }
    for fort_timer_name in (
        "fort_enemy_capture_elapsed",
        "fort_enemy_capture_grace",
    ):
        if fort_timer_name in task_data:
            timers = task_data.get(fort_timer_name) or {}
            task_data[fort_timer_name] = {
                team: {
                    int(target_id): max(0.0, float(value))
                    for target_id, value in (timers.get(team) or {}).items()
                }
                for team in ("red", "blue")
            }
    for terrain_value_name in (
        "terrain_sequence_elapsed",
        "terrain_standard_defence",
        "terrain_standard_remaining",
        "terrain_tunnel_defence_remaining",
        "terrain_tunnel_cooling_remaining",
        "terrain_road_cooldown",
    ):
        if terrain_value_name in task_data:
            values = task_data.get(terrain_value_name) or {}
            task_data[terrain_value_name] = {
                team: {
                    int(target_id): max(0.0, float(value))
                    for target_id, value in (values.get(team) or {}).items()
                }
                for team in ("red", "blue")
            }
    for terrain_list_name in (
        "terrain_sequence_cards",
        "terrain_cards_inside",
    ):
        if terrain_list_name in task_data:
            values = task_data.get(terrain_list_name) or {}
            task_data[terrain_list_name] = {
                team: {
                    int(target_id): [str(card_id) for card_id in (card_ids or [])]
                    for target_id, card_ids in (values.get(team) or {}).items()
                }
                for team in ("red", "blue")
            }
    if "terrain_last_positions" in task_data:
        values = task_data.get("terrain_last_positions") or {}
        task_data["terrain_last_positions"] = {
            team: {
                int(target_id): [float(position[0]), float(position[1])]
                for target_id, position in (values.get(team) or {}).items()
                if isinstance(position, (list, tuple)) and len(position) >= 2
            }
            for team in ("red", "blue")
        }
    if "assembly_gain_elapsed" in task_data:
        restored_elapsed = {
            team: max(0.0, float(value))
            for team, value in (task_data.get("assembly_gain_elapsed") or {}).items()
            if team in ("red", "blue")
        }
        task_data["assembly_gain_elapsed"] = {
            "red": restored_elapsed.get("red", 0.0),
            "blue": restored_elapsed.get("blue", 0.0),
        }
    if "assembly_completed" in task_data:
        task_data["assembly_completed"] = set(
            int(value) for value in (task_data.get("assembly_completed") or [])
        )
    if "radar_marks" in task_data:
        task_data["radar_marks"] = {
            int(target_id): float(value)
            for target_id, value in (task_data.get("radar_marks") or {}).items()
        }
    if "active_buffs" in task_data:
        task_data["active_buffs"] = [
            ActiveBuff(**item) for item in (task_data.get("active_buffs") or [])
        ]
    if task_data.get("dodge_goal") is not None:
        task_data["dodge_goal"] = tuple(task_data["dodge_goal"])
    if "field_zone_overrides" in task_data:
        allowed_regions = {identifier for identifier, _ in REGION_TYPES}
        task_data["field_zone_overrides"] = {
            canonical_region_id(name): [
                [float(point[0]), float(point[1])]
                for point in (points or [])
                if isinstance(point, (list, tuple)) and len(point) >= 2
            ]
            for name, points in (task_data.get("field_zone_overrides") or {}).items()
            if canonical_region_id(name) in allowed_regions
            and isinstance(points, (list, tuple))
        }

    controlled = snapshot.get("controlled_robot_id")
    controlled_robot_id = int(controlled) if controlled is not None else None
    task = TaskScenario(**task_data)
    task.set_central_highland_zones(task.central_highland_zones)
    task.set_terrain_crossing_cards(task.terrain_crossing_cards)
    return task, SentryState(**sentry_data), controlled_robot_id


def delete_snapshot(
    snapshots: list[dict[str, Any]], index: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not 0 <= index < len(snapshots):
        raise IndexError("snapshot index out of range")
    remaining = list(snapshots)
    removed = remaining.pop(index)
    return remaining, removed


class ScenarioStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def save(self, snapshots: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(snapshots, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
