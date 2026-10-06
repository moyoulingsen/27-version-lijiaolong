#include <cmath>
#include <memory>

#include "geometry_msgs/msg/pose_stamped.hpp"
#include "rclcpp/rclcpp.hpp"

#include "decision_process/msg/decision_to_autoaim.hpp"
#include "decision_process/msg/desicion_send_data.hpp"

/*
- 十个消息端测试共用的输出监视器。
- 只订阅并原样打印决策输出，不保存预期值，不判断通过或失败。
- 每收到一帧就打印一帧，用于检查约 0.1 秒周期的真实消息流。
 */
class DecisionOutputStreamMonitor : public rclcpp::Node
{
public:
  DecisionOutputStreamMonitor()
  : Node("decision_output_stream_monitor")
  {
    const auto reliable_qos = rclcpp::QoS(rclcpp::KeepLast(10)).reliable();

    goal_sub_ = create_subscription<geometry_msgs::msg::PoseStamped>(
      "/goal_pose", reliable_qos,
      [this](const geometry_msgs::msg::PoseStamped::SharedPtr msg) {
        const auto & q = msg->pose.orientation;
        const double yaw = std::atan2(
          2.0 * (q.w * q.z + q.x * q.y),
          1.0 - 2.0 * (q.y * q.y + q.z * q.z));
        RCLCPP_INFO(
          get_logger(),
          "TX /goal_pose frame=%s xyz=[%.3f, %.3f, %.3f] yaw=%.3f",
          msg->header.frame_id.c_str(), msg->pose.position.x,
          msg->pose.position.y, msg->pose.position.z, yaw);
      });

    serial_sub_ = create_subscription<decision_process::msg::DesicionSendData>(
      "/serial_send_data", reliable_qos,
      [this](const decision_process::msg::DesicionSendData::SharedPtr msg) {
        RCLCPP_INFO(
          get_logger(),
          "TX /serial_send_data posture=%u respawn=%u tripod=%u spin=%u shoot=%u",
          static_cast<unsigned int>(msg->posture),
          static_cast<unsigned int>(msg->confirm_respawn),
          static_cast<unsigned int>(msg->tripod_mode),
          static_cast<unsigned int>(msg->spin_mode),
          static_cast<unsigned int>(msg->shoot_mode));
      });

    autoaim_sub_ = create_subscription<decision_process::msg::DecisionToAutoaim>(
      "/decision_to_autoaim", reliable_qos,
      [this](const decision_process::msg::DecisionToAutoaim::SharedPtr msg) {
        RCLCPP_INFO(
          get_logger(),
          "TX /decision_to_autoaim color=%u target=%u yaw=%.3f",
          static_cast<unsigned int>(msg->color),
          static_cast<unsigned int>(msg->target), msg->decide_yaw);
      });

    RCLCPP_INFO(get_logger(), "输出监视器已启动：原样打印所有决策输出");
  }

private:
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr goal_sub_;
  rclcpp::Subscription<decision_process::msg::DesicionSendData>::SharedPtr serial_sub_;
  rclcpp::Subscription<decision_process::msg::DecisionToAutoaim>::SharedPtr autoaim_sub_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<DecisionOutputStreamMonitor>());
  rclcpp::shutdown();
  return 0;
}
