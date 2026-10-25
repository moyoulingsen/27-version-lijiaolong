"""CUDA-native high-throughput trainer for the batched assault simulator."""

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
from rl.envs.sentry_assault import GpuSentryAssaultEnv
from .checkpoint import load_checkpoint, save_checkpoint
from .evaluator import evaluate_checkpoint
from .metrics import append_jsonl, write_json
from .trainer import resolve_device


def run_gpu_training(
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
    device = resolve_device(training.device)
    if device.type != "cuda":
        raise ValueError("GPU trainer requires a CUDA device")
    checkpoint_dir = run_dir / "checkpoints"
    replay_dir = run_dir / "replays"
    checkpoint_dir.mkdir(parents=True)
    replay_dir.mkdir()
    metrics_path = run_dir / "metrics.jsonl"
    console_path = run_dir / "console.log"

    random.seed(training.seed)
    np.random.seed(training.seed)
    torch.manual_seed(training.seed)
    torch.cuda.manual_seed_all(training.seed)
    torch.backends.cudnn.benchmark = True
    torch.set_float32_matmul_precision("high")

    env = GpuSentryAssaultEnv(training.num_envs, assault, device=device)
    learner = RecurrentPPO(
        env.scalar_size,
        env.spatial_shape,
        env.critic_size,
        num_envs=training.num_envs,
        network=network,
        config=ppo,
        device=device,
    )
    rollout = RecurrentRollout(
        training.rollout_steps,
        training.num_envs,
        env.scalar_size,
        env.spatial_shape,
        env.critic_size,
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
    resume_successes = int(resume_payload.get("successful_episodes", 0)) if resume_payload else 0
    previous_elapsed = float(resume_payload.get("elapsed_seconds", 0.0)) if resume_payload else 0.0
    if training.max_env_steps is not None and training.max_env_steps <= resume_global_step:
        raise ValueError(
            "max_env_steps must be greater than checkpoint global_step "
            f"({resume_global_step})"
        )
    metadata = {
        "schema": "single-sentry-assault-training-v2-gpu",
        "started_at": datetime.now().isoformat(),
        "backend": "gpu_tensor",
        "device": str(device),
        "assault": asdict(assault),
        "network": asdict(network),
        "ppo": asdict(ppo),
        "training": asdict(training),
        "resumed_from": str(resume_checkpoint) if resume_checkpoint else None,
        "resume_global_step": resume_global_step,
        "resume_episode": resume_episodes,
        "replay_policy": "final checkpoint evaluated in CPU reference environment",
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
    env.set_curriculum_progress(
        resume_global_step / assault.curriculum_transition_steps
    )
    observations = env.reset()
    episode_returns = torch.zeros(training.num_envs, device=device)
    episode_scores = torch.zeros(training.num_envs, device=device)
    episode_objective = torch.zeros(training.num_envs, device=device)
    episode_shaping = torch.zeros(training.num_envs, device=device)
    episode_hits = torch.zeros(training.num_envs, device=device)
    episode_valid_fires = torch.zeros(training.num_envs, device=device)
    episode_permanent_locks = torch.zeros(training.num_envs, device=device)
    episode_outpost_destroyed = torch.zeros(
        training.num_envs, dtype=torch.bool, device=device
    )
    episodes = resume_episodes
    successful_episodes = resume_successes
    global_step = resume_global_step
    update_round = resume_updates
    session_start_step = global_step
    start = time.monotonic()
    deadline = start + training.duration_hours * 3600.0
    next_log = start + training.log_seconds
    next_checkpoint = start + training.checkpoint_minutes * 60.0
    latest_stats = None
    log(
        f"GPU tensor training started device={device} envs={training.num_envs} "
        f"rollout={training.rollout_steps} duration={training.duration_hours:.2f}h "
        f"max_env_steps={training.max_env_steps or 'unbounded'} "
        f"resume_step={resume_global_step} resume_episode={resume_episodes}"
    )
    try:
        while (
            time.monotonic() < deadline
            and (
                training.max_env_steps is None
                or global_step < training.max_env_steps
            )
            and not stop_requested
        ):
            decision = learner.act_tensors(observations)
            transition = env.step(decision.action)
            next_values = learner.value_tensors(
                transition.observation,
                decision.next_state,
                reset=torch.zeros(
                    training.num_envs, dtype=torch.bool, device=device
                ),
            )
            rollout.add(
                scalar=observations.scalar,
                spatial=observations.spatial,
                critic=observations.critic,
                categorical_actions=decision.categorical,
                continuous_actions=decision.continuous,
                log_probabilities=decision.log_probabilities,
                values=decision.values,
                next_values=next_values,
                rewards=transition.reward,
                terminated=transition.terminated,
                truncated=transition.truncated,
                episode_starts=observations.recurrent_reset,
                initial_state=decision.initial_state,
            )
            global_step += training.num_envs
            episode_returns += transition.reward
            episode_scores += transition.raw_reward
            episode_objective += transition.objective_score
            episode_shaping += transition.shaping_score
            episode_hits += transition.hit.to(torch.float32)
            episode_valid_fires += transition.valid_fire.to(torch.float32)
            episode_permanent_locks += transition.permanent_lock_triggered.to(
                torch.float32
            )
            episode_outpost_destroyed |= transition.outpost_destroyed
            done = transition.terminated | transition.truncated
            observations = transition.observation
            if bool(done.any().item()):
                indices = torch.nonzero(done, as_tuple=False).squeeze(1)
                batch = torch.stack(
                    (
                        episode_returns[indices],
                        episode_scores[indices],
                        episode_objective[indices],
                        episode_shaping[indices],
                        transition.terminated[indices].float(),
                        transition.remaining_time[indices],
                        episode_hits[indices],
                        episode_valid_fires[indices],
                        episode_permanent_locks[indices],
                        episode_outpost_destroyed[indices].float(),
                        transition.curriculum_mode[indices].float(),
                    ),
                    dim=1,
                ).detach().cpu().numpy()
                first_episode = episodes + 1
                for env_index, values in zip(indices.detach().cpu().tolist(), batch):
                    episodes += 1
                    success = bool(values[4])
                    successful_episodes += int(success)
                    append_jsonl(
                        metrics_path,
                        {
                            "type": "episode",
                            "episode": episodes,
                            "env_index": int(env_index),
                            "global_step": global_step,
                            "return": float(values[0]),
                            "raw_score": float(values[1]),
                            "objective_score": float(values[2]),
                            "shaping_score": float(values[3]),
                            "success": success,
                            "remaining_time": float(values[5]),
                            "hits": int(values[6]),
                            "valid_fires": int(values[7]),
                            "permanent_locks": int(values[8]),
                            "outpost_destroyed": bool(values[9]),
                            "curriculum_mode": int(values[10]),
                        },
                    )
                log(
                    f"episodes={first_episode}-{episodes} batch={len(batch)} "
                    f"mean_score={batch[:, 1].mean():+.3f} "
                    f"mean_shaping={batch[:, 3].mean():+.3f} "
                    f"objective_positive={int((batch[:, 2] > 0).sum())} "
                    f"outposts={int(batch[:, 9].sum())} "
                    f"successes={int(batch[:, 4].sum())} "
                    f"mean_hits={batch[:, 6].mean():.1f} "
                    f"mean_valid_fire={batch[:, 7].mean():.1f} "
                    f"permanent_locks={int(batch[:, 8].sum())}"
                )
                episode_returns[done] = 0.0
                episode_scores[done] = 0.0
                episode_objective[done] = 0.0
                episode_shaping[done] = 0.0
                episode_hits[done] = 0.0
                episode_valid_fires[done] = 0.0
                episode_permanent_locks[done] = 0.0
                episode_outpost_destroyed[done] = False
                env.set_curriculum_progress(
                    global_step / assault.curriculum_transition_steps
                )
                observations = env.reset(done)
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
                speed = (global_step - session_start_step) / max(elapsed, 1e-6)
                update_status = (
                    " ppo=waiting"
                    if latest_stats is None
                    else (
                        f" kl={latest_stats.approximate_kl:.4f}"
                        f" grad={latest_stats.gradient_norm:.3f}"
                        f" minibatches={latest_stats.updates}"
                        f" early_stop={int(latest_stats.early_stopped)}"
                    )
                )
                log(
                    f"steps={global_step} episodes={episodes} "
                    f"success={successful_episodes / max(1, episodes):.3f} "
                    f"updates={update_round} speed={speed:.1f} step/s "
                    f"avg_episode_equivalent={assault.episode_seconds / assault.time_step / max(speed, 1e-6):.3f}s"
                    f" curriculum={env.curriculum_progress:.3f}"
                    f"{update_status}"
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
    evaluation: dict[str, object] | None = None
    if not stop_requested:
        log("exporting one deterministic replay in CPU reference environment")
        evaluation = evaluate_checkpoint(
            checkpoint_dir / "final.pt",
            episodes=1,
            seed=training.seed + episodes,
            replay_directory=replay_dir,
            device=str(device),
        )
        write_json(run_dir / "evaluation.json", evaluation)
        log(
            f"evaluation score={float(evaluation['mean_raw_score']):+.3f} "
            f"success_rate={float(evaluation['success_rate']):.3f}"
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
        "evaluation": evaluation,
    }
    write_json(run_dir / "summary.json", summary)
    log(f"training finished steps={global_step} episodes={episodes}")
    return summary


__all__ = ["run_gpu_training"]
