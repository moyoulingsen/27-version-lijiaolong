#include <chrono>
#include <functional>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

class NoAmmoInputPublisher : public rclcpp::Node
{
public:
  NoAmmoInputPublisher()
  : Node("no_ammo_input_publisher"), start_(std::chrono::steady_clock::now())
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    const auto reliable_qos = rclcpp::QoS(10).reliable();
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>("/state_estimation", sensor_qos);
    referee_pub_ = create_publisher<decision_process::msg::ReceiveData>("/serial_receive_data", reliable_qos);
    autoaim_pub_ = create_publisher<decision_process::msg::AutoaimToDecision>("/autoaim_to_decision", sensor_qos);
    timer_ = create_wall_timer(100ms, std::bind(&NoAmmoInputPublisher::publishFrame, this));
    RCLCPP_INFO(get_logger(), "任务3无弹：无储备时站桩，有储备后去补给点，弹量增加后退出");
  }

private:
  void publishFrame()
  {
    const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
    nav_msgs::msg::Odometry odom;
    odom.header.stamp = now(); odom.header.frame_id = "map"; odom.child_frame_id = "base_link";
    if (t >= 4.5) {odom.pose.pose.position.x = 2.0; odom.pose.pose.position.y = 1.0;}
    else if (t >= 1.5) {odom.pose.pose.position.x = 4.971; odom.pose.pose.position.y = 7.5;}
    else {odom.pose.pose.position.x = 1.0; odom.pose.pose.position.y = 2.0;}
    odom.pose.pose.position.z = 0.3; odom.pose.pose.orientation.w = 1.0;

    decision_process::msg::ReceiveData referee;
    referee.game_period = 2U; referee.time = t < 2.5 ? 420U : 359U;
    referee.hp_sentry = 400U; referee.defence_buff = 60U; referee.color = 0U;
    referee.ammo = t < 7.0 ? 0U : 100U; referee.hp_outpost = 1000U; referee.hp_base = 5000U;
    referee.hp_enemy = {250U, 190U, 180U, 170U, 160U, 0U, 4500U, 350U};

    decision_process::msg::AutoaimToDecision autoaim;
    autoaim.target.assign(9U, 1U); autoaim.target_distance.assign(9U, 2.0);
    autoaim.target_polar_r.assign(9U, 2.0); autoaim.target_polar_angle.assign(9U, 0.0);

    odom_pub_->publish(odom); referee_pub_->publish(referee); autoaim_pub_->publish(autoaim);
    RCLCPP_INFO(get_logger(), "INPUT task=4 t=%.1f time=%u ammo=%u", t,
      static_cast<unsigned int>(referee.time), static_cast<unsigned int>(referee.ammo));
    if (t >= 9.0) {timer_->cancel(); rclcpp::shutdown();}
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
  rclcpp::spin(std::make_shared<NoAmmoInputPublisher>());
  rclcpp::shutdown();
  return 0;
}
