# RMUC 2026 单哨兵强化学习

红方哨兵从真实出生点出发，不依赖导航器、行为树、路径点或自动瞄准，直接控制八方向移动、底盘转速、云台转速、三种姿态、强化模式和开火，依次摧毁蓝方前哨与基地。

算法采用 PyTorch、CNN + MLP + LSTM、独立 Critic、PPO、GAE 和 value bootstrap。GPU训练使用批量张量环境，CPU环境作为真实规则参考实现和最终验证环境。

## 目录

```text
RL/
├── pyproject.toml
├── configs/                    # 配置说明与后续配置预设
├── scripts/                    # 一键训练、评估、回放
├── src/rl/
│   ├── cli/                    # 命令入口
│   ├── config/                 # 类型化环境、网络、PPO配置
│   ├── envs/sentry_assault/    # CPU/GPU环境、地图、局部观测
│   ├── algorithms/ppo/         # PPO、GAE、rollout、动作分布
│   ├── models/                 # CNN/MLP/LSTM Actor-Critic
│   ├── runners/                # 训练、评估、检查点、指标
│   └── replay/                 # JSONL/SQLite记录和Pygame回放
├── tests/                      # CPU/GPU对拍和产物检查
└── artifacts/
    ├── models/sentry_v1/       # 已发布模型
    ├── replays/sentry_v1/      # 已验证成功回放
    └── runs/                   # 完整实验记录
```

源码与训练产物严格分离。新的训练运行统一写入 `RL/artifacts/runs/`。

## 安装

```bash
cd /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/pygame_sim_v2
source .venv-rl/bin/activate
python -m pip install -e RL
```

安装后可以使用 `rl-train`、`rl-evaluate`、`rl-monitor` 和 `rl-replay`，也可以使用对应的 `python -m rl...` 命令。

## 动作与观测

Actor动作：停止/八方向移动、连续底盘转速、连续云台转速、三种姿态、强化模式和开火。

Actor观测：37维标量状态和 `6×41×41` 局部地图。Critic额外使用25维训练期全局状态，但全局状态不会进入Actor动作链路。

## 奖励

奖励实现在 `src/rl/envs/sentry_assault/cpu_env.py` 与GPU等价实现中，数值统一来自 `src/rl/config/sentry_assault.py`。

核心目标奖励：

```text
建筑有效伤害              +5 / HP
每个建筑首次命中          +250
摧毁前哨                  +5000 + 剩余时间×10
摧毁基地                  +10000 + 剩余时间×20
```

攻击桥接奖励：发现目标、进入射程、在正确条件下开火、首次有效开火和持续有效开火。远距离无效开火轻微扣分，首次触发永久热量锁扣 `-1000`。

移动奖励只评价刷新本局最近距离、探索新网格、脱困和碰撞，不提供固定路线、导航点或下一步动作。

## 训练

完整比赛仍为420秒、物理步长0.1秒，但训练不等待现实时间。

```bash
./RL/scripts/train_sentry.sh \
  --num-envs 512 \
  --rollout-steps 256 \
  --duration-hours 2 \
  --run-name sentry_experiment
```

等价命令：

```bash
python -m rl.cli.train \
  --backend gpu \
  --device cuda \
  --curriculum \
  --num-envs 512 \
  --rollout-steps 256 \
  --duration-hours 2
```

断点续训：

```bash
python -m rl.cli.train \
  --resume RL/artifacts/runs/<run_name> \
  --max-env-steps 1000000000 \
  --num-envs 512 \
  --rollout-steps 256 \
  --duration-hours 2
```

## 已发布模型

```text
RL/artifacts/models/sentry_v1/final.pt
RL/artifacts/models/sentry_v1/validation.json
RL/artifacts/replays/sentry_v1/
```

该模型在CPU参考环境完整红方出生场景中正式验证10局全部通关，平均约56秒结束比赛。

PPO最终策略使用随机动作采样。部署和正式评估必须使用 `--stochastic`；纯argmax模式仅用于诊断，因为它可能在障碍边缘反复选择同一最大概率方向。

```bash
./RL/scripts/evaluate_sentry.sh \
  RL/artifacts/models/sentry_v1/final.pt \
  --episodes 10 \
  --device cuda
```

## Pygame回放

```bash
./RL/scripts/replay_sentry.sh \
  RL/artifacts/replays/sentry_v1/episode_000001.sqlite
```

按键：空格暂停，左右键逐帧，`+/-`调整速度，`Home/End`跳转，`Esc`退出。
