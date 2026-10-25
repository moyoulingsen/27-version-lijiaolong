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
        "hp_friend": [200, 250, 200, 200],
        "friendly_ground_positions": [5.0, 5.0, 6.0, 5.0, 7.0, 5.0, 8.0, 5.0],
        "pursuit_costmap_polygon": [[0.0, 15.0], [28.0, 15.0], [28.0, 0.0], [0.0, 0.0]],
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
        route_state = copy.deepcopy(state)
        route_state["time"] = 100
        route_state["hp_enemy"][5] = 0
        route_state["aggressive_patrol_points"] = [
            [11.0, 3.0],
            [15.0, 7.5],
            [11.0, 12.0],
        ]
        stopped = copy.deepcopy(route_state)
        stopped["game_period"] = 0
        for _ in range(5):
            client.publish_state(stopped)
            time.sleep(0.05)
        wait_for(
            client,
            route_state,
            lambda output: near_goal(output, (11.0, 3.0)),
            "Pygame manual patrol route reaches behavior-tree blackboard",
        )

        # Both patrol policies share waypoint_index. Exercise an aggressive
        # route index that is larger than the conservative route, then switch
        # policy without changing either route. The conservative route must
        # wrap the stale index instead of failing to publish a goal.
        unequal_routes = copy.deepcopy(route_state)
        unequal_routes["aggressive_patrol_points"] = [
            [11.0, 3.0],
            [12.0, 3.0],
            [13.0, 3.0],
            [14.0, 3.0],
            [15.0, 3.0],
        ]
        unequal_routes["conservative_patrol_points"] = [
            [5.0, 5.0],
            [6.0, 5.0],
        ]
        stopped = copy.deepcopy(unequal_routes)
        stopped["game_period"] = 0
        for _ in range(5):
            client.publish_state(stopped)
            time.sleep(0.05)
        wait_for(
            client,
            unequal_routes,
            lambda output: near_goal(output, (11.0, 3.0)),
            "unequal patrol routes start from the first aggressive point",
        )
        for current_point, next_point in zip(
            unequal_routes["aggressive_patrol_points"][:-1],
            unequal_routes["aggressive_patrol_points"][1:],
        ):
            unequal_routes["x"], unequal_routes["y"] = current_point
            wait_for(
                client,
                unequal_routes,
                lambda output, expected=tuple(next_point): near_goal(output, expected),
                f"aggressive patrol advances to {tuple(next_point)}",
            )
        unequal_routes["ammo"] = 24
        unequal_routes["pending_ammo"] = 0
        wait_for(
            client,
            unequal_routes,
            lambda output: near_goal(output, (5.0, 5.0))
            and output["serial"]["tripod_mode"] == 1,
            "short conservative route wraps the shared waypoint index",
        )

        dead_state = copy.deepcopy(state)
        dead_state["hp_sentry"] = 0
        dead_state["x"], dead_state["y"] = 10.0, 8.0
        wait_for(
            client,
            dead_state,
            lambda output: output["serial"]["confirm_respawn"] == 1
            and output.get("goal") is None,
            "dead sentry confirms respawn after the wait without moving",
            timeout=7.0,
        )

        revived_state = copy.deepcopy(dead_state)
        revived_state["hp_sentry"] = 400
        wait_for(
            client,
            revived_state,
            lambda output: output["serial"]["confirm_respawn"] == 0
            and near_goal(output, (2.10, 1.30)),
            "revived sentry returns to the supply point",
        )
        revived_state["x"], revived_state["y"] = 2.10, 1.30
        wait_for(
            client,
            revived_state,
            lambda output: near_goal(output, (13.44, 11.14)),
            "respawn flow releases normal policy after reaching supply",
        )

        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and near_goal(output, (13.44, 11.14))
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
            and near_goal(output, (13.44, 11.14)),
            "engineer robot 2 is excluded from target selection",
        )

        # Aerial robot 5 is visible but configured as an invincible target in
        # the XML attack policy. Even at low health and in range it must not
        # preempt the opening outpost.
        state["hp_enemy"][4] = 20
        state["autoaim"]["target"][5] = 1
        state["autoaim"]["target_distance"][5] = 3.0
        state["autoaim"]["target_polar_r"][5] = 3.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6
            and near_goal(output, (13.44, 11.14)),
            "aerial robot 5 is excluded as an invincible target",
        )
        state["hp_enemy"][4] = 100
        state["autoaim"]["target"][5] = 0
        state["autoaim"]["target_distance"][5] = 0.0
        state["autoaim"]["target_polar_r"][5] = 0.0

        # The base uses the same visual candidate path as attackable robots.
        # Its living outpost keeps it invincible; once that protection ends,
        # a visible low-health base is selected and fired upon directly.
        state["hp_enemy"][6] = 40
        state["autoaim"]["target"][7] = 1
        state["autoaim"]["target_distance"][7] = 3.0
        state["autoaim"]["target_polar_r"][7] = 3.0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 6,
            "enemy base remains excluded while its outpost survives",
        )
        state["hp_enemy"][5] = 0
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 7
            and output["serial"]["posture"] == 1
            and output["serial"]["shoot_mode"] == 1,
            "visible vulnerable enemy base uses normal attack selection",
        )
        state["hp_enemy"][5] = 1000
        state["hp_enemy"][6] = 5000
        state["autoaim"]["target"][7] = 0
        state["autoaim"]["target_distance"][7] = 0.0
        state["autoaim"]["target_polar_r"][7] = 0.0

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
            and near_goal(output, (13.44, 11.14)),
            "outpost pursuit resumes after detected robot disappears",
        )

        state["x"], state["y"] = 13.65, 9.86
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (13.44, 11.14))
            and output["serial"]["shoot_mode"] == 0,
            "outpost pursuit does not stop or fire early",
        )

        state["x"], state["y"] = 13.44, 11.14
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
        state["hp_friend"] = [200, 0, 0, 0]
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] != 3
            or output.get("goal") is None,
            "two costmap friendlies block moving-target pursuit",
        )
        state["hp_friend"] = [200, 250, 0, 0]
        wait_for(
            client,
            state,
            lambda output: output["autoaim"]["target"] == 3
            and output["serial"]["posture"] == 3
            and output["serial"]["shoot_mode"] == 0
            and output.get("goal") is not None,
            "detected low-health target preempts in-range outpost and is pursued",
        )
        state["hp_friend"] = [200, 250, 200, 200]

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
            client, state, lambda output: near_goal(output, (2.10, 1.30))
            and output["serial"]["posture"] == 3,
            "low-health recovery",
        )

        state["hp_sentry"] = 250
        wait_for(
            client, state, lambda output: near_goal(output, (2.10, 1.30))
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

        state["economy"] = 399
        state["hp_sentry"] = 299
        stopped_at_boundary = copy.deepcopy(state)
        stopped_at_boundary["game_period"] = 0
        for _ in range(5):
            client.publish_state(stopped_at_boundary)
            time.sleep(0.05)
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (5.0, 5.0))
            and output["serial"]["spin_mode"] == 3
            and output["serial"]["tripod_mode"] == 1,
            "XML 300 HP boundary selects conservative patrol",
        )

        state["hp_sentry"] = 300
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (12.0, 3.0))
            and output["serial"]["spin_mode"] == 1,
            "XML 300 HP boundary keeps aggressive patrol at equality",
        )

        state["hp_sentry"] = 400
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (12.0, 3.0)),
            "restore full health before accumulated-damage checks",
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
            and not near_goal(output, (2.10, 1.30)),
            "sub-50-HP target preempts health recovery",
        )

        # A non-low-health target cannot block recovery.
        state["hp_enemy"][2] = 100
        wait_for(
            client, state, lambda output: near_goal(output, (2.10, 1.30))
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

        # Exactly 25 rounds remains combat-ready; dropping below 25 latches a
        # supply trip. If no pickup is available the sentry may patrol, but a
        # newly available pickup must immediately preempt that patrol.
        state["ammo"] = 25
        state["pending_ammo"] = 100
        wait_for(
            client, state, lambda output: near_goal(output, (12.0, 3.0)),
            "25 rounds does not trigger ammunition recovery",
        )

        state["ammo"] = 24
        state["pending_ammo"] = 0
        wait_for(
            client, state, lambda output: near_goal(output, (5.0, 5.0))
            and output["serial"]["spin_mode"] == 3
            and output["serial"]["tripod_mode"] == 1,
            "low-ammo state uses conservative patrol before pickup is available",
        )

        state["pending_ammo"] = 100
        wait_for(
            client, state, lambda output: near_goal(output, (2.10, 1.30)),
            "newly available ammunition preempts patrol",
        )

        # Simulate Pygame's supply settlement: ammunition transfers at the
        # supply point, but the behavior tree remains there until HP is full.
        state["x"], state["y"] = 2.10, 1.30
        state["ammo"] = 124
        state["pending_ammo"] = 0
        state["hp_sentry"] = 300
        wait_for(
            client,
            state,
            lambda output: output.get("goal") is None
            and output["serial"]["posture"] == 3
            and output["serial"]["shoot_mode"] == 0,
            "ammunition recovery waits at supply until full health",
        )

        state["hp_sentry"] = 400
        wait_for(
            client,
            state,
            lambda output: near_goal(output, (12.0, 3.0)),
            "ammunition recovery releases only after full health",
        )

        state["x"], state["y"] = 4.971, 7.5
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
            lambda output: near_goal(output, (2.10, 1.30))
            and output["serial"]["spin_mode"] == 0,
            "both-low patrol boundary remains below health-recovery priority",
        )
        state["hp_sentry"] = 400

        running = copy.deepcopy(state)
        running["time"] = 10
        running["x"], running["y"] = 12.0, 3.0
        wait_for(client, running, lambda output: client.connected, "playing phase observed")
        finished = copy.deepcopy(running)
        finished["game_period"] = 0
        finished["time"] = 0
        wait_for(
            client, finished, lambda output: near_goal(output, (3.725, 7.975)),
            "return home after match",
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
