# 任务8：云台控制

## 需求与实现

当当前决策同时给出有效目标编号和射击指令时，tripod_mode=0 停止云台转动；否则 tripod_mode=1，让云台持续 360 度搜索。

综合树使用 Parallel 同帧执行主行为和辅助控制。主行为先更新 target 与 shoot_mode，辅助支路随后计算 spin_mode 与 tripod_mode，并用 KeepRunning 保证每个 tick 都重新执行，而不是被并行节点记为已完成。

## 验证记录

验证日期：2026-10-06。

- 工程编译通过。
- 全部逻辑测试 45 项，0 错误、0 失败。
- 搜索阶段 target=6、shoot=0、tripod=1。
- 锁定阶段 target=6、shoot=1、tripod=0。
- 丢失目标后 shoot=0、tripod=1。
