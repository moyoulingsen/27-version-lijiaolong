#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"

#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

class TestDataPublisher : public rclcpp::Node
{
public:
  TestDataPublisher()
  : Node("decision_test_data_publisher")
  {
    simulate_return_home_ = declare_parameter<bool>("simulate_return_home", false);
    simulate_attack_outpost_ = declare_parameter<bool>("simulate_attack_outpost", false);
    simulate_no_ammo_ = declare_parameter<bool>("simulate_no_ammo", false);
    simulation_start_ = std::chrono::steady_clock::now();
    const auto sensor_qos = rclcpp::SensorDataQoS();
    const auto reliable_qos = rclcpp::QoS(rclcpp::KeepLast(10)).reliable();

    odometry_pub_ = create_publisher<nav_msgs::msg::Odometry>("/state_estimation", sensor_qos);
    referee_pub_ = create_publisher<decision_process::msg::ReceiveData>(
      "/serial_receive_data", reliable_qos);
    autoaim_pub_ = create_publisher<decision_process::msg::AutoaimToDecision>(
      "/autoaim_to_decision", sensor_qos);

    timer_ = create_wall_timer(100ms, std::bind(&TestDataPublisher::publishTestData, this));
    RCLCPP_INFO(get_logger(), "Publishing test input data at 10 Hz");
  }

private:
  void publishTestData()
  {
    nav_msgs::msg::Odometry odometry;
    odometry.header.stamp = now();
    odometry.header.frame_id = "map";
    odometry.child_frame_id = "base_link";
    const double elapsed = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - simulation_start_).count();
    if (simulate_no_ammo_ && elapsed >= 4.0) {
      odometry.pose.pose.position.x = 2.0;
      odometry.pose.pose.position.y = 1.0;
    } else if (simulate_no_ammo_ && elapsed >= 1.0) {
      odometry.pose.pose.position.x = 4.971;
      odometry.pose.pose.position.y = 7.5;
    } else if (simulate_attack_outpost_ && elapsed >= 1.0) {
      odometry.pose.pose.position.x = 16.0;
      odometry.pose.pose.position.y = 11.0;
    } else {
      odometry.pose.pose.position.x = 1.0;
      odometry.pose.pose.position.y = 2.0;
    }
    odometry.pose.pose.position.z = 0.3;
    odometry.pose.pose.orientation.z = std::sin(0.25);
    odometry.pose.pose.orientation.w = std::cos(0.25);
    odometry_pub_->publish(odometry);

    decision_process::msg::ReceiveData referee;
    if (simulate_return_home_) {
      if (elapsed < 1.0) {
        referee.game_period = 0;
        referee.time = 0;
      } else if (elapsed < 2.0) {
        referee.game_period = 2;
        referee.time = 400;
      } else {
        referee.game_period = 0;
        referee.time = 0;
      }
    } else if (simulate_no_ammo_) {
      referee.game_period = 2;
      referee.time = elapsed < 2.0 ? 420U : 359U;
    } else {
      referee.game_period = 2;
      referee.time = 400;
    }
    referee.hp_sentry = 400;
    referee.defence_buff = 60;
    referee.color = 0;
    referee.ammo = simulate_no_ammo_ && elapsed < 6.0 ? 0U : 200U;
    if (simulate_no_ammo_ && elapsed >= 6.0) {
      referee.ammo = 100U;
    }
    referee.hp_outpost = 1000;
    referee.hp_base = 5000;
    const uint16_t enemy_outpost_hp =
      simulate_attack_outpost_ && elapsed >= 3.0 ? 0U : 900U;
    referee.hp_enemy = {250, 190, 180, 170, 160, enemy_outpost_hp, 4500, 350};
    referee.radar_data = {
      5.0F, 5.0F, 6.0F, 5.0F, 7.0F, 5.0F,
      8.0F, 5.0F, 9.0F, 5.0F, 10.0F, 5.0F};
    referee_pub_->publish(referee);

    decision_process::msg::AutoaimToDecision autoaim;
    autoaim.target = {1, 1, 1, 1, 1, 1, 1, 1, 1};
    if (simulate_attack_outpost_) {
      autoaim.target[6] = elapsed >= 2.0 && elapsed < 3.0 ? 1U : 0U;
    }
    autoaim.target_distance = {1.0, 2.1, 2.2, 2.3, 2.4, 2.5, 6.0, 7.0, 2.8};
    if (simulate_attack_outpost_) {
      autoaim.target_distance[6] = autoaim.target[6] != 0U ? 4.0 : 0.0;
    }
    autoaim.target_polar_r = {1.0, 2.1, 2.2, 2.3, 2.4, 2.5, 6.0, 7.0, 2.8};
    autoaim.target_polar_angle = {-0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4};
    autoaim_pub_->publish(autoaim);
  }

  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odometry_pub_;
  rclcpp::Publisher<decision_process::msg::ReceiveData>::SharedPtr referee_pub_;
  rclcpp::Publisher<decision_process::msg::AutoaimToDecision>::SharedPtr autoaim_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  bool simulate_return_home_{false};
  bool simulate_attack_outpost_{false};
  bool simulate_no_ammo_{false};
  std::chrono::steady_clock::time_point simulation_start_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<TestDataPublisher>());
  rclcpp::shutdown();
  return 0;
}
