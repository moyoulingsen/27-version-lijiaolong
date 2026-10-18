"""Persistent scenario snapshots for the Pygame verification tool."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .core import SentryState
from .task_state import ActiveBuff, TaskScenario


def capture_snapshot(
    name: str,
    task: TaskScenario,
    sentry: SentryState,
    controlled_robot_id: int | None,
    controlled_robot_team: str | None = None,
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
    ):
        if resource_name in task_data:
            task_data[resource_name] = {
                int(target_id): float(value)
                for target_id, value in (task_data.get(resource_name) or {}).items()
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

    controlled = snapshot.get("controlled_robot_id")
    controlled_robot_id = int(controlled) if controlled is not None else None
    return (
        TaskScenario(**task_data),
        SentryState(**sentry_data),
        controlled_robot_id,
    )


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
