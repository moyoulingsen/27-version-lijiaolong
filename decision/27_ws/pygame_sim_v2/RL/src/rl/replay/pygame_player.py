"""Play RL trajectories inside the existing full SimulatorApp renderer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from rm2026_sim.app import SimulatorApp

from .pygame_bridge import iter_replay


SEEK_HOLD_DELAY_SECONDS = 0.28
SEEK_INITIAL_MULTIPLIER = 8.0
SEEK_MAX_MULTIPLIER = 32.0
SEEK_ACCELERATION_SECONDS = 1.0


@dataclass(slots=True)
class HoldSeekController:
    """Turn a short +/- press into speed control and a hold into seeking."""

    direction: int = 0
    held_seconds: float = 0.0
    frame_accumulator: float = 0.0
    activated: bool = False

    def press(self, direction: int) -> None:
        if direction not in (-1, 1):
            raise ValueError("seek direction must be -1 or 1")
        if self.direction == direction:
            return
        self.direction = direction
        self.held_seconds = 0.0
        self.frame_accumulator = 0.0
        self.activated = False

    def release(self, direction: int) -> bool:
        if self.direction != direction:
            return False
        was_activated = self.activated
        self.direction = 0
        self.held_seconds = 0.0
        self.frame_accumulator = 0.0
        self.activated = False
        return was_activated

    def update(self, elapsed: float, frames_per_second: float) -> int:
        if self.direction == 0 or elapsed <= 0.0:
            return 0
        previous_held = self.held_seconds
        self.held_seconds += elapsed
        active_elapsed = max(0.0, self.held_seconds - SEEK_HOLD_DELAY_SECONDS)
        previous_active = max(0.0, previous_held - SEEK_HOLD_DELAY_SECONDS)
        delta_active = active_elapsed - previous_active
        if delta_active <= 0.0:
            return 0
        self.activated = True
        acceleration = min(
            1.0,
            active_elapsed / SEEK_ACCELERATION_SECONDS,
        )
        multiplier = SEEK_INITIAL_MULTIPLIER + (
            SEEK_MAX_MULTIPLIER - SEEK_INITIAL_MULTIPLIER
        ) * acceleration
        self.frame_accumulator += delta_active * frames_per_second * multiplier
        frame_delta = int(self.frame_accumulator)
        self.frame_accumulator -= frame_delta
        return self.direction * frame_delta


def load_frames(path: Path) -> list[dict[str, object]]:
    return [item for item in iter_replay(path) if item.get("type") == "frame"]


def apply_frame(app: SimulatorApp, frame: dict[str, object]) -> None:
    state = frame["state"]
    sentry = state["sentry"]
    structures = state["structures"]
    app.sentry.x = float(sentry["x"])
    app.sentry.y = float(sentry["y"])
    app.sentry.spin_angle = float(sentry["chassis_angle"])
    app.sentry.turret_angle = float(sentry["turret_angle"])
    app.sentry.spin_speed = float(sentry["spin_speed"])
    app.sentry.turret_speed = float(sentry["turret_speed"])
    app.sentry.heat = float(sentry["heat"])
    app.sentry.enable_manual_control()
    app.task.remaining_time = float(state["remaining_time"])
    app.task.sentry_hp = float(sentry["hp"])
    app.task.ammo = int(sentry["ammo"])
    app.task.active_posture = int(sentry["posture"])
    app.task.posture_reinforced = bool(sentry["reinforced"])
    app.task.enemy_outpost_hp = float(structures["outpost_hp"])
    app.task.enemy_base_hp = float(structures["base_hp"])
    app.task.enemy_base_shield = float(structures["base_shield"])
    for target_id in tuple(app.task.robot_hp):
        app.task.robot_hp[target_id] = 0.0
    for target_id in tuple(app.task.own_robot_hp):
        app.task.own_robot_hp[target_id] = 0.0


def run_replay(
    path: Path,
    *,
    frames_per_second: float = 30.0,
    max_frames: int | None = None,
    screenshot: Path | None = None,
) -> None:
    if frames_per_second <= 0.0:
        raise ValueError("frames_per_second must be positive")
    frames = load_frames(path)
    if not frames:
        raise ValueError("replay contains no frames")
    try:
        import pygame
    except ModuleNotFoundError as error:
        raise SystemExit("Pygame is not installed in .venv-rl") from error
    app = SimulatorApp(pygame)
    # The RL trajectory viewer uses the live SimulatorApp renderer without a
    # DatasetReplay instance.  Keep its panels interactive but read-only.
    app.rl_replay_mode = True
    app.pg.display.set_caption("RMUC 2026 | RL单哨兵训练回放")
    index = 0
    speed = 1.0
    paused = False
    hold_seek = HoldSeekController()
    rendered = 0
    accumulator = 0.0
    running = True
    try:
        while running:
            elapsed = app.clock.tick(60) / 1000.0
            for event in app.pg.event.get():
                if event.type == app.pg.QUIT:
                    running = False
                elif event.type == app.pg.KEYDOWN:
                    if event.key == app.pg.K_ESCAPE:
                        running = False
                    elif event.key in (app.pg.K_SPACE, app.pg.K_p):
                        paused = not paused
                    elif event.key == app.pg.K_LEFT:
                        index = max(0, index - 1)
                    elif event.key == app.pg.K_RIGHT:
                        index = min(len(frames) - 1, index + 1)
                    elif event.key == app.pg.K_HOME:
                        index = 0
                    elif event.key == app.pg.K_END:
                        index = len(frames) - 1
                    elif event.key in (app.pg.K_EQUALS, app.pg.K_PLUS, app.pg.K_KP_PLUS):
                        hold_seek.press(1)
                    elif event.key in (app.pg.K_MINUS, app.pg.K_KP_MINUS):
                        hold_seek.press(-1)
                elif event.type == app.pg.KEYUP:
                    if event.key in (app.pg.K_EQUALS, app.pg.K_PLUS, app.pg.K_KP_PLUS):
                        if not hold_seek.release(1):
                            speed = min(16.0, speed * 2.0)
                    elif event.key in (app.pg.K_MINUS, app.pg.K_KP_MINUS):
                        if not hold_seek.release(-1):
                            speed = max(0.25, speed / 2.0)
                elif event.type == app.pg.MOUSEWHEEL:
                    app._scroll_map_editor_list(
                        event.y,
                        app.pg.mouse.get_pos(),
                    )
                elif (
                    event.type == app.pg.MOUSEBUTTONDOWN
                    and event.button in (4, 5)
                ):
                    app._scroll_map_editor_list(
                        1 if event.button == 4 else -1,
                        event.pos,
                    )
                elif event.type == app.pg.MOUSEBUTTONDOWN and event.button == 1:
                    app._handle_mouse_click(event.pos)
            seek_frames = hold_seek.update(elapsed, frames_per_second)
            if seek_frames:
                index = max(0, min(len(frames) - 1, index + seek_frames))
            if not paused:
                accumulator += elapsed * frames_per_second * speed
                advance = int(accumulator)
                if advance:
                    accumulator -= advance
                    index = min(len(frames) - 1, index + advance)
                    if index == len(frames) - 1:
                        paused = True
            frame = frames[index]
            apply_frame(app, frame)
            app._render(app._viewport())
            overlay = app.small_font.render(
                f"RL回放  帧 {index + 1}/{len(frames)}  速度 {speed:.2f}x  "
                f"本步得分 {float(frame.get('reward', 0.0)):.1f}",
                True,
                (255, 223, 120),
            )
            app.screen.blit(overlay, (340, 106))
            help_overlay = app.small_font.render(
                "短按 +/- 调速｜长按 +/- 快进/快退｜空格暂停｜左右逐帧",
                True,
                (185, 204, 211),
            )
            app.screen.blit(help_overlay, (340, 134))
            app.pg.display.flip()
            rendered += 1
            if max_frames is not None and rendered >= max_frames:
                if screenshot is not None:
                    screenshot.parent.mkdir(parents=True, exist_ok=True)
                    app.pg.image.save(app.screen, str(screenshot))
                running = False
    finally:
        app.pg.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play one RL replay in SimulatorApp.")
    parser.add_argument("replay", type=Path)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--screenshot", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_replay(
        args.replay,
        frames_per_second=args.fps,
        max_frames=args.max_frames,
        screenshot=args.screenshot,
    )


if __name__ == "__main__":
    main()


__all__ = ["HoldSeekController", "apply_frame", "load_frames", "run_replay"]
