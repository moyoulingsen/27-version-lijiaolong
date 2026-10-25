"""Wall-clock bounded vectorized recurrent PPO training."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import random
import signal
import time

import numpy as np
import torch

from rl.algorithms.ppo import RecurrentPPO, RecurrentRollout
from rl.config import AssaultConfig, NetworkConfig, PPOConfig, TrainingConfig
from rl.envs.sentry_assault import VectorSentryAssaultEnv
from rl.replay import ReplayRecorder
from .checkpoint import load_checkpoint, save_checkpoint
from .metrics import append_jsonl, write_json


def resolve_device(value: str) -> torch.device:
    if value == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(value)


def run_training(
    run_dir: Path,
    *,
    assault: AssaultConfig,
    network: NetworkConfig,
    ppo: PPOConfig,
    training: TrainingConfig,
    resume_checkpoint: Path | None = None,
) -> dict[str, object]:
    if run_dir.exists():
        raise FileExistsError(run_dir)
    checkpoint_dir = run_dir / "checkpoints"
    replay_dir = run_dir / "replays"
    checkpoint_dir.mkdir(parents=True)
    replay_dir.mkdir()
    metrics_path = run_dir / "metrics.jsonl"
    console_path = run_dir / "console.log"
    device = resolve_device(training.device)
    random.seed(training.seed)
    np.random.seed(training.seed)
    torch.manual_seed(training.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(training.seed)
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
        torch.set_float32_matmul_precision("high")

    vector_env = VectorSentryAssaultEnv(training.num_envs, assault)
    sample_env = vector_env.envs[0]
    learner = RecurrentPPO(
        sample_env.scalar_size,
        sample_env.spatial_shape,
        sample_env.critic_size,
        num_envs=training.num_envs,
        network=network,
        config=ppo,
        device=device,
    )
    rollout = RecurrentRollout(
        training.rollout_steps,
        training.num_envs,
        sample_env.scalar_size,
        sample_env.spatial_shape,
        sample_env.critic_size,
        lstm_layers=network.lstm_layers,
        recurrent_hidden=network.recurrent_hidden,
        device=device,
    )
    resume_payload = (
        load_checkpoint(resume_checkpoint, learner)
        if resume_checkpoint is not None
        else None
    )
    resume_global_step = int(resume_payload.get("global_step", 0)) if resume_payload else 0
    resume_episodes = int(resume_payload.get("episode", 0)) if resume_payload else 0
    resume_updates = int(resume_payload.get("update_round", 0)) if resume_payload else 0
    resume_successes = (
        int(resume_payload.get("successful_episodes", 0)) if resume_payload else 0
    )
    previous_elapsed = (
        float(resume_payload.get("elapsed_seconds", 0.0)) if resume_payload else 0.0
    )
    if (
        training.max_env_steps is not None
        and training.max_env_steps <= resume_global_step
    ):
        raise ValueError(
            "max_env_steps must be greater than the checkpoint global_step "
            f"({resume_global_step})"
        )
    metadata = {
        "schema": "single-sentry-assault-training-v1",
        "started_at": datetime.now().isoformat(),
        "device": str(device),
        "assault": asdict(assault),
        "network": asdict(network),
        "ppo": asdict(ppo),
        "training": asdict(training),
        "resumed_from": str(resume_checkpoint) if resume_checkpoint else None,
        "resume_global_step": resume_global_step,
        "resume_episode": resume_episodes,
        "reward": {
            "distance_progress": "(previous_distance - distance) * 0.5",
            "aim_progress": "(previous_angle_error - angle_error) * 0.2",
            "first_range": 2.0,
            "first_line_of_sight": 2.0,
            "collision": -0.02,
            "stuck_after_one_second": -0.05,
            "time_per_second": -0.01,
            "new_outpost_damage": 1.0,
            "new_base_damage": 1.0,
            "outpost_destroyed": "remaining_time * 10",
            "base_destroyed": "remaining_time * 20",
            "training_scale": assault.reward_scale,
        },
    }
    write_json(run_dir / "metadata.json", metadata)

    def log(message: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
        print(line, flush=True)
        with console_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    stop_requested = False

    def request_stop(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    observations = vector_env.reset(
        seed=training.seed + resume_episodes * training.num_envs
    )
    episode_returns = np.zeros(training.num_envs, dtype=np.float64)
    episode_scores = np.zeros(training.num_envs, dtype=np.float64)
    episode_objective_scores = np.zeros(training.num_envs, dtype=np.float64)
    episode_shaping_scores = np.zeros(training.num_envs, dtype=np.float64)
    episodes = resume_episodes
    successful_episodes = resume_successes
    global_step = resume_global_step
    update_round = resume_updates
    session_start_step = global_step
    start = time.monotonic()
    deadline = start + training.duration_hours * 3600.0
    next_log = start + training.log_seconds
    next_checkpoint = start + training.checkpoint_minutes * 60.0
    recorder = ReplayRecorder(replay_dir)
    recorder.start(
        episodes + 1,
        seed=training.seed + episodes * training.num_envs,
        metadata=metadata,
    )
    log(
        f"training started device={device} envs={training.num_envs} "
        f"duration={training.duration_hours:.2f}h "
        f"max_env_steps={training.max_env_steps or 'unbounded'} "
        f"resume_step={resume_global_step} resume_episode={resume_episodes}"
    )
    latest_stats = None
    try:
        while (
            (
                global_step < training.max_env_steps
                if training.max_env_steps is not None
                else time.monotonic() < deadline
            )
            and not stop_requested
        ):
            decision = learner.act(observations)
            transitions = vector_env.step(decision.actions)
            terminal_observations = tuple(item.observation for item in transitions)
            next_values = learner.value(
                terminal_observations,
                decision.next_state,
                reset=torch.zeros(training.num_envs, dtype=torch.bool),
            )
            rollout.add(
                scalar=np.stack([item.scalar for item in observations]),
                spatial=np.stack([item.spatial for item in observations]),
                critic=np.stack([item.critic for item in observations]),
                categorical_actions=decision.categorical,
                continuous_actions=decision.continuous,
                log_probabilities=decision.log_probabilities,
                values=decision.values,
                next_values=next_values,
                rewards=np.asarray([item.reward for item in transitions], dtype=np.float32),
                terminated=np.asarray([item.terminated for item in transitions]),
                truncated=np.asarray([item.truncated for item in transitions]),
                episode_starts=np.asarray([item.recurrent_reset for item in observations]),
                initial_state=decision.initial_state,
            )
            global_step += training.num_envs
            episode_returns += np.asarray([item.reward for item in transitions])
            episode_scores += np.asarray([item.raw_reward for item in transitions])
            episode_objective_scores += np.asarray(
                [item.info["objective_score"] for item in transitions]
            )
            episode_shaping_scores += np.asarray(
                [item.info["shaping_score"] for item in transitions]
            )
            recorder.write(
                {
                    "type": "frame",
                    "action": asdict(decision.actions[0]),
                    "reward": transitions[0].raw_reward,
                    "state": vector_env.envs[0].replay_state(),
                }
            )
            next_observations = list(terminal_observations)
            for index, transition in enumerate(transitions):
                if not (transition.terminated or transition.truncated):
                    continue
                episodes += 1
                successful_episodes += int(transition.terminated)
                append_jsonl(
                    metrics_path,
                    {
                        "type": "episode",
                        "episode": episodes,
                        "env_index": index,
                        "global_step": global_step,
                        "return": float(episode_returns[index]),
                        "raw_score": float(episode_scores[index]),
                        "objective_score": float(episode_objective_scores[index]),
                        "shaping_score": float(episode_shaping_scores[index]),
                        "success": bool(transition.terminated),
                        "remaining_time": transition.info["remaining_time"],
                    },
                )
                log(
                    f"episode={episodes} total_score={episode_scores[index]:+.3f} "
                    f"shaping={episode_shaping_scores[index]:+.3f} "
                    f"objective={episode_objective_scores[index]:+.1f} "
                    f"success={bool(transition.terminated)} "
                    f"remaining={float(transition.info['remaining_time']):.1f}s"
                )
                episode_returns[index] = 0.0
                episode_scores[index] = 0.0
                episode_objective_scores[index] = 0.0
                episode_shaping_scores[index] = 0.0
                next_observations[index] = vector_env.reset_at(
                    index,
                    seed=training.seed + episodes * training.num_envs + index,
                )
                if index == 0:
                    recorder.close()
                    if (
                        training.max_env_steps is None
                        or global_step < training.max_env_steps
                    ):
                        recorder.start(
                            episodes + 1,
                            seed=training.seed + episodes * training.num_envs,
                            metadata=metadata,
                        )
            observations = tuple(next_observations)
            if rollout.full:
                latest_stats = learner.update(rollout)
                rollout.clear()
                update_round += 1
                append_jsonl(
                    metrics_path,
                    {
                        "type": "update",
                        "update": update_round,
                        "global_step": global_step,
                        **asdict(latest_stats),
                    },
                )
            now = time.monotonic()
            if now >= next_log:
                elapsed = now - start
                success_rate = successful_episodes / max(1, episodes)
                log(
                    f"steps={global_step} episodes={episodes} success={success_rate:.3f} "
                    f"updates={update_round} "
                    f"speed={(global_step - session_start_step) / max(elapsed, 1e-6):.1f} step/s"
                )
                next_log = now + training.log_seconds
            if now >= next_checkpoint:
                save_checkpoint(
                    checkpoint_dir / "latest.pt",
                    learner=learner,
                    global_step=global_step,
                    episode=episodes,
                    update_round=update_round,
                    successful_episodes=successful_episodes,
                    elapsed_seconds=previous_elapsed + now - start,
                    metadata=metadata,
                )
                next_checkpoint = now + training.checkpoint_minutes * 60.0
    finally:
        recorder.close()
    elapsed = time.monotonic() - start
    save_checkpoint(
        checkpoint_dir / "final.pt",
        learner=learner,
        global_step=global_step,
        episode=episodes,
        update_round=update_round,
        successful_episodes=successful_episodes,
        elapsed_seconds=previous_elapsed + elapsed,
        metadata=metadata,
    )
    summary = {
        "global_step": global_step,
        "episodes": episodes,
        "successful_episodes": successful_episodes,
        "success_rate": successful_episodes / max(1, episodes),
        "updates": update_round,
        "elapsed_seconds": elapsed,
        "cumulative_elapsed_seconds": previous_elapsed + elapsed,
        "resumed_from": str(resume_checkpoint) if resume_checkpoint else None,
        "max_env_steps": training.max_env_steps,
        "stopped_by_signal": stop_requested,
        "latest_update": asdict(latest_stats) if latest_stats is not None else None,
    }
    write_json(run_dir / "summary.json", summary)
    log(f"training finished steps={global_step} episodes={episodes}")
    return summary


__all__ = ["resolve_device", "run_training"]
