from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch

from rm2026_sim.app import SimulatorApp


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


if __name__ == "__main__":
    unittest.main()
