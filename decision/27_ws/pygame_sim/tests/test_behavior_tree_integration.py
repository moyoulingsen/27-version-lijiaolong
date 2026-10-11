#!/usr/bin/env python3
"""End-to-end checks for Pygame UDP -> ROS 2 -> BehaviorTree.CPP."""

from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rm2026_sim.ros_bridge import BehaviorTreeBridgeClient


def base_state() -> dict:
    return {
        "game_period": 2,
        "time": 420,
        "hp_sentry": 400,
        "defence_buff": 60,
        "color": 0,
        "ammo": 120,
        "hp_outpost": 1000,
        "hp_base": 5000,
        "hp_enemy": [200, 250, 200, 200, 100, 1000, 5000, 400],
        "radar_data": [5.0, 7.5, 8.0, 7.5, 9.0, 9.0, 12.0, 5.0, 15.0, 10.0, 25.0, 8.0],
        "pending_ammo": 0,
        "x": 4.971,
        "y": 7.5,
        "yaw": 0.0,
        "autoaim": {
            "target": [0] * 9,
            "target_distance": [0.0] * 9,
            "target_polar_r": [0.0] * 9,
            "target_polar_angle": [0.0] * 9,
        },
        "aggressive_patrol": False,
    }


def near_goal(output: dict, expected: tuple[float, float], tolerance: float = 0.3) -> bool:
    goal = output.get("goal")
    return (
        isinstance(goal, list)
        and len(goal) == 2
        and math.hypot(goal[0] - expected[0], goal[1] - expected[1]) <= tolerance
    )


def wait_for(client, state, predicate, label, timeout=5.0):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        client.publish_state(state)
        latest = client.latest_output()
        if latest is not None and predicate(latest):
            print(f"PASS: {label}: {latest}")
            return latest
        time.sleep(0.05)
    raise AssertionError(f"{label} timed out; latest={latest}")


def main() -> None:
    client = BehaviorTreeBridgeClient(timeout=2.0)
    try:
        state = base_state()
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and near_goal(output, (16.0, 11.0)),
            "enemy outpost pursuit",
        )

        state["x"], state["y"] = 13.65, 9.86
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (16.0, 11.0))
            and output["serial"]["shoot_mode"] == 0,
            "outpost pursuit does not stop or fire early",
        )

        state["x"], state["y"] = 16.0, 11.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and output["serial"]["shoot_mode"] == 0,
            "at attack point without autoaim does not fire",
        )

        state["autoaim"]["target"][6] = 1
        state["autoaim"]["target_distance"][6] = 5.3
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and output["serial"]["shoot_mode"] == 1,
            "attack and fire at outpost",
        )

        state["hp_enemy"][5] = 0
        state["autoaim"]["target"][6] = 0
        state["autoaim"]["target_distance"][6] = 0.0
        state["hp_sentry"] = 150
        wait_for(
            client, state, lambda output: near_goal(output, (2.0, 1.0)),
            "low-health recovery",
        )

        state["hp_sentry"] = 400
        state["x"], state["y"] = 4.971, 7.5
        state["aggressive_patrol"] = False
        wait_for(
            client, state, lambda output: near_goal(output, (5.0, 5.0)),
            "conservative patrol",
        )

        state["aggressive_patrol"] = True
        wait_for(
            client, state, lambda output: near_goal(output, (12.0, 3.0)),
            "aggressive patrol",
        )

        # Reproduce the UI sequence: clear carried ammunition first, allow the
        # no-ammo patrol to start, then add ammunition waiting at the supply.
        # The behavior tree must preempt patrol as soon as pickup becomes
        # available instead of staying latched on the RUNNING patrol child.
        state["ammo"] = 0
        state["pending_ammo"] = 0
        wait_for(
            client, state, lambda output: near_goal(output, (12.0, 3.0)),
            "no-ammo patrol before pickup becomes available",
        )

        state["pending_ammo"] = 100
        wait_for(
            client, state, lambda output: near_goal(output, (2.0, 1.0)),
            "newly available ammunition preempts patrol",
        )

        state["ammo"] = 120
        state["pending_ammo"] = 0
        state["hp_outpost"] = 0
        wait_for(
            client,
            state,
            lambda output: output["serial"]["spin_mode"] > 0,
            "small gyro after own outpost destruction",
        )

        running = copy.deepcopy(state)
        running["time"] = 10
        running["x"], running["y"] = 12.0, 3.0
        wait_for(client, running, lambda output: client.connected, "playing phase observed")
        finished = copy.deepcopy(running)
        finished["game_period"] = 0
        finished["time"] = 0
        wait_for(
            client, finished, lambda output: near_goal(output, (4.971, 7.5)),
            "return home after match",
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
