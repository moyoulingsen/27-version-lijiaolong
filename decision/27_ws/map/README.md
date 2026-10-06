# RM 决策平面仿真

该目录是一个独立的 ROS 2 功能包 `rm_decision_sim`，用来联调已有的 5 棵 BehaviorTree.CPP 决策树。

## 技术链路

| 职责 | 实现 |
| --- | --- |
| 物理仿真 | Gazebo Harmonic (`gz sim 8`)，含差速底盘、激光雷达、碰撞体 |
| 导航 | ROS 2 Nav2，全局 `NavfnPlanner` 开启 A*，局部 DWB 控制 |
| 定位 | Gazebo 轮速里程计 + 2D LiDAR + Nav2 AMCL |
| 可视化 | RViz2 显示地图、机器人、扫描、代价地图、路径和验证状态 |
| 行为控制 | 原有 `decision_process` 节点和 5 个 BehaviorTree.CPP XML |

`nav_goal_adapter.py` 只将现有 `/goal_pose` 转为 Nav2 `NavigateToPose` Action，不产生新决策。`rm_map_simulator.py` 只模拟裁判系统和自矄输入，并根据实际位姿与决策输出判定场景是否通过。

## 地图与数据

场地是 28 m x 15 m。前哨站和基地为带碰撞的圆柱，机器人为长方体。敌方机器人在第一版中是静止模型。

默认数据来自 `data/rmuc_2026_region_dataset.sqlite` 的 `game_id=1778631047459`：

- 6 个蓝方机器人的坐标、类型和血量取开局第 1 秒快照。
- 基地和前哨站血量取数据集，前哨站血量按任务接口上限归一到 1000。
- 数据集中所有基地/前哨站坐标都是 `(0,0,0)`，因此建筑使用对称场地坐标布置。
- 数据溯源和实体数值记录在 `config/dataset_snapshot.yaml`。

Gazebo 世界在 `worlds/rm_arena.sdf`，Nav2 占据地图由 `scripts/generate_map.py` 按相同几何生成。

## 依赖

当前系统已有 Gazebo Harmonic、`ros_gz` 和 RViz2。Nav2 需安装：

```bash
sudo apt update
sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup
```

## 构建

```bash
cd /home/lijiaolong/桌面/27-version-lijiaolong/决策/27_ws
bash map/build_simulation.sh
source ~/.ros/decision_27_ws_nav2/install/setup.bash
```

构建脚本会使用 `~/.ros/decision_27_ws_nav2` 英文路径、系统 `/usr/bin/colcon` 并显式指定 `/usr/bin/python3`，既避免 ROSIDL 在中文路径下失败，也避免 Conda Python 3.13 与 ROS 2 Jazzy Python 3.12 的消息类型 ABI 冲突。

## 运行单个场景

```bash
ros2 launch rm_decision_sim simulation.launch.py scenario:=attack_outpost
```

`scenario` 可选值：

| 值 | XML | 自动验证点 |
| --- | --- | --- |
| `return_home` | `01_return_home.xml` | 比赛退出进行阶段后回到 `(4.971,7.5)` |
| `posture` | `02_posture_switch.xml` | 进行阶段输出移动姿态 `3` |
| `attack_outpost` | `03_attack_outpost.xml` | Nav2 到 `(16,11)`，选择 6 号、射击、前哨站归零 |
| `no_ammo` | `04_no_ammo.xml` | 产生待领弹量后到 `(2,1)` 领取 100 发 |
| `dodge` | `05_dodge.xml` | 视野外受伤后移动，安全期后恢复普通目标 |

运行时可查看机读状态：

```bash
ros2 topic echo /simulation/status
```

如果只要检查 Gazebo 世界、机器人和传感器，不启动 Nav2/决策节点：

```bash
ros2 launch rm_decision_sim gazebo_only.launch.py
```

## 批量验证 5 棵树

```bash
bash map/validate_all.sh
```

脚本使用无界面 Gazebo，每个场景最长 100 秒，最后输出 `Result: 5/5 scenarios passed`。失败时会保留 `/tmp/rm_<scenario>.*.log` 便于定位。
