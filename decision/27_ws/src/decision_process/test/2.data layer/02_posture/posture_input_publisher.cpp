#include <chrono>
#include <functional>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

class PostureInputPublisher : public rclcpp::Node
{
public:
  PostureInputPublisher()
  : Node("posture_input_publisher"), start_(std::chrono::steady_clock::now())
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    const auto reliable_qos = rclcpp::QoS(10).reliable();
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>("/state_estimation", sensor_qos);
    referee_pub_ = create_publisher<decision_process::msg::ReceiveData>("/serial_receive_data", reliable_qos);
    autoaim_pub_ = create_publisher<decision_process::msg::AutoaimToDecision>("/autoaim_to_decision", sensor_qos);
    timer_ = create_wall_timer(100ms, std::bind(&PostureInputPublisher::publishFrame, this));
    RCLCPP_INFO(get_logger(), "任务2姿态：先保持进攻姿态1，前哨摧毁后切换移动姿态3");
  }

private:
  void publishFrame()
  {
    const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
    nav_msgs::msg::Odometry odom;
    odom.header.stamp = now();
    odom.header.frame_id = "map";
    odom.child_frame_id = "base_link";
    odom.pose.pose.position.x = t < 1.5 ? 1.0 : 16.0;
    odom.pose.pose.position.y = t < 1.5 ? 2.0 : 11.0;
    odom.pose.pose.position.z = 0.3;
    odom.pose.pose.orientation.w = 1.0;

    decision_process::msg::ReceiveData referee;
    referee.game_period = 2U; referee.time = 400U; referee.hp_sentry = 400U;
    referee.defence_buff = 60U; referee.color = 0U; referee.ammo = 200U;
    referee.hp_outpost = 1000U; referee.hp_base = 5000U;
    const uint16_t outpost_hp = t < 2.5 ? 900U : 0U;
    referee.hp_enemy = {250U, 190U, 180U, 170U, 160U, outpost_hp, 4500U, 350U};

    decision_process::msg::AutoaimToDecision autoaim;
    autoaim.target.assign(9U, 0U); autoaim.target_distance.assign(9U, 0.0);
    autoaim.target_polar_r.assign(9U, 0.0); autoaim.target_polar_angle.assign(9U, 0.0);

    odom_pub_->publish(odom); referee_pub_->publish(referee); autoaim_pub_->publish(autoaim);
    RCLCPP_INFO(get_logger(), "INPUT task=2 t=%.1f outpost_hp=%u", t, outpost_hp);
    if (!released_ && outpost_hp == 0U) {
      released_ = true;
      RCLCPP_WARN(get_logger(), "【检查】攻击任务释放，posture 应从1切换为3");
    }
    if (t >= 7.0) {timer_->cancel(); rclcpp::shutdown();}
  }

  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
  rclcpp::Publisher<decision_process::msg::ReceiveData>::SharedPtr referee_pub_;
  rclcpp::Publisher<decision_process::msg::AutoaimToDecision>::SharedPtr autoaim_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  std::chrono::steady_clock::time_point start_;
  bool released_{false};
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<PostureInputPublisher>());
  rclcpp::shutdown();
  return 0;
}
