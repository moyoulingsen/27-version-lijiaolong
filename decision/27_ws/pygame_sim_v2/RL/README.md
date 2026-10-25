# RMUC 2026 单哨兵强化学习

训练好的最优切片
cd /home/lijiaolong/桌面/27-version-lijiaolong/decision/27_ws/pygame_sim_v2
source .venv-rl/bin/activate

./RL/scripts/replay_sentry.sh \
  RL/artifacts/runs/sentry_reward_v3_phasefix_20261025_121526/replays/episode_000001.sqlite


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

## 地图来源

训练不再读取旧PGM碰撞地图。Pygame、CPU参考环境和GPU张量环境统一从项目根目录的 `map_regions.json` 构建墙体、特殊墙、减速区、飞坡方向和隧道通道。`custom_6` 与 `custom_7` 是明确可通行的两条隧道，局部地图和GPU碰撞张量都会把通道显示为自由空间。

## 奖励

奖励实现在 `src/rl/envs/sentry_assault/cpu_env.py` 与GPU等价实现中，数值统一来自 `src/rl/config/sentry_assault.py`。

奖励通过编号长期保留，V1/V2不会被后续版本覆盖。

V1是已发布模型使用的原始密集引导奖励：

```text
建筑有效伤害              +5 / HP
每个建筑首次命中          +250
摧毁前哨                  +5000 + 剩余时间×10
摧毁基地                  +10000 + 剩余时间×20
```

攻击桥接奖励：发现目标、进入射程、在正确条件下开火、首次有效开火和持续有效开火。远距离无效开火轻微扣分，首次触发永久热量锁扣 `-1000`。

移动奖励只评价刷新本局最近距离、探索新网格、脱困和碰撞，不提供固定路线、导航点或下一步动作。

V2用于从V1 Actor进行效率微调：

```text
距离进步                  ×0.5
瞄准进步                  ×0.2
新探索网格                +0.01，单局上限1
建筑有效伤害              +1 / HP
摧毁前哨                  +剩余时间×10
摧毁基地                  +剩余时间×20
碰撞/持续卡住             -0.02 / -0.05
每秒时间成本              -0.01
首次永久热锁              -1000
```

V2没有距离里程碑、瞄准里程碑、开火里程碑、首次命中或固定摧毁奖金。

V3用于摆脱V2已经形成的下路和角落局部最优：

```text
到最近开放射位的可行路径进步       ×2.0
实际移动距离成本                   -0.5 / 米
首次命中前哨/基地                  +剩余时间×1.0 / ×0.5
开放射位有效开火                   +0.25 / 秒
射程内贴墙                         最高 -0.5 / 秒
超过8秒未造成建筑伤害              逐渐增加，最高 -0.6 / 秒
碰撞/持续卡住                      -0.05 / -0.10
```

“开放射位”是所有满足射程、碰撞和最小空间条件的地图网格集合，不是固定红点。
训练只查询预计算的最短可行距离作为奖励，Actor观测中没有路径、导航点或下一步动作。
因此上方隧道和开阔射位只有在确实更短、更高效时才会自然成为优解。V3成熟课程仍
保留30%的随机、目标附近和两条隧道出生，不再完全关闭路线探索。
其中上方隧道保持前哨存活，用于训练开局攻击路线；垂直隧道出生时前哨已摧毁，
只训练后半局基地攻击路线，避免两个阶段向共享移动策略提供冲突梯度。

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

V2从V1只继承Actor侧地图编码、LSTM和动作头；Critic、优化器、步数和运行时隐藏状态全部重新开始：

```bash
./RL/scripts/train_sentry.sh \
  --reward-version 2 \
  --warm-start RL/artifacts/models/sentry_v1/final.pt \
  --num-envs 1024 \
  --rollout-steps 128 \
  --duration-hours 2 \
  --run-name sentry_reward_v2
```

普通 `--resume` 只用于同一奖励编号继续训练；切换奖励编号必须使用 `--warm-start`。

V3建议从当前V2最终检查点继承感知、瞄准和开火能力，但重置移动方向动作头，避免
旧下路策略直接覆盖新奖励：

```bash
./RL/scripts/train_sentry.sh \
  --reward-version 3 \
  --warm-start RL/artifacts/runs/sentry_reward_v2_20261025_105111/checkpoints/final.pt \
  --reset-movement-head \
  --num-envs 1024 \
  --rollout-steps 128 \
  --duration-hours 2 \
  --run-name sentry_reward_v3
```

## 已发布模型

```text
RL/artifacts/models/sentry_v1/final.pt
RL/artifacts/models/sentry_v1/validation.json
RL/artifacts/replays/sentry_v1/
```

该模型此前在旧训练地图中验证10局全部通关，平均约56秒结束比赛。统一到当前Pygame V2地图后，它不再作为最终部署模型，只作为V2训练的Actor warm-start基础；当前V2地图回测3局未通关。

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

按键：空格暂停，左右键逐帧，短按 `+/-` 调整速度，长按 `+/-`
连续快进/快退，`Home/End` 跳转，`Esc` 退出。左右侧单位页签和属性卡可点击，
历史属性保持只读。
