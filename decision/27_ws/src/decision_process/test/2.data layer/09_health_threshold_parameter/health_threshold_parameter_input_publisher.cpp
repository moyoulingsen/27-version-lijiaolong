#include <chrono>
#include <functional>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

class HealthThresholdParameterInputPublisher : public rclcpp::Node
{
public:
  HealthThresholdParameterInputPublisher()
  : Node("health_threshold_parameter_input_publisher"), start_(std::chrono::steady_clock::now())
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    const auto reliable_qos = rclcpp::QoS(10).reliable();
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>("/state_estimation", sensor_qos);
    referee_pub_ = create_publisher<decision_process::msg::ReceiveData>("/serial_receive_data", reliable_qos);
    autoaim_pub_ = create_publisher<decision_process::msg::AutoaimToDecision>("/autoaim_to_decision", sensor_qos);
    timer_ = create_wall_timer(100ms, std::bind(&HealthThresholdParameterInputPublisher::publishFrame, this));
    RCLCPP_INFO(get_logger(), "任务9 XML阈值：树中设260，hp250应回血，hp270应释放");
  }

private:
  void publishFrame()
  {
    const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
    nav_msgs::msg::Odometry odom;
    odom.header.stamp = now(); odom.header.frame_id = "map";
    if (t >= 1.5 && t < 2.8) {
      odom.pose.pose.position.x = 2.0; odom.pose.pose.position.y = 1.0;
    } else {
      odom.pose.pose.position.x = 5.0; odom.pose.pose.position.y = 5.0;
    }
    odom.pose.pose.orientation.w = 1.0;

    decision_process::msg::ReceiveData referee;
    referee.game_period = 2U; referee.time = 300U;
    referee.hp_sentry = t < 2.8 ? 250U : 270U;
    referee.color = 0U; referee.ammo = 200U; referee.hp_outpost = 1000U;
    referee.hp_base = 5000U;
    referee.hp_enemy = {250U, 200U, 200U, 200U, 200U, 0U, 5000U, 400U};
    referee.radar_data.assign(12U, 0.0F);

    decision_process::msg::AutoaimToDecision autoaim;
    autoaim.target.assign(9U, 0U); autoaim.target_distance.assign(9U, 0.0);
    autoaim.target_polar_r.assign(9U, 0.0); autoaim.target_polar_angle.assign(9U, 0.0);

    odom_pub_->publish(odom); referee_pub_->publish(referee); autoaim_pub_->publish(autoaim);
    RCLCPP_INFO(get_logger(), "INPUT task=10 t=%.1f xml_threshold=260 hp=%u position=[%.1f,%.1f]",
      t, static_cast<unsigned int>(referee.hp_sentry),
      odom.pose.pose.position.x, odom.pose.pose.position.y);
    if (t >= 4.2) {timer_->cancel(); rclcpp::shutdown();}
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
  rclcpp::spin(std::make_shared<HealthThresholdParameterInputPublisher>());
  rclcpp::shutdown();
  return 0;
}
