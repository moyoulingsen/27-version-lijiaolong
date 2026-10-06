#include <chrono>
#include <cmath>
#include <functional>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

class DodgeInputPublisher : public rclcpp::Node
{
public:
  DodgeInputPublisher()
  : Node("dodge_input_publisher"), start_(std::chrono::steady_clock::now())
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    const auto reliable_qos = rclcpp::QoS(10).reliable();
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>("/state_estimation", sensor_qos);
    referee_pub_ = create_publisher<decision_process::msg::ReceiveData>("/serial_receive_data", reliable_qos);
    autoaim_pub_ = create_publisher<decision_process::msg::AutoaimToDecision>("/autoaim_to_decision", sensor_qos);
    timer_ = create_wall_timer(100ms, std::bind(&DodgeInputPublisher::publishFrame, this));
    RCLCPP_INFO(get_logger(), "任务4躲避：先完成攻击导航，再模拟无目标掉血和连续躲避");
  }

private:
  void publishFrame()
  {
    const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
    nav_msgs::msg::Odometry odom;
    odom.header.stamp = now(); odom.header.frame_id = "map"; odom.child_frame_id = "base_link";
    if (t >= 4.6) {odom.pose.pose.position.x = 16.8; odom.pose.pose.position.y = 11.8;}
    else if (t >= 3.8) {odom.pose.pose.position.x = 16.0; odom.pose.pose.position.y = 11.8;}
    else if (t >= 1.0) {odom.pose.pose.position.x = 16.0; odom.pose.pose.position.y = 11.0;}
    else {odom.pose.pose.position.x = 1.0; odom.pose.pose.position.y = 2.0;}
    odom.pose.pose.position.z = 0.3;
    odom.pose.pose.orientation.z = std::sin(0.25);
    odom.pose.pose.orientation.w = std::cos(0.25);

    decision_process::msg::ReceiveData referee;
    referee.game_period = 2U; referee.time = 400U;
    referee.hp_sentry = t < 3.0 ? 400U : 350U; referee.defence_buff = 60U;
    referee.color = 0U; referee.ammo = 200U; referee.hp_outpost = 1000U; referee.hp_base = 5000U;
    const uint16_t outpost_hp = t < 2.0 ? 900U : 0U;
    referee.hp_enemy = {250U, 190U, 180U, 170U, 160U, outpost_hp, 4500U, 350U};

    decision_process::msg::AutoaimToDecision autoaim;
    autoaim.target.assign(9U, 0U); autoaim.target_distance.assign(9U, 0.0);
    autoaim.target_polar_r.assign(9U, 0.0); autoaim.target_polar_angle.assign(9U, 0.0);

    odom_pub_->publish(odom); referee_pub_->publish(referee); autoaim_pub_->publish(autoaim);
    RCLCPP_INFO(get_logger(), "INPUT task=5 t=%.1f hp=%u outpost_hp=%u position=[%.1f,%.1f]",
      t, static_cast<unsigned int>(referee.hp_sentry), outpost_hp,
      odom.pose.pose.position.x, odom.pose.pose.position.y);
    if (t >= 7.0) {timer_->cancel(); rclcpp::shutdown();}
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
  rclcpp::spin(std::make_shared<DodgeInputPublisher>());
  rclcpp::shutdown();
  return 0;
}
