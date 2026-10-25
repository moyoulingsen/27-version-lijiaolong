"""CLI entry point for single-sentry assault training."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import torch

from rl.config import AssaultConfig, NetworkConfig, PPOConfig, TrainingConfig
from rl.compat import install_legacy_checkpoint_aliases
from rl.runners import run_gpu_training, run_training


RL_ROOT = Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train one sentry to destroy the enemy outpost and base."
    )
    parser.add_argument("--duration-hours", type=float, default=2.0)
    parser.add_argument("--max-env-steps", type=int)
    parser.add_argument(
        "--num-envs",
        type=int,
        help="Parallel environments. Overrides the checkpoint value when resuming.",
    )
    parser.add_argument(
        "--rollout-steps",
        type=int,
        help="Steps stored per environment. Overrides the checkpoint value when resuming.",
    )
    parser.add_argument("--time-step", type=float, default=0.1)
    parser.add_argument("--episode-seconds", type=float, default=420.0)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--backend",
        choices=("gpu", "cpu"),
        default="gpu",
        help="gpu uses the tensor-native batched simulator; cpu uses the reference simulator.",
    )
    parser.add_argument("--run-name", default="")
    parser.add_argument("--checkpoint-minutes", type=float, default=20.0)
    parser.add_argument("--log-seconds", type=float, default=10.0)
    parser.add_argument(
        "--curriculum",
        action="store_true",
        help="Use reverse curriculum resets that decay to the real red-home start.",
    )
    parser.add_argument(
        "--curriculum-max-progress",
        type=float,
        help="Override the maximum curriculum progress when starting or resuming.",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="Checkpoint file or previous run directory to continue from.",
    )
    parser.add_argument(
        "--warm-start",
        type=Path,
        help="Load Actor features from a checkpoint with a fresh Critic and optimizer.",
    )
    parser.add_argument(
        "--reset-movement-head",
        action="store_true",
        help="Warm-start perception/shooting while relearning route selection.",
    )
    parser.add_argument(
        "--reward-version",
        type=int,
        choices=(1, 2, 3),
        help="Reward profile number. V1 remains the original guided reward.",
    )
    return parser.parse_args()


def resolve_resume_checkpoint(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_file():
        return path
    if not path.is_dir():
        raise FileNotFoundError(path)
    published_path = path / "final.pt"
    if published_path.is_file():
        return published_path
    final_path = path / "checkpoints" / "final.pt"
    latest_path = path / "checkpoints" / "latest.pt"
    if final_path.is_file():
        return final_path
    if latest_path.is_file():
        return latest_path
    raise FileNotFoundError(f"no final.pt or latest.pt under {path}")


def main() -> None:
    args = parse_args()
    if args.duration_hours <= 0.0:
        raise ValueError("duration-hours must be positive")
    if args.max_env_steps is not None and args.max_env_steps <= 0:
        raise ValueError("max-env-steps must be positive")
    if args.num_envs is not None and args.num_envs <= 0:
        raise ValueError("num-envs must be positive")
    if args.rollout_steps is not None and args.rollout_steps <= 0:
        raise ValueError("rollout-steps must be positive")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.resume is not None and args.warm_start is not None:
        raise ValueError("--resume and --warm-start are mutually exclusive")
    if args.reset_movement_head and args.warm_start is None:
        raise ValueError("--reset-movement-head requires --warm-start")
    resume_checkpoint = (
        resolve_resume_checkpoint(args.resume) if args.resume is not None else None
    )
    warm_start_checkpoint = (
        resolve_resume_checkpoint(args.warm_start)
        if args.warm_start is not None
        else None
    )
    if resume_checkpoint is not None:
        install_legacy_checkpoint_aliases()
        payload = torch.load(resume_checkpoint, map_location="cpu", weights_only=False)
        checkpoint_metadata = payload["metadata"]
        assault = AssaultConfig(**checkpoint_metadata["assault"])
        if (
            args.reward_version is not None
            and args.reward_version != assault.reward_version
        ):
            raise ValueError(
                "--resume cannot change reward versions; use --warm-start instead"
            )
        if args.curriculum_max_progress is not None:
            assault = replace(
                assault,
                curriculum_max_progress=args.curriculum_max_progress,
            )
        network = NetworkConfig(**checkpoint_metadata["network"])
        ppo = PPOConfig(**checkpoint_metadata["ppo"])
        base_training = TrainingConfig(**checkpoint_metadata["training"])
        training = replace(
            base_training,
            duration_hours=args.duration_hours,
            max_env_steps=(
                args.max_env_steps
                if args.max_env_steps is not None
                else base_training.max_env_steps
            ),
            num_envs=(
                args.num_envs if args.num_envs is not None else base_training.num_envs
            ),
            rollout_steps=(
                args.rollout_steps
                if args.rollout_steps is not None
                else base_training.rollout_steps
            ),
            device=args.device,
            checkpoint_minutes=args.checkpoint_minutes,
            log_seconds=args.log_seconds,
        )
        run_name = args.run_name or f"{args.resume.name}_resume_{timestamp}"
    else:
        reward_version = args.reward_version or 1
        assault = replace(
            AssaultConfig(),
            time_step=args.time_step,
            episode_seconds=args.episode_seconds,
            curriculum_enabled=args.curriculum,
            reward_version=reward_version,
            curriculum_max_progress=(
                args.curriculum_max_progress
                if args.curriculum_max_progress is not None
                else (
                    1.0
                    if reward_version in (2, 3)
                    else AssaultConfig().curriculum_max_progress
                )
            ),
        )
        if warm_start_checkpoint is not None:
            install_legacy_checkpoint_aliases()
            warm_payload = torch.load(
                warm_start_checkpoint,
                map_location="cpu",
                weights_only=False,
            )
            warm_metadata = warm_payload.get("metadata", {})
            network = NetworkConfig(**warm_metadata.get("network", {}))
        else:
            network = NetworkConfig()
        ppo = PPOConfig()
        if reward_version == 2:
            ppo = replace(
                ppo,
                learning_rate=3e-5,
                clip_ratio=0.10,
                target_kl=0.01,
                entropy_coefficient=0.02,
                fire_entropy_coefficient=0.03,
                continuous_entropy_coefficient=0.002,
            )
        elif reward_version == 3:
            ppo = replace(
                ppo,
                learning_rate=3e-5,
                clip_ratio=0.10,
                target_kl=0.01,
                entropy_coefficient=0.04,
                fire_entropy_coefficient=0.02,
                continuous_entropy_coefficient=0.003,
            )
        training = replace(
            TrainingConfig(),
            duration_hours=args.duration_hours,
            max_env_steps=args.max_env_steps,
            num_envs=(
                args.num_envs
                if args.num_envs is not None
                else TrainingConfig.num_envs
            ),
            rollout_steps=(
                args.rollout_steps
                if args.rollout_steps is not None
                else TrainingConfig.rollout_steps
            ),
            seed=args.seed,
            device=args.device,
            checkpoint_minutes=args.checkpoint_minutes,
            log_seconds=args.log_seconds,
        )
        run_name = args.run_name or f"sentry_reward_v{reward_version}_{timestamp}"
    runner = run_gpu_training if args.backend == "gpu" else run_training
    runner(
        RL_ROOT / "artifacts" / "runs" / run_name,
        assault=assault,
        network=network,
        ppo=ppo,
        training=training,
        resume_checkpoint=resume_checkpoint,
        warm_start_checkpoint=warm_start_checkpoint,
        reset_movement_head=args.reset_movement_head,
    )


if __name__ == "__main__":
    main()
