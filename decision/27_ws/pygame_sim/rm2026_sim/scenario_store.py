"""Persistent scenario snapshots for the Pygame verification tool."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .core import SentryState
from .task_state import TaskScenario


def capture_snapshot(
    name: str,
    task: TaskScenario,
    sentry: SentryState,
    controlled_robot_id: int | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "task": asdict(task),
        "sentry": asdict(sentry),
        "controlled_robot_id": controlled_robot_id,
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
