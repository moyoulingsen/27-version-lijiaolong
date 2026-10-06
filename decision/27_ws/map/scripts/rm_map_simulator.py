#!/usr/bin/python3
"""Referee/autoaim scenario driver and validator for the Gazebo/Nav2 simulation."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)

from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray

from decision_process.msg import (
    AutoaimToDecision,
    DecisionToAutoaim,
    DesicionSendData,
    ReceiveData,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arena_data import load_snapshot  # noqa: E402


STARTS = {
    "return_home": (14.0, 4.0, 0.0),
    "attack_outpost": (4.971, 7.5, 0.0),
    "no_ammo": (10.0, 4.0, 0.0),
    "dodge": (4.0, 5.0, 0.0),
}
VALID_SCENARIOS = tuple(STARTS)


def planar_distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def yaw_from_quaternion(orientation):
    sin_yaw = 2.0 * (orientation.w * orientation.z + orientation.x * orientation.y)
    cos_yaw = 1.0 - 2.0 * (orientation.y ** 2 + orientation.z ** 2)
    return math.atan2(sin_yaw, cos_yaw)


class ScenarioDriver(Node):
    def __init__(self):
        super().__init__("rm_decision_scenario")
        self.declare_parameter("scenario", "attack_outpost")
        self.declare_parameter("dataset_path", "")
        self.declare_parameter("game_id", 0)
        self.declare_parameter("exit_on_result", False)
        self.scenario = self.get_parameter("scenario").value
        if self.scenario not in VALID_SCENARIOS:
            raise ValueError(f"scenario must be one of {VALID_SCENARIOS}, got {self.scenario}")
        dataset_path = self.get_parameter("dataset_path").value
        self.snapshot = load_snapshot(dataset_path, self.get_parameter("game_id").value)
        self.exit_on_result = bool(self.get_parameter("exit_on_result").value)
        self.start_x, self.start_y, self.start_yaw = STARTS[self.scenario]

        reliable = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        latched = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.odom_pub = self.create_publisher(Odometry, "/state_estimation", qos_profile_sensor_data)
        self.referee_pub = self.create_publisher(ReceiveData, "/serial_receive_data", reliable)
        self.autoaim_pub = self.create_publisher(
            AutoaimToDecision, "/autoaim_to_decision", qos_profile_sensor_data
        )
        self.initial_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped, "/initialpose", latched
        )
        self.marker_pub = self.create_publisher(MarkerArray, "/simulation/markers", latched)
        self.status_pub = self.create_publisher(String, "/simulation/status", latched)

        self.create_subscription(Odometry, "/odom", self._on_odom, qos_profile_sensor_data)
        self.create_subscription(
            PoseWithCovarianceStamped, "/amcl_pose", self._on_amcl, reliable
        )
        self.create_subscription(PoseStamped, "/goal_pose", self._on_goal, reliable)
        self.create_subscription(
            DesicionSendData, "/serial_send_data", self._on_serial_command, reliable
        )
        self.create_subscription(
            DecisionToAutoaim,
            "/decision_to_autoaim",
            self._on_autoaim_command,
            reliable,
        )

        self.position = [self.start_x, self.start_y]
        self.yaw = self.start_yaw
        self.amcl_received = False
        self.odom_received = False
        self.goal = None
        self.serial_command = None
        self.autoaim_command = None
        self.enemy_outpost_hp = self.snapshot.enemy_outpost_hp
        self.ammo = 0 if self.scenario == "no_ammo" else 120
        self.sentry_hp = 400
        self.result_state = "RUNNING"
        self.result_detail = "waiting for scenario evidence"
        self._clock_start = None
        self._last_elapsed = 0.0
        self._last_initial_pose = -100.0
        self._finish_at = None
        self._shot_seen = False
        self._attack_reached = False
        self._supply_reached_at = None
        self._normal_reached = False
        self._damage_at = None
        self._damage_position = None
        self._evade_goal_seen = False
        self._evade_motion_seen = False
        self._recovery_goal_seen = False

        self.timer = self.create_timer(0.05, self._tick)
        self.get_logger().info(
            f"Scenario={self.scenario}, dataset game_id={self.snapshot.game_id}, "
            f"match={self.snapshot.match_name}"
        )

    def _elapsed(self):
        now = self.get_clock().now()
        if self._clock_start is None:
            self._clock_start = now
        return max(0.0, (now - self._clock_start).nanoseconds / 1.0e9)

    def _on_odom(self, message):
        self.odom_received = True
        if self.amcl_received:
            return
        # Gazebo diff-drive odometry is displacement from the spawn pose.
        dx = message.pose.pose.position.x
        dy = message.pose.pose.position.y
        c = math.cos(self.start_yaw)
        s = math.sin(self.start_yaw)
        self.position = [self.start_x + c * dx - s * dy, self.start_y + s * dx + c * dy]
        self.yaw = self.start_yaw + yaw_from_quaternion(message.pose.pose.orientation)

    def _on_amcl(self, message):
        self.amcl_received = True
        self.position = [message.pose.pose.position.x, message.pose.pose.position.y]
        self.yaw = yaw_from_quaternion(message.pose.pose.orientation)

    def _on_goal(self, message):
        self.goal = (message.pose.position.x, message.pose.position.y)
        if self.scenario == "dodge" and self._damage_at is not None:
            if planar_distance(self.goal, (5.0, 5.0)) > 0.4:
                self._evade_goal_seen = True
            elif self._evade_goal_seen:
                self._recovery_goal_seen = True

    def _on_serial_command(self, message):
        self.serial_command = message

    def _on_autoaim_command(self, message):
        self.autoaim_command = message

    def _publish_initial_pose(self, elapsed):
        if self.amcl_received or elapsed < 2.0 or elapsed - self._last_initial_pose < 1.0:
            return
        self._last_initial_pose = elapsed
        message = PoseWithCovarianceStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "map"
        message.pose.pose.position.x = self.start_x
        message.pose.pose.position.y = self.start_y
        message.pose.pose.orientation.z = math.sin(self.start_yaw * 0.5)
        message.pose.pose.orientation.w = math.cos(self.start_yaw * 0.5)
        message.pose.covariance[0] = 0.04
        message.pose.covariance[7] = 0.04
        message.pose.covariance[35] = 0.02
        self.initial_pose_pub.publish(message)

    def _game_state(self, elapsed):
        if self.scenario == "return_home":
            if elapsed < 5.0:
                return 0, 0
            if elapsed < 10.0:
                return 2, 410
            return 0, 0
        if self.scenario == "no_ammo":
            return 2, 420 if elapsed < 10.0 else 359
        return 2, max(1, 420 - int(elapsed))

    def _publish_inputs(self, elapsed, dt):
        game_period, remaining = self._game_state(elapsed)
        referee = ReceiveData()
        referee.game_period = game_period
        referee.time = remaining
        referee.hp_sentry = self.sentry_hp
        referee.defence_buff = 60
        referee.color = 0
        referee.ammo = self.ammo
        referee.hp_outpost = self.snapshot.own_outpost_hp
        referee.hp_base = self.snapshot.own_base_hp

        enemy_hp = [0] * 8
        for entity in self.snapshot.enemies:
            enemy_hp[entity.target_id - 1] = max(0, min(entity.hp, 1001))
        enemy_hp[5] = self.enemy_outpost_hp
        enemy_hp[6] = self.snapshot.enemy_base_hp
        referee.hp_enemy = enemy_hp
        by_target = {entity.target_id: entity for entity in self.snapshot.enemies}
        radar = []
        for target in (1, 2, 3, 4, 5, 8):
            entity = by_target.get(target)
            radar.extend((float(entity.x), float(entity.y)) if entity else (0.0, 0.0))
        referee.radar_data = radar
        self.referee_pub.publish(referee)

        autoaim = AutoaimToDecision()
        autoaim.target = [0] * 9
        autoaim.target_distance = [0.0] * 9
        autoaim.target_polar_r = [0.0] * 9
        autoaim.target_polar_angle = [0.0] * 9
        outpost_distance = planar_distance(self.position, (20.0, 7.5))
        if self.scenario == "attack_outpost" and self.enemy_outpost_hp > 0 and outpost_distance <= 6.2:
            autoaim.target[6] = 1
            autoaim.target_distance[6] = outpost_distance
            autoaim.target_polar_r[6] = outpost_distance
            autoaim.target_polar_angle[6] = math.atan2(
                7.5 - self.position[1], 20.0 - self.position[0]
            ) - self.yaw
        self.autoaim_pub.publish(autoaim)

        state = Odometry()
        state.header.stamp = self.get_clock().now().to_msg()
        state.header.frame_id = "map"
        state.child_frame_id = "base_footprint"
        state.pose.pose.position.x = self.position[0]
        state.pose.pose.position.y = self.position[1]
        state.pose.pose.position.z = 0.19
        state.pose.pose.orientation.z = math.sin(self.yaw * 0.5)
        state.pose.pose.orientation.w = math.cos(self.yaw * 0.5)
        self.odom_pub.publish(state)

        if (
            self.scenario == "attack_outpost"
            and self.serial_command is not None
            and self.autoaim_command is not None
            and self.serial_command.shoot_mode == 1
            and self.autoaim_command.target == 6
            and autoaim.target[6] == 1
        ):
            self._shot_seen = True
            self.enemy_outpost_hp = max(0, self.enemy_outpost_hp - max(1, int(300.0 * dt)))

    def _evaluate(self, elapsed):
        if self.result_state != "RUNNING":
            return
        if self.scenario == "return_home":
            if elapsed >= 10.0 and planar_distance(self.position, (4.971, 7.5)) <= 0.18:
                self._pass("game ended and sentry returned to (4.971, 7.5)")
        elif self.scenario == "attack_outpost":
            if planar_distance(self.position, (16.0, 11.0)) <= 0.22:
                self._attack_reached = True
            if self._attack_reached and self._shot_seen and self.enemy_outpost_hp == 0:
                self._pass("reached attack point, selected target 6, fired, and destroyed outpost")
        elif self.scenario == "no_ammo":
            at_supply = planar_distance(self.position, (2.0, 1.0)) <= 0.18
            if at_supply and self.goal is not None and planar_distance(self.goal, (2.0, 1.0)) <= 0.05:
                if self._supply_reached_at is None:
                    self._supply_reached_at = elapsed
                elif elapsed - self._supply_reached_at >= 0.6:
                    self.ammo = 100
            if self._supply_reached_at is not None and self.ammo > 0:
                self._pass("zero-ammo sentry collected the pending 100 rounds at supply")
        elif self.scenario == "dodge":
            if planar_distance(self.position, (5.0, 5.0)) <= 0.18:
                self._normal_reached = True
            if elapsed >= 12.0 and self._normal_reached and self._damage_at is None:
                self.sentry_hp = 350
                self._damage_at = elapsed
                self._damage_position = tuple(self.position)
                self.get_logger().info("Injected one unseen-damage event: HP 400 -> 350")
            if self._damage_position is not None and planar_distance(self.position, self._damage_position) >= 0.50:
                self._evade_motion_seen = True
            if self._evade_goal_seen and self._evade_motion_seen and self._recovery_goal_seen:
                self._pass("unseen damage caused movement, then normal goal resumed after quiet period")

        timeout = 80.0
        if elapsed >= timeout and self.result_state == "RUNNING":
            self._fail("scenario timed out before all required evidence was observed")

    def _pass(self, detail):
        self.result_state = "PASS"
        self.result_detail = detail
        self._finish_at = self._elapsed() + 1.0 if self.exit_on_result else None
        self.get_logger().info(f"VALIDATION PASS [{self.scenario}]: {detail}")

    def _fail(self, detail):
        self.result_state = "FAIL"
        self.result_detail = detail
        self._finish_at = self._elapsed() + 1.0 if self.exit_on_result else None
        self.get_logger().error(f"VALIDATION FAIL [{self.scenario}]: {detail}")

    def _marker(self, marker_id, marker_type, x, y, z, text=""):
        marker = Marker()
        marker.header.frame_id = "map"
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = "rm_decision_sim"
        marker.id = marker_id
        marker.type = marker_type
        marker.action = Marker.ADD
        marker.pose.position.x = x
        marker.pose.position.y = y
        marker.pose.position.z = z
        marker.pose.orientation.w = 1.0
        marker.color.a = 0.95
        marker.color.r = 0.95
        marker.color.g = 0.95
        marker.color.b = 0.95
        marker.text = text
        marker.scale.x = 0.18
        marker.scale.y = 0.18
        marker.scale.z = 0.28
        marker.lifetime = Duration(seconds=0).to_msg()
        return marker

    def _publish_visuals_and_status(self, elapsed):
        markers = MarkerArray()
        labels = (
            (1, 1.0, 7.5, 1.45, f"RED BASE  HP {self.snapshot.own_base_hp}"),
            (2, 8.0, 7.5, 1.20, f"RED OUTPOST  HP {self.snapshot.own_outpost_hp}"),
            (3, 20.0, 7.5, 1.20, f"BLUE OUTPOST  HP {self.enemy_outpost_hp}"),
            (4, 27.0, 7.5, 1.45, f"BLUE BASE  HP {self.snapshot.enemy_base_hp}"),
        )
        for marker_id, x, y, z, text in labels:
            markers.markers.append(self._marker(marker_id, Marker.TEXT_VIEW_FACING, x, y, z, text))
        points = ((10, 4.971, 7.5, "HOME"), (11, 2.0, 1.0, "SUPPLY"), (12, 16.0, 11.0, "ATTACK"))
        for marker_id, x, y, text in points:
            marker = self._marker(marker_id, Marker.CYLINDER, x, y, 0.025)
            marker.scale.x = 0.45
            marker.scale.y = 0.45
            marker.scale.z = 0.05
            marker.color.r = 0.10
            marker.color.g = 0.85
            marker.color.b = 0.30
            marker.color.a = 0.75
            markers.markers.append(marker)
            markers.markers.append(
                self._marker(marker_id + 10, Marker.TEXT_VIEW_FACING, x, y, 0.55, text)
            )
        hud = self._marker(
            30,
            Marker.TEXT_VIEW_FACING,
            14.0,
            14.2,
            1.2,
            f"{self.scenario} | {self.result_state} | HP {self.sentry_hp} | ammo {self.ammo}",
        )
        hud.scale.z = 0.42
        if self.result_state == "PASS":
            hud.color.r, hud.color.g, hud.color.b = 0.1, 1.0, 0.2
        elif self.result_state == "FAIL":
            hud.color.r, hud.color.g, hud.color.b = 1.0, 0.1, 0.1
        markers.markers.append(hud)
        self.marker_pub.publish(markers)

        status = {
            "scenario": self.scenario,
            "state": self.result_state,
            "detail": self.result_detail,
            "elapsed": round(elapsed, 2),
            "position": [round(self.position[0], 3), round(self.position[1], 3)],
            "goal": list(self.goal) if self.goal else None,
            "localization": "amcl" if self.amcl_received else "odometry_fallback",
            "planner": "Nav2 Navfn A*",
            "game_id": self.snapshot.game_id,
        }
        self.status_pub.publish(String(data=json.dumps(status, ensure_ascii=False)))

    def _tick(self):
        elapsed = self._elapsed()
        dt = min(0.2, max(0.0, elapsed - self._last_elapsed))
        self._last_elapsed = elapsed
        self._publish_initial_pose(elapsed)
        self._publish_inputs(elapsed, dt)
        self._evaluate(elapsed)
        self._publish_visuals_and_status(elapsed)
        if self._finish_at is not None and elapsed >= self._finish_at:
            rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    node = None
    exit_code = 1
    try:
        node = ScenarioDriver()
        rclpy.spin(node)
        exit_code = 0 if node.result_state == "PASS" else 2
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
