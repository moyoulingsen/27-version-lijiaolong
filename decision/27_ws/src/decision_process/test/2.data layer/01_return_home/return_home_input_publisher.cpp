#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"

#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

class ReturnHomeInputPublisher : public rclcpp::Node
{
public:
  ReturnHomeInputPublisher()
  : Node("return_home_input_publisher"), start_time_(std::chrono::steady_clock::now())
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    const auto reliable_qos = rclcpp::QoS(rclcpp::KeepLast(10)).reliable();
    odometry_pub_ = create_publisher<nav_msgs::msg::Odometry>("/state_estimation", sensor_qos);
    referee_pub_ = create_publisher<decision_process::msg::ReceiveData>(
      "/serial_receive_data", reliable_qos);
    autoaim_pub_ = create_publisher<decision_process::msg::AutoaimToDecision>(
      "/autoaim_to_decision", sensor_qos);
    timer_ = create_wall_timer(100ms, std::bind(&ReturnHomeInputPublisher::publishFrame, this));
    RCLCPP_INFO(get_logger(), "任务1归位：10秒后把 game_period 从2切换为0");
  }

private:
  double elapsedSeconds() const
  {
    return std::chrono::duration<double>(
      std::chrono::steady_clock::now() - start_time_).count();
  }

  void publishFrame()
  {
    const double elapsed = elapsedSeconds();
    nav_msgs::msg::Odometry odometry;
    odometry.header.stamp = now();
    odometry.header.frame_id = "map";
    odometry.child_frame_id = "base_link";
    odometry.pose.pose.position.x = 1.0;
    odometry.pose.pose.position.y = 2.0;
    odometry.pose.pose.position.z = 0.3;
    odometry.pose.pose.orientation.w = 1.0;

    const bool game_running = elapsed < 10.0;
    decision_process::msg::ReceiveData referee;
    referee.game_period = game_running ? 2U : 0U;
    referee.time = game_running ?
      static_cast<uint16_t>(std::max(0, 400 - static_cast<int>(elapsed))) : 0U;
    referee.hp_sentry = 400U;
    referee.defence_buff = 60U;
    referee.color = 0U;
    referee.ammo = 200U;
    referee.hp_outpost = 1000U;
    referee.hp_base = 5000U;
    referee.hp_enemy = {250U, 190U, 180U, 170U, 160U, 900U, 4500U, 350U};
    referee.radar_data = {5.0F, 5.0F, 6.0F, 5.0F, 7.0F, 5.0F,
      8.0F, 5.0F, 9.0F, 5.0F, 10.0F, 5.0F};

    decision_process::msg::AutoaimToDecision autoaim;
    autoaim.target.assign(9U, 0U);
    autoaim.target_distance.assign(9U, 0.0);
    autoaim.target_polar_r.assign(9U, 0.0);
    autoaim.target_polar_angle.assign(9U, 0.0);

    odometry_pub_->publish(odometry);
    referee_pub_->publish(referee);
    autoaim_pub_->publish(autoaim);
    RCLCPP_INFO(
      get_logger(), "INPUT task=1 t=%.1f period=%u position=[1.0,2.0]", elapsed,
      static_cast<unsigned int>(referee.game_period));

    if (!change_printed_ && !game_running) {
      change_printed_ = true;
      RCLCPP_WARN(get_logger(), "【检查】比赛结束，应输出归位目标 map [4.971,7.500,1.000]");
    }
    if (elapsed >= 15.0 && !finished_) {
      finished_ = true;
      timer_->cancel();
      rclcpp::shutdown();
    }
  }

  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odometry_pub_;
  rclcpp::Publisher<decision_process::msg::ReceiveData>::SharedPtr referee_pub_;
  rclcpp::Publisher<decision_process::msg::AutoaimToDecision>::SharedPtr autoaim_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  std::chrono::steady_clock::time_point start_time_;
  bool change_printed_{false};
  bool finished_{false};
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<ReturnHomeInputPublisher>());
  rclcpp::shutdown();
  return 0;
}
