from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch

from rm2026_sim.app import SimulatorApp
from rm2026_sim.dataset_replay import DatasetReplay, MatchRecord, RobotSample


@unittest.skipUnless(importlib.util.find_spec("pygame"), "Pygame is not installed")
class RobotPropertyUITests(unittest.TestCase):
    def setUp(self) -> None:
        import pygame

        self.environment = patch.dict(os.environ, {
            "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
        })
        self.environment.start()
        self.pg = pygame
        self.app = SimulatorApp(pygame)

    def tearDown(self) -> None:
        self.app.bridge.close()
        self.pg.quit()
        self.environment.stop()

    def render_at(self, position: tuple[int, int]) -> None:
        with patch.object(self.pg.mouse, "get_pos", return_value=position):
            self.app._render(self.app._viewport())

    def test_hover_disappears_and_clicked_card_stays_until_unpinned(self) -> None:
        self.assertEqual(self.app.map_surface.get_size(), (3708, 2052))
        self.render_at((0, 0))
        row, team, target_id = self.app.robot_property_regions[0]
        self.render_at(row.center)
        self.assertEqual(self.app.hovered_robot_key, (team, target_id))
        self.assertIsNotNone(self.app.robot_property_popup_rect)

        self.render_at((0, 0))
        self.assertIsNone(self.app.hovered_robot_key)
        self.assertIsNone(self.app.robot_property_popup_rect)

        self.app._handle_mouse_click(row.center)
        self.render_at((0, 0))
        self.assertEqual(self.app.pinned_robot_key, (team, target_id))
        self.assertIsNotNone(self.app.robot_property_popup_rect)
        self.app._handle_mouse_click((0, 0))
        self.assertEqual(self.app.pinned_robot_key, (team, target_id))

        close = next(rect for rect, action, _, _ in self.app.click_regions
                     if action == "unpin_robot_property")
        self.app._handle_mouse_click(close.center)
        self.render_at((0, 0))
        self.assertIsNone(self.app.pinned_robot_key)
        self.assertIsNone(self.app.robot_property_popup_rect)

    def test_rule_attributes_fit_card_and_drive_button_selects_local_robot(self) -> None:
        self.app.pinned_robot_key = ("red", 1)
        self.render_at((0, 0))
        with patch.object(self.app, "_draw_key_value", wraps=self.app._draw_key_value) as rows:
            self.app._draw_robot_property_popup()
        popup = self.app.robot_property_popup_rect
        for call in rows.call_args_list:
            self.assertLess(call.args[1] + 31, popup.bottom - 42)
        drive = next(rect for rect, action, _, _ in self.app.click_regions
                     if action == "control_own_robot")
        self.app._handle_mouse_click(drive.center)
        self.assertEqual(self.app.controlled_robot_id, 1)
        self.assertEqual(self.app.controlled_robot_team, "red")
        self.assertFalse(self.app.sentry.manual_control)

    def test_function_keys_select_friendly_robots_without_scene_injection(self) -> None:
        self.render_at((0, 0))
        self.assertEqual(len(self.app.robot_property_regions), 8)
        self.assertFalse(
            any(action == "task_key" for _, action, _, _ in self.app.click_regions)
        )
        self.assertEqual(
            sum(action == "auto_control" for _, action, _, _ in self.app.click_regions),
            1,
        )
        self.assertEqual(
            sum(action == "restart_validation" for _, action, _, _ in self.app.click_regions),
            1,
        )
        original_outpost_hp = self.app.task.own_outpost_hp
        self.app._select_own_robot_function_key(self.pg.K_F1)
        self.assertEqual(self.app.controlled_robot_id, 1)
        self.assertEqual(self.app.controlled_robot_team, "red")
        self.assertEqual(self.app.task.own_outpost_hp, original_outpost_hp)

        self.app._select_own_robot_function_key(self.pg.K_F5)
        self.assertEqual(self.app.controlled_robot_id, 5)
        self.assertEqual(self.app.controlled_robot_team, "red")

        self.app._select_own_robot_function_key(self.pg.K_F8)
        self.assertTrue(self.app.sentry.manual_control)
        self.assertIsNone(self.app.controlled_robot_id)

        self.app._select_own_robot_function_key(self.pg.K_F6)
        self.assertTrue(self.app.sentry.manual_control)
        self.assertEqual(self.app.task.own_outpost_hp, original_outpost_hp)

        minus_health = next(
            rect
            for rect, action, target_id, direction in self.app.click_regions
            if action == "own_robot_health" and target_id == 1 and direction == -1
        )
        self.app._handle_mouse_click(minus_health.center)
        self.assertEqual(self.app.task.own_robot_health(1), 180)

        enemy_tab = next(
            rect
            for rect, action, team, _ in self.app.click_regions
            if action == "robot_team_tab" and team == "blue"
        )
        self.app._handle_mouse_click(enemy_tab.center)
        self.render_at((0, 0))
        self.assertEqual(self.app.robot_property_team, "blue")
        self.assertEqual(len(self.app.robot_property_regions), 8)
        self.assertTrue(
            all(team == "blue" for _, team, _ in self.app.robot_property_regions)
        )

    def test_rl_replay_keeps_team_tabs_interactive_and_values_read_only(self) -> None:
        self.app.rl_replay_mode = True
        self.render_at((0, 0))
        enemy_tab = next(
            rect
            for rect, action, team, _ in self.app.click_regions
            if action == "robot_team_tab" and team == "blue"
        )
        self.assertTrue(self.app._handle_mouse_click(enemy_tab.center))
        self.render_at((0, 0))
        self.assertEqual(self.app.robot_property_team, "blue")
        self.assertTrue(
            all(team == "blue" for _, team, _ in self.app.robot_property_regions)
        )
        self.assertFalse(
            any(
                action in {"enemy_health", "own_robot_health"}
                for _, action, _, _ in self.app.click_regions
            )
        )

    def test_map_region_layers_are_hidden_until_selected_in_bottom_panel(self) -> None:
        self.render_at((0, 0))
        self.assertFalse(self.app.map_layers_panel_open)
        self.assertTrue(
            all(not visible for visible in self.app.map_layer_visibility.values())
        )

        expand = next(
            rect for rect, action, _, _ in self.app.click_regions
            if action == "toggle_map_layers_panel"
        )
        self.app._handle_mouse_click(expand.center)
        self.render_at((0, 0))
        self.assertTrue(self.app.map_layers_panel_open)

        road = next(
            rect for rect, action, target, _ in self.app.click_regions
            if action == "toggle_map_layer" and target == "zone:terrain_road"
        )
        self.app._handle_mouse_click(road.center)
        self.assertTrue(self.app.map_layer_visibility["zone:terrain_road"])
        self.assertTrue(self.app.show_field_zones)

        collapse = next(
            rect for rect, action, _, _ in self.app.click_regions
            if action == "toggle_map_layers_panel"
        )
        self.app._handle_mouse_click(collapse.center)
        self.assertFalse(self.app.map_layers_panel_open)

    def test_replay_property_panels_use_dataset_health_and_heat_limits(self) -> None:
        self.app.bridge.close()
        match = MatchRecord(
            "东部赛区", 1, "schedule", 1, 123, None,
            "red", "blue", None, None, 10.0,
        )

        def sample(
            robot_id: int,
            robot_type: str,
            team: str,
            hp: float,
            max_hp: float,
            *,
            large_heat: float | None = None,
            large_heat_limit: float | None = None,
        ) -> RobotSample:
            return RobotSample(
                time_seconds=0.0, robot_id=robot_id, robot_type=robot_type,
                team=team, school=team, opponent_school="other", hp=hp,
                max_hp=max_hp, x=1.0, y=1.0, z=0.0, heading_degrees=0.0,
                chassis_power=50.0, small_heat=0.0, small_heat_limit=100.0,
                large_heat=large_heat, large_heat_limit=large_heat_limit,
                shots_17mm=0.0, shots_42mm=0.0, team_coins=400.0,
                remaining_coins=400.0, vulnerable=False,
            )

        replay = DatasetReplay(
            match,
            (
                sample(1, "英雄", "红", 123.0, 456.0,
                       large_heat=78.0, large_heat_limit=333.0),
                sample(11, "前哨站", "红", 1400.0, 1700.0),
                sample(101, "英雄", "蓝", 110.0, 460.0),
                sample(111, "前哨站", "蓝", 1300.0, 1650.0),
            ),
            (),
        )
        self.app = SimulatorApp(self.pg, replay=replay)
        self.app.pinned_robot_key = ("red", 1)

        with patch.object(self.pg.mouse, "get_pos", return_value=(0, 0)):
            with patch.object(
                self.app, "_draw_adjustable_progress_bar",
                wraps=self.app._draw_adjustable_progress_bar,
            ) as progress_bars:
                with patch.object(
                    self.app, "_draw_key_value", wraps=self.app._draw_key_value,
                ) as key_values:
                    self.app._render(self.app._viewport())

        own_outpost = next(
            call for call in progress_bars.call_args_list
            if call.args[3] == "己方前哨"
        )
        self.assertEqual(own_outpost.args[5], 1700.0)
        popup_heat_limit = next(
            call for call in key_values.call_args_list
            if call.args[2] == "射击热量上限"
        )
        self.assertEqual(popup_heat_limit.args[3], "333.0")


if __name__ == "__main__":
    unittest.main()
