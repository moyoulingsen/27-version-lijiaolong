#!/usr/bin/python3
"""Forward the existing decision /goal_pose topic to Nav2 NavigateToPose."""

import math

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose


def yaw_from_pose(pose):
    return 2.0 * math.atan2(pose.orientation.z, pose.orientation.w)


class NavGoalAdapter(Node):
    def __init__(self):
        super().__init__("decision_nav_goal_adapter")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._client = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self._pending = None
        self._last_key = None
        self._goal_handle = None
        self._subscription = self.create_subscription(
            PoseStamped, "/goal_pose", self._on_goal, qos
        )
        self._timer = self.create_timer(0.25, self._try_send)

    def _on_goal(self, message):
        key = (
            round(message.pose.position.x, 3),
            round(message.pose.position.y, 3),
            round(yaw_from_pose(message.pose), 3),
        )
        if key == self._last_key:
            return
        self._last_key = key
        self._pending = message
        self.get_logger().info(
            "Decision goal queued for Nav2: x=%.3f y=%.3f yaw=%.3f"
            % (key[0], key[1], key[2])
        )

    def _try_send(self):
        if self._pending is None or not self._client.server_is_ready():
            return
        message = self._pending
        self._pending = None
        goal = NavigateToPose.Goal()
        goal.pose = message
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        future = self._client.send_goal_async(goal)
        future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future):
        try:
            self._goal_handle = future.result()
        except Exception as error:  # ROS future propagates transport failures here.
            self.get_logger().error(f"Nav2 goal request failed: {error}")
            return
        if not self._goal_handle.accepted:
            self.get_logger().error("Nav2 rejected the decision goal")
            return
        self.get_logger().info("Nav2 accepted the decision goal")
        result_future = self._goal_handle.get_result_async()
        result_future.add_done_callback(self._on_result)

    def _on_result(self, future):
        try:
            result = future.result()
            self.get_logger().info(f"Nav2 action finished with status={result.status}")
        except Exception as error:
            self.get_logger().error(f"Nav2 result failed: {error}")


def main(args=None):
    rclpy.init(args=args)
    node = NavGoalAdapter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
