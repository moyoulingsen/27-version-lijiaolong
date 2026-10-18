"""Legacy standalone SQLite viewer.

The supported replay entry point is now :class:`rm2026_sim.app.SimulatorApp`;
this module remains only for backwards compatibility with older callers.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from .core import Arena, Viewport
from .dataset_replay import (
    DEFAULT_DATASET_PATH,
    DatasetError,
    DatasetRepository,
    DatasetReplay,
    MatchRecord,
    ReplayFrame,
    ReplayPlayer,
)


APP_ROOT = Path(__file__).resolve().parent.parent
FIELD_LAYOUT_PATH = APP_ROOT / "assets" / "rmuc2026_field_layout.png"
SIDE_WIDTH = 365
HEADER_HEIGHT = 70
FOOTER_HEIGHT = 100


def _font_path(bold: bool = False) -> str | None:
    candidates = (
        ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    )
    return next((path for path in candidates if Path(path).is_file()), None)


class ReplayApp:
    """Interactive, read-only replay window.

    The viewer intentionally never feeds recorded state back into the live
    decision tree.  It is a separate transport mode for inspecting the
    official observations and event stream without changing the validator.
    """

    def __init__(
        self,
        pygame_module,
        repository: DatasetRepository,
        matches: tuple[MatchRecord, ...],
        initial_index: int = 0,
    ) -> None:
        self.pg = pygame_module
        self.repository = repository
        self.matches = matches
        self.match_index = max(0, min(initial_index, len(matches) - 1))
        self.pg.init()
        self.pg.display.set_caption("RMUC 2026 SQLite 数据集回放")
        self.screen = self.pg.display.set_mode((1600, 950), self.pg.RESIZABLE)
        self.clock = self.pg.time.Clock()
        self.title_font = self.pg.font.Font(_font_path(True), 28)
        self.body_font = self.pg.font.Font(_font_path(False), 19)
        self.small_font = self.pg.font.Font(_font_path(False), 16)
        self.arena = Arena()
        self.map_surface = self.pg.image.load(str(FIELD_LAYOUT_PATH)).convert()
        self.scaled_map = None
        self.scaled_map_size = None
        self.replay: DatasetReplay
        self.player: ReplayPlayer
        self._open_match(self.match_index)
        self.timeline_rect = None
        self.dragging_timeline = False

    def _open_match(self, index: int) -> None:
        self.match_index = max(0, min(index, len(self.matches) - 1))
        self.replay = self.repository.load_replay(self.matches[self.match_index].game_id)
        self.player = ReplayPlayer(self.replay)

    def _viewport(self) -> Viewport:
        width, height = self.screen.get_size()
        left = SIDE_WIDTH + 24
        right = width - 24
        top = HEADER_HEIGHT + 20
        bottom = height - FOOTER_HEIGHT - 18
        scale = min((right - left) / self.arena.width, (bottom - top) / self.arena.height)
        map_width = self.arena.width * scale
        map_height = self.arena.height * scale
        return Viewport(
            left + ((right - left) - map_width) / 2.0,
            top + ((bottom - top) - map_height) / 2.0,
            map_width,
            map_height,
            self.arena,
        )

    def run(self, *, max_frames: int | None = None, screenshot_path: Path | None = None) -> None:
        frame_count = 0
        running = True
        try:
            while running:
                elapsed = min(self.clock.tick(60) / 1000.0, 0.1)
                for event in self.pg.event.get():
                    if event.type == self.pg.QUIT:
                        running = False
                    elif event.type == self.pg.KEYDOWN:
                        running = self._handle_key(event) and running
                    elif event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        self._handle_timeline(event.pos)
                    elif event.type == self.pg.MOUSEBUTTONUP and event.button == 1:
                        self.dragging_timeline = False
                    elif event.type == self.pg.MOUSEMOTION and self.dragging_timeline:
                        self._handle_timeline(event.pos)

                frame = self.player.update(elapsed)
                self._render(frame)
                self.pg.display.flip()
                frame_count += 1
                if max_frames is not None and frame_count >= max_frames:
                    if screenshot_path is not None:
                        self.pg.image.save(self.screen, str(screenshot_path))
                    running = False
        finally:
            self.pg.quit()

    def _handle_key(self, event) -> bool:
        key = event.key
        if key == self.pg.K_ESCAPE:
            return False
        if key == self.pg.K_SPACE:
            self.player.toggle()
        elif key == self.pg.K_LEFT:
            self.player.step(-10.0 if event.mod & self.pg.KMOD_SHIFT else -1.0)
        elif key == self.pg.K_RIGHT:
            self.player.step(10.0 if event.mod & self.pg.KMOD_SHIFT else 1.0)
        elif key == self.pg.K_HOME:
            self.player.seek(0.0)
        elif key == self.pg.K_END:
            self.player.seek(self.replay.duration_seconds)
        elif key in (self.pg.K_EQUALS, self.pg.K_PLUS, self.pg.K_KP_PLUS):
            self.player.faster()
        elif key in (self.pg.K_MINUS, self.pg.K_KP_MINUS):
            self.player.slower()
        elif key == self.pg.K_l:
            self.player.loop = not self.player.loop
        elif key in (self.pg.K_n, self.pg.K_PAGEDOWN):
            self._open_match((self.match_index + 1) % len(self.matches))
        elif key in (self.pg.K_b, self.pg.K_PAGEUP):
            self._open_match((self.match_index - 1) % len(self.matches))
        return True

    def _handle_timeline(self, position: tuple[int, int]) -> None:
        if self.timeline_rect is None or not self.timeline_rect.collidepoint(position):
            return
        self.dragging_timeline = True
        ratio = (position[0] - self.timeline_rect.left) / max(1, self.timeline_rect.width)
        self.player.seek(ratio * self.replay.duration_seconds)

    def _render(self, frame: ReplayFrame) -> None:
        self.screen.fill((238, 241, 242))
        self._draw_header(frame)
        self._draw_arena(frame)
        self._draw_side_panel(frame)
        self._draw_footer(frame)

    def _draw_header(self, frame: ReplayFrame) -> None:
        self.pg.draw.rect(self.screen, (31, 42, 47), (0, 0, self.screen.get_width(), HEADER_HEIGHT))
        title = self.title_font.render("RMUC 2026 区域赛数据集回放", True, (242, 246, 247))
        self.screen.blit(title, (22, 17))
        status = self.body_font.render(
            f"局 {self.match_index + 1}/{len(self.matches)}  ·  game_id {self.replay.match.game_id}",
            True,
            (184, 205, 211),
        )
        self.screen.blit(status, (self.screen.get_width() - status.get_width() - 24, 24))

    def _draw_arena(self, frame: ReplayFrame) -> None:
        viewport = self._viewport()
        rect = self.pg.Rect(round(viewport.left), round(viewport.top), round(viewport.width), round(viewport.height))
        if self.scaled_map_size != rect.size:
            self.scaled_map = self.pg.transform.smoothscale(self.map_surface, rect.size)
            self.scaled_map_size = rect.size
        self.screen.blit(self.scaled_map, rect)
        self.pg.draw.rect(self.screen, (98, 111, 117), rect, 2)
        for x in range(0, 29, 2):
            start = viewport.world_to_screen(x, 0)
            end = viewport.world_to_screen(x, self.arena.height)
            self.pg.draw.line(self.screen, (170, 178, 181), start, end, 1)
        for y in range(0, 16, 5):
            start = viewport.world_to_screen(0, y)
            end = viewport.world_to_screen(self.arena.width, y)
            self.pg.draw.line(self.screen, (170, 178, 181), start, end, 1)
        for sample in frame.samples:
            if sample.x is None or sample.y is None:
                continue
            x, y = sample.x, sample.y
            out_of_bounds = not (0.0 <= x <= self.arena.width and 0.0 <= y <= self.arena.height)
            # Building rows in the official timeseries use (0, 0) as a
            # placeholder.  Their physical positions are fixed by the field.
            if sample.robot_type in ("基地", "前哨站"):
                x = 1.0 if sample.team == "红" else 27.0
                y = 7.5
                if sample.robot_type == "前哨站":
                    x = 8.0 if sample.team == "红" else 20.0
            display_x, display_y = self.arena.clamp(x, y) if out_of_bounds else (x, y)
            screen_x, screen_y = viewport.world_to_screen(display_x, display_y)
            if sample.robot_type in ("基地", "前哨站"):
                color = (201, 61, 68) if sample.team == "红" else (62, 111, 201)
                radius = max(10, round(0.45 * viewport.scale))
                self.pg.draw.rect(self.screen, color, (round(screen_x - radius), round(screen_y - radius), radius * 2, radius * 2), 3)
            else:
                color = (211, 70, 79) if sample.team == "红" else (56, 107, 198)
                radius = max(5, round(0.26 * viewport.scale))
                self.pg.draw.circle(self.screen, color, (round(screen_x), round(screen_y)), radius)
                if sample.heading_degrees is not None:
                    angle = math.radians(sample.heading_degrees)
                    end = (screen_x + math.cos(angle) * radius * 1.9, screen_y - math.sin(angle) * radius * 1.9)
                    self.pg.draw.line(self.screen, (29, 39, 45), (screen_x, screen_y), end, 2)
            if out_of_bounds:
                # Keep noisy/out-of-range telemetry visible at the nearest
                # border without changing the raw value held by the replay.
                self.pg.draw.circle(self.screen, (227, 135, 45), (round(screen_x), round(screen_y)), 7, 2)
            label = self.small_font.render(f"{sample.team}{sample.robot_id} {sample.robot_type}", True, (28, 38, 42))
            self.screen.blit(label, (round(screen_x + 7), round(screen_y - 18)))

    def _draw_side_panel(self, frame: ReplayFrame) -> None:
        panel = self.pg.Rect(0, HEADER_HEIGHT, SIDE_WIDTH, self.screen.get_height() - HEADER_HEIGHT - FOOTER_HEIGHT)
        self.pg.draw.rect(self.screen, (249, 250, 250), panel)
        self.pg.draw.line(self.screen, (196, 204, 207), (SIDE_WIDTH, panel.top), (SIDE_WIDTH, panel.bottom), 1)
        match = self.replay.match
        y = panel.top + 18
        lines = (
            match.schedule,
            f"第 {match.round_number} 局  |  {match.region}",
            f"红：{match.red_school}",
            f"蓝：{match.blue_school}",
            f"胜方：{match.winner or '未知'}",
            f"样本：{self.replay.sample_count:,} 行 / {len(self.replay.robot_ids)} 个实体",
        )
        for index, text in enumerate(lines):
            font = self.body_font if index == 0 else self.small_font
            color = (29, 45, 51) if index == 0 else (84, 96, 101)
            self.screen.blit(font.render(text, True, color), (18, y))
            y += 31 if index == 0 else 25
        y += 10
        self.screen.blit(self.body_font.render("当前事件", True, (29, 45, 51)), (18, y))
        y += 32
        recent = frame.events[-8:]
        if not recent:
            self.screen.blit(self.small_font.render("暂无事件", True, (119, 129, 133)), (18, y))
        for event in reversed(recent):
            detail = event.event_type
            if event.category:
                detail += f" / {event.category}"
            if event.value is not None:
                detail += f" {event.value:g}"
            line = f"{event.time_seconds:6.1f}s  {detail}"
            self.screen.blit(self.small_font.render(line[:32], True, (79, 91, 96)), (18, y))
            y += 23
        hint_y = panel.bottom - 160
        self.screen.blit(self.body_font.render("回放控制", True, (29, 45, 51)), (18, hint_y))
        hints = ("空格 播放/暂停", "←/→ 单步，Shift 十秒", "+/- 倍速，L 循环", "N/B 下一局/上一局", "Home/End 首尾，Esc 退出")
        for index, hint in enumerate(hints):
            self.screen.blit(self.small_font.render(hint, True, (84, 96, 101)), (18, hint_y + 31 + index * 21))

    def _draw_footer(self, frame: ReplayFrame) -> None:
        y = self.screen.get_height() - FOOTER_HEIGHT
        self.pg.draw.rect(self.screen, (31, 42, 47), (0, y, self.screen.get_width(), FOOTER_HEIGHT))
        self.timeline_rect = self.pg.Rect(SIDE_WIDTH + 24, y + 20, self.screen.get_width() - SIDE_WIDTH - 48, 12)
        self.pg.draw.rect(self.screen, (78, 94, 101), self.timeline_rect, border_radius=6)
        ratio = frame.time_seconds / self.replay.duration_seconds if self.replay.duration_seconds else 0.0
        progress = self.pg.Rect(self.timeline_rect.left, self.timeline_rect.top, max(1, round(self.timeline_rect.width * ratio)), self.timeline_rect.height)
        self.pg.draw.rect(self.screen, (68, 176, 153), progress, border_radius=6)
        self.pg.draw.circle(self.screen, (244, 247, 246), (progress.right, self.timeline_rect.centery), 7)
        time_text = self.body_font.render(
            f"{frame.time_seconds:06.1f} / {self.replay.duration_seconds:.0f} 秒    {'播放中' if self.player.playing else '已暂停'}    {self.player.speed:g}x",
            True,
            (236, 242, 243),
        )
        self.screen.blit(time_text, (SIDE_WIDTH + 24, y + 50))
        event_text = self.small_font.render(f"事件累计 {len(frame.events)}", True, (178, 195, 199))
        self.screen.blit(event_text, (self.screen.get_width() - event_text.get_width() - 24, y + 53))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="RMUC 2026 SQLite Pygame replay")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--game-id", type=int)
    parser.add_argument("--region")
    parser.add_argument("--school")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args(argv)
    repository = None
    try:
        repository = DatasetRepository(args.dataset)
        matches = repository.list_matches(region=args.region, school=args.school)
        if not matches:
            raise DatasetError("No matches matched the requested filters")
        index = 0
        if args.game_id is not None:
            matching = [i for i, match in enumerate(matches) if match.game_id == args.game_id]
            if not matching:
                raise DatasetError(f"game_id {args.game_id} is not in the filtered match list")
            index = matching[0]
        import pygame

        ReplayApp(pygame, repository, matches, index).run(
            max_frames=args.max_frames,
            screenshot_path=args.screenshot,
        )
    except ModuleNotFoundError as error:
        raise SystemExit("尚未安装 Pygame，请执行：python -m pip install -r requirements.txt") from error
    except (DatasetError, OSError) as error:
        raise SystemExit(str(error)) from error
    finally:
        if repository is not None:
            repository.close()


if __name__ == "__main__":
    main()
