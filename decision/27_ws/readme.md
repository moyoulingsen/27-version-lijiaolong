## workspace

src：行为树的xml，cpp存放的地方

pygame_sim：完成初版简化任务2d地图
pygame_sim2：服务于完整比赛链路，用于训练2d RL的地图。

tools：脚本储存地方，包括启动pygame的脚本，ai验证自检的脚本，启动pygame和cpp桥接的脚本等等

启动命令：
cd "/home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/pygame_sim_v2"
bash run_pygame_sim_v2.sh

## 赛场记录与赛后复现

### 1. 编译并启动

终端 A：先启动 Pygame 仿真器，并在界面中开始比赛。

```bash
cd "/home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/pygame_sim_v2"
bash run_pygame_sim_v2.sh
```

终端 B：启动 ROS 桥、决策节点和自动录包。

```bash
cd "/home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws"
bash tools/build_wsl_workspace.sh
source /opt/ros/jazzy/setup.bash
source "$HOME/.ros/decision_27_ws_runtime/install/setup.bash"
ros2 launch decision_process integrated_sim.launch.py
```

只启动终端 B 时，录包程序仍会建立目录，但由于没有仿真数据输入，`ros2 bag info` 会显示 `Messages: 0`。

启动后会自动产生两类记录：

- 行为树状态记录：`$HOME/.ros/decision_logs/*.btlog`
- ROS 输入输出录包：`$HOME/.ros/decision_bags/match_*/`

终端显示 `Behavior tree log: ...btlog` 和 `Recording...` 即表示两种记录均已启动。比赛或测试结束时用 `Ctrl+C` 退出，保证 rosbag 正常写入元数据。

### Groot2 实时查看节点状态

决策节点启动时会显示：

```text
Groot2 live monitor: 127.0.0.1:1667
```

打开 Groot2，进入 `Monitor`，连接地址 `127.0.0.1`、端口 `1667`。连接成功后即可实时看到节点在 `IDLE/RUNNING/SUCCESS/FAILURE` 之间切换。

本机目前没有检测到 Groot2 可执行程序，需要先安装 Groot2。Groot 1 不适用于当前 BehaviorTree.CPP 4，不要混用。

如果临时不想录包：

```bash
ros2 launch decision_process integrated_sim.launch.py record_bag:=false
```

### 2. 检查记录是否成功

```bash
ls -lh "$HOME/.ros/decision_logs"
latest_bag=$(ls -dt "$HOME"/.ros/decision_bags/match_* | head -n 1)
echo "$latest_bag"
ros2 bag info "$latest_bag"
```

`ros2 bag info` 应显示 `/serial_receive_data`、`/autoaim_to_decision`、`/state_estimation` 以及各决策输出话题的消息数。`.btlog` 可在 Groot2 的日志回放功能中打开，查看每个节点的 `RUNNING/SUCCESS/FAILURE` 变化。

### 3. 赛后回放验证

先关闭正在运行的仿真器、串口节点和旧的决策节点，避免它们同时发布数据。

终端 A：只启动决策节点，并将输出重映射到回放话题，防止误控真车。

```bash
source /opt/ros/jazzy/setup.bash
source "$HOME/.ros/decision_27_ws_runtime/install/setup.bash"
ros2 run decision_process decision_process --ros-args \
  -r /serial_send_data:=/replay/serial_send_data \
  -r /decision_to_autoaim:=/replay/decision_to_autoaim \
  -r /goal_pose:=/replay/goal_pose \
  -r /decision_goal_enabled:=/replay/decision_goal_enabled
```

终端 B：只回放行为树的输入，不回放原始输出。

```bash
latest_bag=$(ls -dt "$HOME"/.ros/decision_bags/match_* | head -n 1)
ros2 bag play "$latest_bag" \
  --topics /serial_receive_data /autoaim_to_decision \
  /state_estimation /tf /tf_static
```

终端 C：观察回放后的决策指令。

```bash
ros2 topic echo /replay/serial_send_data
ros2 topic echo /replay/goal_pose
```

回放结束后，再用 Groot2 打开新生成的 `.btlog`。若节点分支、选择目标和输出指令与比赛时一致，则复现验证通过。
