#include <chrono>
#include <functional>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

class GimbalControlInputPublisher : public rclcpp::Node
{
public:
  GimbalControlInputPublisher()
  : Node("gimbal_control_input_publisher"), start_(std::chrono::steady_clock::now())
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    const auto reliable_qos = rclcpp::QoS(10).reliable();
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>("/state_estimation", sensor_qos);
    referee_pub_ = create_publisher<decision_process::msg::ReceiveData>("/serial_receive_data", reliable_qos);
    autoaim_pub_ = create_publisher<decision_process::msg::AutoaimToDecision>("/autoaim_to_decision", sensor_qos);
    timer_ = create_wall_timer(100ms, std::bind(&GimbalControlInputPublisher::publishFrame, this));
    RCLCPP_INFO(get_logger(), "任务8云台：无锁定旋转、锁定射击停止、丢失目标恢复旋转");
  }

private:
  void publishFrame()
  {
    const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
    nav_msgs::msg::Odometry odom;
    odom.header.stamp = now(); odom.header.frame_id = "map";
    odom.pose.pose.position.x = 16.0; odom.pose.pose.position.y = 11.0;
    odom.pose.pose.orientation.w = 1.0;

    decision_process::msg::ReceiveData referee;
    referee.game_period = 2U; referee.time = 340U; referee.hp_sentry = 400U;
    referee.color = 0U; referee.ammo = 200U; referee.hp_outpost = 1000U;
    referee.hp_base = 5000U;
    referee.hp_enemy = {250U, 200U, 200U, 200U, 200U, 900U, 5000U, 400U};
    referee.radar_data.assign(12U, 0.0F);

    const bool locked = t >= 1.0 && t < 3.0;
    decision_process::msg::AutoaimToDecision autoaim;
    autoaim.target.assign(9U, 0U); autoaim.target_distance.assign(9U, 0.0);
    autoaim.target_polar_r.assign(9U, 0.0); autoaim.target_polar_angle.assign(9U, 0.0);
    autoaim.target[6] = locked ? 1U : 0U;
    autoaim.target_distance[6] = locked ? 3.0 : 0.0;

    odom_pub_->publish(odom); referee_pub_->publish(referee); autoaim_pub_->publish(autoaim);
    RCLCPP_INFO(get_logger(), "INPUT task=8 t=%.1f outpost_locked=%u expected_tripod=%u expected_shoot=%u",
      t, locked ? 1U : 0U, locked ? 0U : 1U, locked ? 1U : 0U);
    if (t >= 4.5) {timer_->cancel(); rclcpp::shutdown();}
  }

  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
  rclcpp::Publisher<decision_process::msg::ReceiveData>::SharedPtr referee_pub_;
  rclcpp::Publisher<decision_process::msg::AutoaimToDecision>::SharedPtr autoaim_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  std::chrono::steady_clock::time_point start_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<GimbalControlInputPublisher>());
  rclcpp::shutdown();
  return 0;
}
