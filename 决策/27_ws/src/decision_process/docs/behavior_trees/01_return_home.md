# 01 归位子树 ReturnHome

## 任务目标

比赛结束后，存活的哨兵自动切换为移动姿态，并向启动点 `(4.971, 7.5)` 导航。

## 输入与输出

| 类型 | 字段 | 用途 |
| --- | --- | --- |
| 输入 | `game_period` | 记录比赛是否曾进入阶段 2，并判断是否已经退出比赛进行阶段 |
| 输入 | `time` | 仅作为计时信息；不能单独用 `time==0` 判断结束，因为赛前同样为 0 |
| 输入 | `hp_sentry` | 血量大于 0 时才允许执行移动归位 |
| 输入 | 定位 `x、y` | 计算哨兵与启动点的平面距离 |
| 输出 | `posture=3` | 归位使用移动姿态 |
| 输出 | `/goal_pose.position.x=4.971` | 启动点 x 坐标 |
| 输出 | `/goal_pose.position.y=7.5` | 启动点 y 坐标 |
| 输出 | `/goal_pose.position.z=1.0` | 任务规定的固定值 |
| 输出 | `/goal_pose.header.frame_id="map"` | 任务规定的地图坐标系 |

## 历史状态

必须保存 `has_started` 和 `has_finished`：

```text
game_period == 2:
    has_started = true
    has_finished = false

game_period != 2 && has_started:
    has_finished = true
```

不能使用当前一帧的 `game_period==0 && time==0` 直接判断比赛结束，否则赛前会误触发归位。

## 子树流程

```text
ReturnHome (ReactiveSequence)
├── GameFinished
├── SentryAlive
├── SetPosture(posture=3)
└── NavigateToPose
    ├── x=4.971
    ├── y=7.5
    ├── z=1.0
    ├── frame_id=map
    └── tolerance=0.15
```

## 节点状态

| 节点 | SUCCESS | FAILURE | RUNNING |
| --- | --- | --- | --- |
| `GameFinished` | 曾进入阶段 2，且当前已退出阶段 2 | 比赛未开始或仍在阶段 2 | 不使用 |
| `SentryAlive` | 已收到裁判数据且 `hp_sentry>0` | 未收到裁判数据或已阵亡 | 不使用 |
| `SetPosture` | 姿态值为 1～3，并已写入输出命令 | 姿态参数非法 | 不使用 |
| `NavigateToPose` | 定位有效且距离不大于容差 | 端口非法 | 尚未收到定位或尚未到达 |

到达判断：

```text
hypot(current_x - 4.971, current_y - 7.5) <= tolerance
```

## 中止行为

如果比赛重新进入阶段 2，`GameFinished` 变为 `FAILURE`，`ReactiveSequence` 会中止正在运行的 `NavigateToPose`，导航发布随即关闭。

## Groot2 文件

打开：

```text
behavior_trees/01_return_home.xml
```

`MainTree` 中归位子树必须位于 `AlwaysSuccess` 之前，否则后者会使归位分支永远无法执行。

## 来源检查

| 结论 | 来源 | 检查结果 |
| --- | --- | --- |
| 阶段 2 为比赛进行阶段，比赛可提前结束 | `任务说明1.md` 第 13 行 | 一致 |
| 赛前阶段 0 的 `time` 为 0 | `任务说明1.md` 第 13～14 行 | 不能只用 `time==0` |
| 启动点为 `(4.971,7.5)` | `任务说明1.md` 第 70 行 | 一致 |
| 比赛结束自动返回启动点 | `任务说明1.md` 第 77 行 | 一致 |
| 导航目标 z 固定为 1.0 | `任务说明1.md` 第 63 行 | 一致 |
| 导航参考坐标系固定为 `map` | `任务说明1.md` 第 64 行 | 一致 |
| 当前坐标来自 `/state_estimation` | `任务说明1.md` 定位模块表；`decision_process_node.cpp` 订阅实现 | 一致 |
| 目标通过 `/goal_pose` 发布 | `任务说明1.md` 导航模块表；`decision_process_node.cpp` 发布实现 | 一致 |

## 独立测试

- 赛前 `game_period=0,time=0`：不得触发归位。
- 进入阶段 2：记录比赛已经开始，但不得触发归位。
- 从阶段 2 切换到其他阶段：触发归位。
- 未收到定位：导航节点保持 `RUNNING`。
- 距启动点大于 0.15m：持续发布目标并返回 `RUNNING`。
- 距启动点不大于 0.15m：停止导航发布并返回 `SUCCESS`。
- 哨兵血量为 0：不发布归位目标。

ROS 联调可使用 C++ 测试发布器，避免 Python 消息类型支持版本影响：

```bash
ros2 run decision_process test_data_publisher \
  --ros-args -p simulate_return_home:=true
```

该模式依次发布约 1 秒赛前阶段、约 1 秒比赛阶段，随后退出比赛阶段并保持定位点 `(1,2)`，用于确认归位目标是否发布。

## 当前边界

- 当前只实现第 1 个任务，`AlwaysSuccess` 是后续 22 个任务的占位分支。
- 归位目标 yaw 暂设为 `0.0`，任务说明未指定最终朝向。
- 到达容差 `0.15m` 是工程参数，不是规则硬编码，可在 XML 中修改。

## 验证记录

验证日期：2026-10-04。

| 检查项 | 结果 |
| --- | --- |
| `decision_process` 编译 | 通过 |
| 行为树 XML 加载 | 通过，节点启动时成功加载 `01_return_home.xml` |
| `MatchLifecycle` 单元测试 | 通过 |
| 到达容差单元测试 | 通过 |
| 赛前 `period=0,time=0` 不误触发 | 通过 |
| 比赛阶段 2 退出后发布归位目标 | 通过 |
| `/goal_pose` 实际输出 | `frame=map, xyz=[4.97, 7.50, 1.00], yaw=0.0` |
