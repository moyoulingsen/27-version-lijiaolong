# 消息端回归测试（任务 1～10）

本目录使用真实 `decision_master.xml` 和真实 `decision_process` 节点。每个任务只模拟上游的定位、裁判系统和自瞄消息，共用一个输出监视器打印 `/goal_pose`、`/serial_send_data` 和 `/decision_to_autoaim`。测试不自动判定通过或失败，需要根据时间线人工检查输出。

## 目录

| 目录 | 测试任务 | 输入时间线 |
| --- | --- | --- |
| `01_return_home/` | 归位 | 第 10 秒将 `game_period` 从 2 改为 0 |
| `02_posture/` | 姿态 | 前哨存活时姿态 1，前哨摧毁后进入普通移动姿态 3 |
| `03_attack_outpost/` | 打前哨 | 导航到 `(16,11)`，先搜索，再锁定射击，最后前哨血量归零 |
| `04_no_ammo/` | 无弹补给 | 无储备时去站桩点，产生 100 发储备后去补给点，弹量增加后退出 |
| `05_dodge/` | 躲避 | 先到达攻击点，随后在无可见敌人时掉血，观察连续短距离躲避 |
| `06_patrol/` | 巡逻 | 依次到达三个 XML 点位，再沿原路线反向返回 |
| `07_spin_control/` | 小陀螺 | 己方前哨血量由 1000 变 0，观察 spin 从 0 变 1 |
| `08_gimbal_control/` | 云台 | 搜索、锁定射击和丢失目标三个阶段切换 tripod |
| `09_low_health_recovery/` | 回血 | hp 低于 200 前往补给点，恢复后返回巡逻 |
| `10_health_threshold_parameter/` | XML 阈值 | 使用 260 阈值验证 250 触发、270 释放 |
| `common/` | 公共代码 | 十个任务共用的决策输出监视器 |

每个任务目录包含自己的输入发布器和独立 launch。外层 `test_decision_message_flow.launch.py` 是统一入口，通过 `scenario` 选择任务，避免多个测试同时向相同话题发布数据。

## 一键启动

以下脚本会自动隔离 ROS 域、准备纯英文验证工作区、构建 `decision_process` 并启动对应测试，不需要手工执行 `colcon build` 或 `source`。

## 观察工具

在另一个终端运行：

```bash
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_decision_message_flow_observer.sh
```

十个测试均为 10 Hz，输入发布器结束后 launch 自动关闭。重点比较每条 `INPUT task=N` 日志前后的 `TX` 输出变化。

### 独立启动

```bash
# 任务1：归位
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_return_home_message_flow.sh

# 任务2：姿态
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_posture_message_flow.sh

# 任务3：打前哨
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_attack_outpost_message_flow.sh

# 任务4：无弹补给
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_no_ammo_message_flow.sh

# 任务5：躲避
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_dodge_message_flow.sh

# 任务6～10
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_patrol_message_flow.sh
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_spin_control_message_flow.sh
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_gimbal_control_message_flow.sh
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_low_health_recovery_message_flow.sh
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_health_threshold_parameter_message_flow.sh
```

### 总启动

```bash
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_all_decision_message_flows.sh
```

总脚本只构建一次，然后按照任务 1 到任务 10 的顺序串行执行。由于十个测试使用相同的 ROS 话题，不能同时启动，否则不同输入发布器会互相干扰。

通用入口也可以直接指定编号或名称：

```bash
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_decision_message_flow.sh 3
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_decision_message_flow.sh dodge
```

## 构建

```bash
cd /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select decision_process --packages-ignore behaviortree_cpp
source install/setup.bash
```

如果中文路径影响构建，继续使用现有的英文验证工作区脚本。

## 总 launch

任务编号和名称都可以使用：

```bash
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=1
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=posture
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=attack_outpost
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=no_ammo
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=dodge
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=patrol
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=spin_control
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=gimbal_control
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=low_health_recovery
ros2 launch decision_process test_decision_message_flow.launch.py scenario:=health_threshold_parameter
```

名称对应关系：`1=return_home`、`2=posture`、`3=attack_outpost`、`4=no_ammo`、`5=dodge`、`6=patrol`、`7=spin_control`、`8=gimbal_control`、`9=low_health_recovery`、`10=health_threshold_parameter`。

## 独立 launch

```bash
ros2 launch decision_process test_return_home_message_flow.launch.py
ros2 launch decision_process test_posture_message_flow.launch.py
ros2 launch decision_process test_attack_outpost_message_flow.launch.py
ros2 launch decision_process test_no_ammo_message_flow.launch.py
ros2 launch decision_process test_dodge_message_flow.launch.py
```

