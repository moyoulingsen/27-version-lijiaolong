#!/usr/bin/env python3
"""End-to-end checks for Pygame UDP -> ROS 2 -> BehaviorTree.CPP."""

from __future__ import annotations

import copy
import math
import os
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
        "economy": 500,
        "x": 4.971,
        "y": 7.5,
        "yaw": 0.0,
        "camera_yaw": 0.0,
        "autoaim": {
            "target": [0] * 9,
            "target_distance": [0.0] * 9,
            "target_polar_r": [0.0] * 9,
            "target_polar_angle": [0.0] * 9,
        },
        "aggressive_patrol": False,
        "conservative_patrol_points": [[5.0, 5.0], [9.0, 5.0], [9.0, 9.0]],
        "aggressive_patrol_points": [[12.0, 3.0], [14.0, 7.5], [12.3, 11.7]],
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
    client = BehaviorTreeBridgeClient(
        port=int(os.environ.get("RM2026_SIM_PORT", "39001")),
        timeout=2.0,
    )
    try:
        state = base_state()
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and near_goal(output, (17.0, 10.0))
            and output["serial"]["spin_mode"] == 1
            and output["serial"]["tripod_mode"] == 1,
            "enemy outpost pursuit uses low-speed gyro and scans with gimbal",
        )

        # Engineer robot 2 is not an attack candidate. Even when visible, the
        # opening outpost remains selected.
        state["autoaim"]["target"][2] = 1
        state["autoaim"]["target_distance"][2] = 3.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and near_goal(output, (17.0, 10.0)),
            "engineer robot 2 is excluded from target selection",
        )

        # A visual target must be projected from camera-relative polar data.
        # Deliberately publish a contradictory radar coordinate to prove that
        # visible-target pursuit does not consume the global radar/world value.
        state["camera_yaw"] = math.pi / 2.0
        state["radar_data"][4:6] = [1.0, 14.0]
        state["autoaim"]["target"][3] = 1
        state["autoaim"]["target_distance"][3] = 5.0
        state["autoaim"]["target_polar_r"][3] = 5.0
        state["autoaim"]["target_polar_angle"][3] = -math.pi / 2.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 3
            and output["serial"]["posture"] == 3
            and output["serial"]["shoot_mode"] == 0
            and near_goal(output, (7.171, 7.5)),
            "camera-relative target converts to map without radar world coordinate",
        )

        state["autoaim"]["target_distance"][3] = 3.0
        state["autoaim"]["target_polar_r"][3] = 3.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 3
            and output["serial"]["posture"] == 1,
            "detected non-engineer robot preempts opening outpost",
        )
        state["autoaim"]["target"][2] = 0
        state["autoaim"]["target_distance"][2] = 0.0
        state["autoaim"]["target"][3] = 0
        state["autoaim"]["target_distance"][3] = 0.0
        state["autoaim"]["target_polar_r"][3] = 0.0
        state["autoaim"]["target_polar_angle"][3] = 0.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and near_goal(output, (17.0, 10.0)),
            "outpost pursuit resumes after detected robot disappears",
        )

        state["x"], state["y"] = 13.65, 9.86
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (17.0, 10.0))
            and output["serial"]["shoot_mode"] == 0,
            "outpost pursuit does not stop or fire early",
        )

        state["x"], state["y"] = 17.0, 10.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and output["serial"]["shoot_mode"] == 0
            and output["serial"]["spin_mode"] == 0,
            "at attack point without autoaim does not fire",
        )

        state["autoaim"]["target"][6] = 1
        state["autoaim"]["target_distance"][6] = 3.9
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and output["serial"]["shoot_mode"] == 1
            and output["serial"]["spin_mode"] == 0
            and output["serial"]["posture"] == 1,
            "attack and fire at outpost",
        )

        # A detected robot below 50 HP preempts the in-range outpost even
        # while it remains outside the 4 m attack range.
        state["hp_enemy"][2] = 40
        state["autoaim"]["target"][3] = 1
        state["autoaim"]["target_distance"][3] = 5.0
        state["autoaim"]["target_polar_r"][3] = 5.0
        state["autoaim"]["target_polar_angle"][3] = 0.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 3
            and output["serial"]["posture"] == 3
            and output["serial"]["shoot_mode"] == 0
            and output.get("goal") is not None,
            "detected low-health target preempts in-range outpost and is pursued",
        )

        state["autoaim"]["target_distance"][3] = 3.0
        state["autoaim"]["target_polar_r"][3] = 3.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 3
            and output["serial"]["posture"] == 1
            and output["serial"]["shoot_mode"] == 1,
            "pursued low-health target is attacked after entering 4m",
        )
        state["hp_enemy"][2] = 200
        state["autoaim"]["target"][3] = 0
        state["autoaim"]["target_distance"][3] = 0.0
        state["autoaim"]["target_polar_r"][3] = 0.0
        state["autoaim"]["target_polar_angle"][3] = 0.0

        state["hp_enemy"][5] = 0
        state["autoaim"]["target"][6] = 0
        state["autoaim"]["target_distance"][6] = 0.0
        state["hp_sentry"] = 150
        wait_for(
            client, state, lambda output: near_goal(output, (2.0, 1.0))
            and output["serial"]["posture"] == 3,
            "low-health recovery",
        )

        state["hp_sentry"] = 250
        wait_for(
            client, state, lambda output: near_goal(output, (2.0, 1.0))
            and output["serial"]["posture"] == 3,
            "health recovery remains active above trigger threshold",
        )

        state["hp_sentry"] = 400
        state["x"], state["y"] = 4.971, 7.5
        state["economy"] = 399
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (12.0, 3.0))
            and output["serial"]["spin_mode"] == 1
            and output["serial"]["tripod_mode"] == 1,
            "low economy alone keeps aggressive patrol",
        )

        state["economy"] = 400
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (12.0, 3.0))
            and output["serial"]["spin_mode"] == 1
            and output["serial"]["tripod_mode"] == 1,
            "economy boundary keeps aggressive patrol",
        )

        # One 25 HP hit remains below the accumulated significant-damage threshold.
        state["hp_sentry"] = 375
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (12.0, 3.0))
            and output["serial"]["spin_mode"] == 1,
            "one 25 HP hit does not trigger evasion",
        )

        # A second 25 HP hit within one second raises the burst total to 50 HP.
        state["hp_sentry"] = 350
        wait_for(
            client,
            state,
            lambda output: output["serial"]["posture"] == 2
            and output["serial"]["spin_mode"] == 3
            and output["serial"]["tripod_mode"] == 1
            and output.get("goal") is not None
            and not near_goal(output, (12.0, 3.0)),
            "two rapid 25 HP hits start accumulated-damage evasion",
        )

        # A detected stronger robot does not cancel evasion.
        state["hp_enemy"][2] = 400
        state["autoaim"]["target"][3] = 1
        state["autoaim"]["target_distance"][3] = 3.0
        wait_for(
            client,
            state,
            lambda output: output["serial"]["posture"] == 2
            and output["serial"]["spin_mode"] == 3
            and output["serial"]["shoot_mode"] == 0,
            "stronger detected target keeps evasion active",
        )

        # Once the observed robot is weaker than the sentry, normal attack owns it.
        state["hp_enemy"][2] = 300
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 3
            and output["serial"]["posture"] == 1,
            "weaker detected target preempts evasion and is attacked",
        )
        state["autoaim"]["target"][3] = 0
        state["autoaim"]["target_distance"][3] = 0.0

        # A detected target below 50 HP still preempts recovery, even when the
        # sentry itself is below the health-recovery threshold.
        state["hp_sentry"] = 150
        state["hp_enemy"][2] = 40
        state["autoaim"]["target"][3] = 1
        state["autoaim"]["target_distance"][3] = 3.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 3
            and output["serial"]["posture"] == 1
            and output["serial"]["shoot_mode"] == 1
            and not near_goal(output, (2.0, 1.0)),
            "sub-50-HP target preempts health recovery",
        )

        # A non-low-health target cannot block recovery.
        state["hp_enemy"][2] = 100
        wait_for(
            client, state, lambda output: near_goal(output, (2.0, 1.0))
            and output["serial"]["posture"] == 3,
            "non-low-health target does not block recovery",
        )
        state["autoaim"]["target"][3] = 0
        state["autoaim"]["target_distance"][3] = 0.0
        state["hp_sentry"] = 400
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (12.0, 3.0)),
            "original aggressive patrol resumes after recovery and evade timeout",
            timeout=7.0,
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
            lambda output: output["serial"]["spin_mode"] == 1,
            "outpost destruction does not override aggressive patrol mode",
        )

        state["economy"] = 399
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (12.0, 3.0))
            and output["serial"]["spin_mode"] == 1,
            "low economy alone remains aggressive after outpost destruction",
        )

        state["hp_sentry"] = 149
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (2.0, 1.0))
            and output["serial"]["spin_mode"] == 0,
            "both-low patrol boundary remains below health-recovery priority",
        )
        state["hp_sentry"] = 400

        state["aggressive_patrol_points"] = [
            [11.0, 3.0],
            [15.0, 7.5],
            [11.0, 12.0],
        ]
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (11.0, 3.0)),
            "Pygame manual patrol route reaches behavior-tree blackboard",
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
