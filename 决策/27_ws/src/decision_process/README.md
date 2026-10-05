# decision_process 决策节点

这个功能包提供 ROS 2 通信层，并开始按任务逐个接入 BehaviorTree.CPP 子树。

当前已经独立完成前 5 个任务：归位、姿态切换、打前哨、无弹量行为和躲避行为。每个任务都有单独的 Groot2 XML、逻辑说明和测试。

## 话题

### 订阅

| 话题 | 消息类型 |
| --- | --- |
| `/state_estimation` | `nav_msgs/msg/Odometry` |
| `/serial_receive_data` | `decision_process/msg/ReceiveData` |
| `/autoaim_to_decision` | `decision_process/msg/AutoaimToDecision` |

### 发布

| 话题 | 消息类型 |
| --- | --- |
| `/goal_pose` | `geometry_msgs/msg/PoseStamped` |
| `/serial_send_data` | `decision_process/msg/DesicionSendData` |
| `/decision_to_autoaim` | `decision_process/msg/DecisionToAutoaim` |

`/goal_pose` 默认不发布。只有将 `publish_goal` 参数设为 `true` 时才会发布，并且 `z` 固定为 `1.0`、`frame_id` 默认为 `map`。

行为树启用后，`NavigateToPose` 节点可以直接更新导航命令，不需要手动设置 `publish_goal` 参数。

## 已实现行为树

| 子树 | XML | 说明文档 |
| --- | --- | --- |
| 01 归位 | `behavior_trees/01_return_home.xml` | `docs/behavior_trees/01_return_home.md` |
| 02 姿态切换 | `behavior_trees/02_posture_switch.xml` | `docs/behavior_trees/02_posture_switch.md` |
| 03 打前哨 | `behavior_trees/03_attack_outpost.xml` | `docs/behavior_trees/03_attack_outpost.md` |
| 04 无弹量行为 | `behavior_trees/04_no_ammo.xml` | `docs/behavior_trees/04_no_ammo.md` |
| 05 躲避行为 | `behavior_trees/05_dodge.xml` | `docs/behavior_trees/05_dodge.md` |

归位触发方式不是简单判断 `time==0`，而是记录比赛曾经进入阶段 2，随后检测到退出阶段 2，避免赛前误触发。

打前哨子树先导航到 `(16,11)`，到点后指定 6 号前哨站；看不见目标时转动云台搜索，看见且有弹时射击，只有完整裁判数据明确报告 `hp_enemy[5]==0` 才释放后续行为。

## 完整字段处理

- `ReceiveData` 的 8 个标量字段、8 个敌方血量和 12 个雷达坐标值都会被保存。
- `AutoaimToDecision` 的 4 个长度为 9 的数组都会被保存。
- `Odometry` 的 xyz、完整四元数和解算后的 yaw 都会被保存。
- 输入数组长度不符合题目规定时，节点会输出警告而不会越界。
- 5 个电控输出字段、3 个自矄输出字段和完整导航目标都已实现。

输出值可以在节点运行时修改，例如：

```bash
ros2 param set /decision_process default_posture 1
ros2 param set /decision_process default_spin_mode 3
ros2 param set /decision_process default_target_number 8
ros2 param set /decision_process goal_x 16.0
ros2 param set /decision_process goal_y 11.0
ros2 param set /decision_process publish_goal true
```

## 编译

```bash
cd 决策/27_ws
bash tools/build_workspace.sh --packages-select decision_process
source tools/source_workspace.sh
```

工作区的上层目录含中文路径，ROS 2 Jazzy 的 `rosidl` 在该路径下直接生成消息会失败。`build_workspace.sh` 会将源码映射到 `~/.ros/decision_27_ws` 英文路径后编译，源代码仍然保存在本工作区内。

## 启动通信节点

```bash
ros2 launch decision_process communication.launch.py
```

也可以直接运行与功能包同名的决策节点：

```bash
ros2 run decision_process decision_process
```

## 自测全部话题

下面的 launch 会同时启动决策通信节点、模拟输入节点和输出监视节点：

```bash
ros2 launch decision_process communication_test.launch.py
```

也可以查看话题：

```bash
ros2 topic list
ros2 topic echo /serial_receive_data
ros2 topic echo /serial_send_data
ros2 topic echo /goal_pose
```

## 说明

- `test_data_publisher` 只用于没有真实裁判系统、自矄和定位节点时的联调。
- 传入 `simulate_return_home:=true` 可模拟比赛结束归位；传入 `simulate_attack_outpost:=true` 可模拟导航、搜索、射击和前哨摧毁流程。
- 传入 `simulate_no_ammo:=true` 可模拟无待领弹量站桩、每分钟弹量累计、前往补给点和领取成功。
- 传入 `simulate_dodge:=true` 可模拟正常到点、视野外受伤、连续躲避以及恢复正常行为。
- `output_monitor` 用来确认三个输出话题的消息确实已发布。
- 后续写决策逻辑时，可以更新 `serial_command_`、`autoaim_command_`和导航目标参数，不需要重写 ROS 2 通信接口。
