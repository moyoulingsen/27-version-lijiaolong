# 第二层：预设话题场景验证

## 第一个回归：比赛结束后返航

该场景持续 15 秒，并直接加载生产行为树 `decision_master.xml`：

- 前 10 秒持续发布 `game_period=2`，模拟比赛进行中；
- 机器人定位固定为 `(1.0, 2.0)`，不会模拟移动反馈；
- 第 8、9 秒在终端显示“注意检查”倒计时；
- 第 10 秒将 `game_period` 切换为 `0`，模拟比赛结束；
- 重点观察 `/serial_send_data.posture` 是否从 `1` 变为 `3`；
- 重点观察是否开始发布 `map` 坐标系下的返航目标 `(4.971, 7.5, 1.0)`；
- 第 15 秒打印观察汇总并自动结束。
- 输入发布器只发布 `/state_estimation`、`/serial_receive_data`、`/autoaim_to_decision`。
- 输出监视器只打印 `/goal_pose`、`/serial_send_data`、`/decision_to_autoaim`。
- 输入与输出周期均设置为 0.1 秒，终端保留完整 INPUT、RX、TX 消息流。
- 仅在比赛结束前约 1 秒以及输入切换时插入中文提醒。
- 不使用专用测试行为树，不自动判断通过或失败。
- 结束时只打印建议人工检查的数据指标。

发布器和监视器彼此独立，二者都不实现生产决策逻辑。最终结果需要人工阅读
Shell 消息流确认。

## 构建并运行

推荐直接执行一键脚本：

```bash
bash /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/tools/run_return_home_message_flow.sh
```

下面的命令是脚本内部执行步骤，通常不需要再手工逐条输入。

当前源码目录曾从 `决策` 改名为 `decision`，原来的 `build` 目录仍保存旧绝对路径；
同时 ROSIDL 对包含中文的工作区路径兼容性不好。因此使用纯英文验证工作区，
只软链接 `src`，让构建产物与原工作区完全分开。

```bash
unset COLCON_PREFIX_PATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH
source /opt/ros/jazzy/setup.bash

mkdir -p /home/lijiaolong/decision_process_verify_ws
ln -sfnT \
  /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/src \
  /home/lijiaolong/decision_process_verify_ws/src

cd /home/lijiaolong/decision_process_verify_ws

colcon build \
  --packages-select decision_process \
  --packages-ignore behaviortree_cpp && \
source /home/lijiaolong/decision_process_verify_ws/install/setup.bash && \
ros2 launch decision_process test_return_home_message_flow.launch.py
```

使用 `&&` 是为了保证构建失败时不会继续加载旧安装包或启动旧节点。
