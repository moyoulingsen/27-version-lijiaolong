#include <algorithm>
#include <chrono>
#include <cstdint>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"

#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

/*
- 节点职责：只按时间发布定位、裁判系统和自瞄输入，不订阅决策输出。
- 0~10 秒：game_period=2，机器人位置固定在 (1.0, 2.0)。
- 第 10 秒：game_period 从 2 切换为 0，模拟比赛结束。
- 发布周期：0.1 秒，即 10 Hz。
- 本节点不包含返航判断，不自动判定测试通过或失败。
 */
class ReturnHomeInputPublisher : public rclcpp::Node
{
public:
  ReturnHomeInputPublisher()
  : Node("return_home_input_publisher"),
    start_time_(std::chrono::steady_clock::now())
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    const auto reliable_qos = rclcpp::QoS(rclcpp::KeepLast(10)).reliable();

    odometry_pub_ = create_publisher<nav_msgs::msg::Odometry>(
      "/state_estimation", sensor_qos);
    referee_pub_ = create_publisher<decision_process::msg::ReceiveData>(
      "/serial_receive_data", reliable_qos);
    autoaim_pub_ = create_publisher<decision_process::msg::AutoaimToDecision>(
      "/autoaim_to_decision", sensor_qos);

    timer_ = create_wall_timer(100ms, std::bind(&ReturnHomeInputPublisher::publishFrame, this));

    RCLCPP_INFO(get_logger(), "========== 回归 1 输入发布器 ==========");
    RCLCPP_INFO(get_logger(), "使用真实 decision_master.xml，输入输出周期均为 0.1 秒");
    RCLCPP_INFO(get_logger(), "前 10 秒比赛进行中，第 10 秒模拟比赛结束");
  }

private:
  static constexpr double kMatchRunningSeconds = 10.0;
  static constexpr double kScenarioSeconds = 15.0;
  static constexpr double kRobotX = 1.0;
  static constexpr double kRobotY = 2.0;

  double elapsedSeconds() const
  {
    return std::chrono::duration<double>(
      std::chrono::steady_clock::now() - start_time_).count();
  }

  void publishFrame()
  {
    const double elapsed = elapsedSeconds();

    if (!change_warning_printed_ && elapsed >= 9.0) {
      change_warning_printed_ = true;
      RCLCPP_WARN(get_logger(), "【注意检查】约 1 秒后比赛结束，准备观察总体消息流变化");
    }

    nav_msgs::msg::Odometry odometry;
    odometry.header.stamp = now();
    odometry.header.frame_id = "map";
    odometry.child_frame_id = "base_link";
    odometry.pose.pose.position.x = kRobotX;
    odometry.pose.pose.position.y = kRobotY;
    odometry.pose.pose.position.z = 0.3;
    odometry.pose.pose.orientation.w = 1.0;

    const bool game_running = elapsed < kMatchRunningSeconds;
    const int elapsed_whole_seconds = static_cast<int>(elapsed);
    decision_process::msg::ReceiveData referee;
    referee.game_period = game_running ? 2U : 0U;
    referee.time = game_running ?
      static_cast<uint16_t>(std::max(0, 400 - elapsed_whole_seconds)) : 0U;
    referee.hp_sentry = 400U;
    referee.defence_buff = 60U;
    referee.color = 0U;
    referee.ammo = 200U;
    referee.hp_outpost = 1000U;
    referee.hp_base = 5000U;
    referee.hp_enemy = {250U, 190U, 180U, 170U, 160U, 900U, 4500U, 350U};
    referee.radar_data = {
      5.0F, 5.0F, 6.0F, 5.0F, 7.0F, 5.0F,
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
      get_logger(),
      "INPUT t=%.1fs /state_estimation frame=map xyz=[%.2f, %.2f, %.2f]",
      elapsed, odometry.pose.pose.position.x, odometry.pose.pose.position.y,
      odometry.pose.pose.position.z);
    RCLCPP_INFO(
      get_logger(),
      "INPUT t=%.1fs /serial_receive_data period=%u time=%u hp=%u ammo=%u enemy_outpost_hp=%u",
      elapsed, static_cast<unsigned int>(referee.game_period),
      static_cast<unsigned int>(referee.time),
      static_cast<unsigned int>(referee.hp_sentry),
      static_cast<unsigned int>(referee.ammo),
      static_cast<unsigned int>(referee.hp_enemy[5]));
    RCLCPP_INFO(
      get_logger(),
      "INPUT t=%.1fs /autoaim_to_decision targets=[0,0,0,0,0,0,0,0,0]", elapsed);

    if (!change_marker_printed_ && !game_running) {
      change_marker_printed_ = true;
      RCLCPP_WARN(
        get_logger(),
        "【注意检查】比赛结束输入已经发出：game_period=0，请观察后续 TX 输出");
    }

    if (elapsed >= kScenarioSeconds && !finished_) {
      finished_ = true;
      printSuggestedMetrics();
      timer_->cancel();
      rclcpp::shutdown();
    }
  }

  void printSuggestedMetrics()
  {
    RCLCPP_INFO(get_logger(), "========== 建议人工检查的数据指标 ==========");
    RCLCPP_INFO(get_logger(), "1. INPUT 与 TX 相邻消息时间戳间隔是否约为 0.1 秒");
    RCLCPP_INFO(get_logger(), "2. 0~10 秒 period 是否持续为 2，定位是否始终为 (1.0, 2.0)");
    RCLCPP_INFO(get_logger(), "3. 第 10 秒 period 是否由 2 变为 0");
    RCLCPP_INFO(get_logger(), "4. 比较切换前后的 posture、target、shoot、tripod 和 goal_pose");
    RCLCPP_INFO(get_logger(), "5. 检查返航目标是否为 map [4.971, 7.500, 1.000]");
    RCLCPP_INFO(get_logger(), "6. 比较 period=0 输入与首个返航输出的时间戳，观察响应延迟");
    RCLCPP_INFO(get_logger(), "本程序不判断通过或失败，请根据完整 Shell 消息流人工确认");
  }

  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odometry_pub_;
  rclcpp::Publisher<decision_process::msg::ReceiveData>::SharedPtr referee_pub_;
  rclcpp::Publisher<decision_process::msg::AutoaimToDecision>::SharedPtr autoaim_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  std::chrono::steady_clock::time_point start_time_;
  bool change_warning_printed_{false};
  bool change_marker_printed_{false};
  bool finished_{false};
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<ReturnHomeInputPublisher>());
  rclcpp::shutdown();
  return 0;
}
