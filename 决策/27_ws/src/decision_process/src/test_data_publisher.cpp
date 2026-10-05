#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"

#include "decision_process/msg/autoaim_to_decision.hpp"
#include "decision_process/msg/receive_data.hpp"

using namespace std::chrono_literals;

/**
 * @brief 行为树联调使用的模拟输入发布节点。
 *
 * 本节点名称为 decision_test_data_publisher，以 10 Hz 发布三类输入：
 * 1. /state_estimation：模拟定位模块输出；
 * 2. /serial_receive_data：模拟裁判系统和电控上传数据；
 * 3. /autoaim_to_decision：模拟自瞄识别结果。
 *
 * 注意：本节点只负责制造输入，不会自动判断测试是否通过。
 * 实际结果需要通过 /goal_pose、/serial_send_data 和
 * /decision_to_autoaim 三个输出话题进行观察或断言。
 * 四个 simulate_* 参数建议每次只启用一个，避免不同场景的数据混合。
 */
class TestDataPublisher : public rclcpp::Node
{
public:
  TestDataPublisher()
  : Node("decision_test_data_publisher")
  {
    /**
     * 返航任务检测：
     * - 测试节点：GameFinished、SetPosture、NavigateToPose。
     * - 发布数据：game_period 在 0～1 秒为 0，1～2 秒为 2，2 秒后恢复为 0，
     *   用于模拟“赛前 -> 比赛进行 -> 比赛结束”的完整状态变化。
     * - 期望结果：赛前不返航；比赛结束后 /serial_send_data.posture 为 3，
     *   /goal_pose 发布哨兵起点 (4.971, 7.5, 1.0)，frame_id 为 map。
     */
    simulate_return_home_ = declare_parameter<bool>("simulate_return_home", false);

    /**
     * 攻击前哨站任务检测：
     * - 测试节点：GameRunning、EnemyOutpostAlive、ApplyPosture、
     *   NavigateToPose、EngageOutpost。
     * - 发布数据：1 秒后定位到攻击点 (16, 11)；2～3 秒自瞄识别 6 号前哨站；
     *   3 秒后 hp_enemy[5] 变为 0，模拟敌方前哨站被摧毁。
     * - 期望结果：先发布 (16, 11, 1.0) 导航目标；未识别前哨时转动云台且不射击；
     *   识别到前哨且有弹时 target 为 6、tripod_mode 为 0、shoot_mode 为 1；
     *   前哨摧毁后停止射击并清除目标。
     */
    simulate_attack_outpost_ = declare_parameter<bool>("simulate_attack_outpost", false);

    /**
     * 无弹量任务检测：
     * - 测试节点：OutOfAmmo、PendingAmmoAvailable、SetCombatIdle、
     *   ApplyPosture、NavigateToPose、CollectPendingAmmo。
     * - 发布数据：开始时 ammo 为 0；2 秒后比赛剩余时间从 420 变为 359，
     *   模拟第一分钟结束并产生 100 发待领取弹药；1 秒后定位到站桩点，
     *   4 秒后定位到补给点 (2, 1)，6 秒后 ammo 变为 100。
     * - 期望结果：无待领弹药时关闭射击并前往站桩点；产生待领弹药后前往补给点；
     *   收到 ammo 增加反馈后结束领弹动作。
     * - 前置条件：综合主树中攻击前哨任务优先级更高，执行本场景前必须确保
     *   hp_enemy[5] 为 0，或单独加载 04_no_ammo.xml，否则主树仍会执行攻击前哨任务。
     */
    simulate_no_ammo_ = declare_parameter<bool>("simulate_no_ammo", false);

    /**
     * 躲避任务检测：
     * - 测试节点：GameRunning、NoEnemyVisible、RecentDamage、
     *   NavigationGoalReached、SetCombatIdle、ApplyPosture、EvadeUntilSafe。
     * - 发布数据：自瞄 target 数组全部为 0；2 秒后 hp_sentry 从 400 降为 350；
     *   定位数据依次变化为 (5, 5)、(5, 5.8)、(5.8, 5.8)，模拟躲避移动反馈。
     * - 期望结果：满足“已到达原目标、视野无敌人、最近受到伤害”后，
     *   /goal_pose 连续发布地图范围内的躲避点；停止受伤超过 quiet_period_sec 后，
     *   EvadeUntilSafe 退出并停止躲避导航。
     * - 前置条件：必须先完成更高优先级的攻击前哨和无弹任务，并让当前导航目标
     *   处于已到达状态，否则综合主树不会进入 DodgeBehavior。
     */
    simulate_dodge_ = declare_parameter<bool>("simulate_dodge", false);
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
  /**
   * @brief 按场景经过时间生成并发布一帧模拟输入。
   *
   * 同一帧依次发布定位、裁判系统和自瞄消息，使行为树能够在连续 tick 中观察
   * 输入状态的变化。这里模拟的是上游消息，不代表仿真机器人已经真实执行输出。
   */
  void publishTestData()
  {
    nav_msgs::msg::Odometry odometry;
    odometry.header.stamp = now();
    odometry.header.frame_id = "map";
    odometry.child_frame_id = "base_link";
    const double elapsed = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - simulation_start_).count();
    // 定位反馈：根据当前测试场景模拟机器人在关键目标点之间的位置变化。
    if (simulate_dodge_ && elapsed >= 4.0) {
      odometry.pose.pose.position.x = 5.8;
      odometry.pose.pose.position.y = 5.8;
    } else if (simulate_dodge_ && elapsed >= 3.0) {
      odometry.pose.pose.position.x = 5.0;
      odometry.pose.pose.position.y = 5.8;
    } else if (simulate_dodge_ && elapsed >= 1.0) {
      odometry.pose.pose.position.x = 5.0;
      odometry.pose.pose.position.y = 5.0;
    } else if (simulate_no_ammo_ && elapsed >= 4.0) {
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

    // 裁判系统反馈：控制比赛阶段、血量、弹量以及敌方前哨站状态。
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
    referee.hp_sentry = simulate_dodge_ && elapsed >= 2.0 ? 350U : 400U;
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

    // 自瞄反馈：控制视野内是否存在目标以及 6 号前哨站是否被识别。
    decision_process::msg::AutoaimToDecision autoaim;
    autoaim.target = {1, 1, 1, 1, 1, 1, 1, 1, 1};
    if (simulate_dodge_) {
      autoaim.target.assign(9U, 0U);
    }
    if (simulate_attack_outpost_) {
      autoaim.target[6] = elapsed >= 2.0 && elapsed < 3.0 ? 1U : 0U;
    }
    autoaim.target_distance = {1.0, 2.1, 2.2, 2.3, 2.4, 2.5, 6.0, 7.0, 2.8};
    if (simulate_dodge_) {
      autoaim.target_distance.assign(9U, 0.0);
    }
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
  bool simulate_dodge_{false};
  std::chrono::steady_clock::time_point simulation_start_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<TestDataPublisher>());
  rclcpp::shutdown();
  return 0;
}
