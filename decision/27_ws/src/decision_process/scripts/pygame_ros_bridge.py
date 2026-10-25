#!/usr/bin/python3
"""Bridge local UDP JSON from Pygame to the ROS 2 decision topics."""

import json
import math
import os
import socket

import rclpy
from geometry_msgs.msg import PoseStamped, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool
from tf2_ros import TransformBroadcaster

from decision_process.msg import (
    AutoaimToDecision,
    DecisionToAutoaim,
    DesicionSendData,
    ReceiveData,
)


HOST = "127.0.0.1"
PORT = int(os.environ.get("RM2026_SIM_PORT", "39001"))


class PygameRosBridge(Node):
    def __init__(self) -> None:
        super().__init__("pygame_ros_bridge")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((HOST, PORT))
        self.socket.setblocking(False)
        self.client_address = None

        self.referee_pub = self.create_publisher(
            ReceiveData, "/serial_receive_data", 10
        )
        self.autoaim_pub = self.create_publisher(
            AutoaimToDecision, "/autoaim_to_decision", 10
        )
        self.odom_pub = self.create_publisher(Odometry, "/state_estimation", 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        self.create_subscription(
            DesicionSendData, "/serial_send_data", self._serial_callback, 10
        )
        self.create_subscription(
            DecisionToAutoaim,
            "/decision_to_autoaim",
            self._autoaim_callback,
            10,
        )
        self.create_subscription(PoseStamped, "/goal_pose", self._goal_callback, 10)
        self.create_subscription(
            Bool, "/decision_goal_enabled", self._goal_enabled_callback, 10
        )

        self.serial_output = {
            "posture": 3,
            "confirm_respawn": 0,
            "tripod_mode": 1,
            "spin_mode": 0,
            "shoot_mode": 0,
        }
        self.autoaim_output = {"color": 0, "target": 0, "decide_yaw": 0.0}
        self.goal = None
        self.goal_enabled = False
        self.create_timer(0.02, self._update)
        self.get_logger().info(f"Pygame UDP bridge listening on {HOST}:{PORT}")

    def _serial_callback(self, message: DesicionSendData) -> None:
        self.serial_output = {
            "posture": int(message.posture),
            "confirm_respawn": int(message.confirm_respawn),
            "tripod_mode": int(message.tripod_mode),
            "spin_mode": int(message.spin_mode),
            "shoot_mode": int(message.shoot_mode),
        }

    def _autoaim_callback(self, message: DecisionToAutoaim) -> None:
        self.autoaim_output = {
            "color": int(message.color),
            "target": int(message.target),
            "decide_yaw": float(message.decide_yaw),
        }

    def _goal_callback(self, message: PoseStamped) -> None:
        self.goal = [float(message.pose.position.x), float(message.pose.position.y)]

    def _goal_enabled_callback(self, message: Bool) -> None:
        self.goal_enabled = bool(message.data)
        if not self.goal_enabled:
            self.goal = None

    @staticmethod
    def _bounded_sequence(values, length, conversion):
        result = [conversion(value) for value in list(values or [])[:length]]
        result.extend(conversion(0) for _ in range(length - len(result)))
        return result

    @staticmethod
    def _flatten_points(values):
        flattened = []
        for point in list(values or []):
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            flattened.extend((float(point[0]), float(point[1])))
        return flattened

    def _publish_state(self, state: dict) -> None:
        referee = ReceiveData()
        referee.game_period = int(state.get("game_period", 0))
        referee.time = max(0, int(state.get("time", 0)))
        referee.hp_sentry = max(0, int(state.get("hp_sentry", 0)))
        referee.defence_buff = max(0, min(100, int(state.get("defence_buff", 0))))
        referee.color = int(state.get("color", 0))
        referee.ammo = max(0, int(state.get("ammo", 0)))
        referee.hp_outpost = max(0, int(state.get("hp_outpost", 0)))
        referee.hp_base = max(0, int(state.get("hp_base", 0)))
        referee.hp_enemy = self._bounded_sequence(state.get("hp_enemy"), 8, int)
        referee.radar_data = self._bounded_sequence(
            state.get("radar_data"), 12, float
        )
        referee.hp_friend = self._bounded_sequence(
            state.get("hp_friend"), 4, int
        )
        referee.friendly_ground_positions = self._bounded_sequence(
            state.get("friendly_ground_positions"), 8, float
        )
        referee.pursuit_costmap_polygon = self._flatten_points(
            state.get("pursuit_costmap_polygon")
        )
        referee.pending_ammo = max(0, int(state.get("pending_ammo", 0)))
        referee.economy = max(0, min(1000, int(state.get("economy", 0))))
        referee.conservative_patrol_points = self._flatten_points(
            state.get("conservative_patrol_points")
        )
        referee.aggressive_patrol_points = self._flatten_points(
            state.get("aggressive_patrol_points")
        )
        self.referee_pub.publish(referee)

        raw_autoaim = state.get("autoaim") or {}
        autoaim = AutoaimToDecision()
        autoaim.target = self._bounded_sequence(raw_autoaim.get("target"), 9, int)
        autoaim.target_distance = self._bounded_sequence(
            raw_autoaim.get("target_distance"), 9, float
        )
        autoaim.target_polar_r = self._bounded_sequence(
            raw_autoaim.get("target_polar_r"), 9, float
        )
        autoaim.target_polar_angle = self._bounded_sequence(
            raw_autoaim.get("target_polar_angle"), 9, float
        )
        self.autoaim_pub.publish(autoaim)

        yaw = float(state.get("yaw", 0.0))
        camera_yaw = float(state.get("camera_yaw", yaw))
        stamp = self.get_clock().now().to_msg()
        odometry = Odometry()
        odometry.header.stamp = stamp
        odometry.header.frame_id = "map"
        odometry.child_frame_id = "base_link"
        odometry.pose.pose.position.x = float(state.get("x", 0.0))
        odometry.pose.pose.position.y = float(state.get("y", 0.0))
        odometry.pose.pose.orientation.z = math.sin(yaw * 0.5)
        odometry.pose.pose.orientation.w = math.cos(yaw * 0.5)
        self.odom_pub.publish(odometry)

        camera = TransformStamped()
        camera.header.stamp = stamp
        camera.header.frame_id = "map"
        camera.child_frame_id = "camera_link"
        camera.transform.translation.x = float(state.get("x", 0.0))
        camera.transform.translation.y = float(state.get("y", 0.0))
        camera.transform.rotation.z = math.sin(camera_yaw * 0.5)
        camera.transform.rotation.w = math.cos(camera_yaw * 0.5)
        self.tf_broadcaster.sendTransform(camera)

    def _send_output(self) -> None:
        if self.client_address is None:
            return
        payload = {
            "serial": self.serial_output,
            "autoaim": self.autoaim_output,
            "goal": self.goal if self.goal_enabled else None,
        }
        self.socket.sendto(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            self.client_address,
        )

    def _update(self) -> None:
        latest = None
        while True:
            try:
                data, address = self.socket.recvfrom(65535)
            except BlockingIOError:
                break
            try:
                latest = json.loads(data.decode("utf-8"))
                self.client_address = address
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                self.get_logger().warning("Ignored malformed Pygame UDP packet")
        if isinstance(latest, dict):
            self._publish_state(latest)
        self._send_output()

    def destroy_node(self):
        self.socket.close()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = PygameRosBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
