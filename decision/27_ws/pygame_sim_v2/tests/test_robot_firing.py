"""Unified referee firing tests for every projectile-capable robot."""

from __future__ import annotations

import math
import unittest

from rm2026_sim.core import SentryState
from rm2026_sim.field_geometry import BLUE_BASE
from rm2026_sim.task_state import ROBOT_PROFILES, TaskScenario


class RobotFiringTests(unittest.TestCase):
    def test_all_projectile_robots_fire_through_one_referee_path(self) -> None:
        for team in ("red", "blue"):
            for shooter_id in (1, 3, 4, 5, 8):
                with self.subTest(team=team, shooter_id=shooter_id):
                    scenario = TaskScenario()
                    sentry = SentryState(x=1.0, y=1.0)
                    if team == "red":
                        if shooter_id != 8:
                            scenario.set_robot_position(
                                shooter_id,
                                (1.0, 1.0),
                                team="red",
                            )
                        scenario.set_robot_position(2, (2.0, 1.0), team="blue")
                        scenario.robot_hp[2] = 250.0
                        if shooter_id == 8:
                            scenario.ammo = 10
                        else:
                            scenario.own_robot_ammo[shooter_id] = 10
                    else:
                        scenario.set_robot_position(
                            shooter_id,
                            (1.0, 1.0),
                            team="blue",
                        )
                        scenario.set_robot_position(2, (2.0, 1.0), team="red")
                        scenario.own_robot_hp[2] = 250.0
                        scenario.robot_ammo[shooter_id] = 10

                    result = scenario.execute_robot_fire(
                        shooter_id,
                        0.0,
                        team=team,
                        sentry=sentry if team == "red" and shooter_id == 8 else None,
                        preferred_target=2,
                    )

                    expected_damage = ROBOT_PROFILES[shooter_id].raw_projectile_damage
                    self.assertTrue(result.fired)
                    self.assertEqual(result.reason, "fired")
                    self.assertEqual(result.target_id, 2)
                    self.assertEqual(result.damage, expected_damage)
                    self.assertEqual(result.projectile, ROBOT_PROFILES[shooter_id].projectile)
                    self.assertGreater(
                        scenario.robot_heat_value(
                            shooter_id,
                            team=team,
                            sentry=sentry if team == "red" and shooter_id == 8 else None,
                        ),
                        0.0,
                    )

    def test_unaligned_shot_is_a_real_miss_and_consumes_resources(self) -> None:
        scenario = TaskScenario()
        scenario.own_robot_ammo[3] = 5
        scenario.set_robot_position(3, (1.0, 1.0), team="red")
        scenario.set_robot_position(2, (2.0, 1.0), team="blue")
        before_hp = scenario.robot_hp[2]

        result = scenario.execute_robot_fire(
            3,
            math.pi,
            team="red",
            preferred_target=2,
        )

        self.assertTrue(result.fired)
        self.assertEqual(result.reason, "fired_miss")
        self.assertIsNone(result.target_id)
        self.assertEqual(result.damage, 0)
        self.assertEqual(scenario.own_robot_ammo[3], 4)
        self.assertEqual(scenario.own_robot_heat[3], 10.0)
        self.assertEqual(scenario.robot_hp[2], before_hp)

    def test_weak_robot_cannot_fire(self) -> None:
        scenario = TaskScenario()
        scenario.own_robot_ammo[3] = 5
        scenario.own_robot_weak_state[3] = True
        scenario.set_robot_position(3, (1.0, 1.0), team="red")
        scenario.set_robot_position(2, (2.0, 1.0), team="blue")

        result = scenario.execute_robot_fire(
            3,
            0.0,
            team="red",
            preferred_target=2,
        )

        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "weak_state")
        self.assertEqual(scenario.own_robot_ammo[3], 5)
        self.assertEqual(scenario.own_robot_heat[3], 0.0)

    def test_line_of_sight_block_causes_a_miss(self) -> None:
        scenario = TaskScenario()
        scenario.robot_ammo[5] = 5
        scenario.set_robot_position(5, (1.0, 1.0), team="blue")
        scenario.set_robot_position(2, (2.0, 1.0), team="red")
        before_hp = scenario.own_robot_hp[2]

        result = scenario.execute_robot_fire(
            5,
            0.0,
            team="blue",
            preferred_target=2,
            line_of_sight=lambda _start, _end: False,
        )

        self.assertTrue(result.fired)
        self.assertEqual(result.reason, "fired_miss")
        self.assertEqual(scenario.own_robot_hp[2], before_hp)

    def test_generic_17mm_shot_uses_base_upper_front_armor(self) -> None:
        scenario = TaskScenario(enemy_outpost_hp=0.0)
        scenario.own_robot_ammo[3] = 5
        shooter = (BLUE_BASE[0] - 1.0, BLUE_BASE[1])
        scenario.set_robot_position(3, shooter, team="red")
        # Stay within the 4-degree alignment tolerance while missing the tiny
        # 10 mm x 10 mm building centre bonus zone.
        aim = math.atan2(BLUE_BASE[1] - shooter[1], BLUE_BASE[0] - shooter[0]) + 0.01

        result = scenario.execute_robot_fire(
            3,
            aim,
            team="red",
            preferred_target=7,
        )

        self.assertTrue(result.fired)
        self.assertEqual(result.target_id, 7)
        self.assertEqual(result.damage, 5)
        self.assertEqual(scenario.enemy_base_shield, 145.0)

    def test_exact_outpost_aim_does_not_imply_critical_damage(self) -> None:
        scenario = TaskScenario()
        scenario.own_robot_ammo[3] = 5
        outpost = scenario.combatant_position("blue", 6)
        shooter = (outpost[0] - 1.0, outpost[1])
        scenario.set_robot_position(3, shooter, team="red")

        result = scenario.execute_robot_fire(
            3,
            0.0,
            team="red",
            preferred_target=6,
        )

        self.assertTrue(result.fired)
        self.assertEqual(result.target_id, 6)
        self.assertEqual(result.damage, 20)
        self.assertEqual(scenario.enemy_outpost_hp, 1480.0)


if __name__ == "__main__":
    unittest.main()
