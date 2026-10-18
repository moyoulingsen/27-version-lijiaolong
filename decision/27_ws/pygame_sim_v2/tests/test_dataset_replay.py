"""Tests for the SQLite-backed replay transport."""

from __future__ import annotations

import unittest

from rm2026_sim.dataset_replay import (
    DEFAULT_DATASET_PATH,
    DatasetRepository,
    DatasetReplay,
    EconomicInference,
    MatchRecord,
    ReplayPlayer,
    ReplayEvent,
    RobotSample,
    dataset_local_entity_id,
)


class DatasetReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DEFAULT_DATASET_PATH.is_file():
            raise unittest.SkipTest(f"dataset not found: {DEFAULT_DATASET_PATH}")
        cls.repository = DatasetRepository(DEFAULT_DATASET_PATH)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.repository.close()

    def test_schema_and_match_lookup(self) -> None:
        matches = self.repository.list_matches(limit=2)
        self.assertEqual(len(matches), 2)
        self.assertIsInstance(matches[0], MatchRecord)
        self.assertEqual(self.repository.get_match(matches[0].game_id), matches[0])

    def test_match_filters_are_parameterized(self) -> None:
        match = self.repository.list_matches(limit=1)[0]
        self.assertTrue(
            self.repository.list_matches(region=match.region, limit=1)
        )
        self.assertTrue(
            self.repository.list_matches(school=match.red_school, limit=1)
        )
        with self.assertRaises(ValueError):
            self.repository.list_matches(limit=-1)

    def test_replay_has_real_samples_and_cumulative_events(self) -> None:
        match = self.repository.list_matches(limit=1)[0]
        replay = self.repository.load_replay(match.game_id)
        self.assertGreater(replay.sample_count, 0)
        self.assertGreaterEqual(replay.duration_seconds, match.duration_seconds)
        frame = replay.frame_at(1.0)
        self.assertTrue(frame.samples)
        self.assertEqual({sample.team for sample in frame.samples}, {"红", "蓝"})
        self.assertTrue(all(event.time_seconds <= frame.time_seconds for event in frame.events))
        self.assertGreater(len(replay.events_between(0.0, match.duration_seconds)), 0)

    def test_frame_interpolates_position_and_wraps_heading(self) -> None:
        def sample(time: float, x: float, heading: float) -> RobotSample:
            return RobotSample(
                time, 1, "英雄", "红", "red", "blue", 100, 200,
                x, 2.0, 0.0, heading, 0.0, 0.0, 50.0, 0.0, 100.0,
                0.0, 0.0, 400.0, 400.0, False,
            )

        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 10)
        replay = DatasetReplay(
            match,
            (sample(1.0, 0.0, 179.0), sample(3.0, 4.0, -179.0)),
            (),
        )
        current = replay.frame_at(2.0).samples[0]
        self.assertAlmostEqual(current.x, 2.0)
        self.assertTrue(abs(abs(current.heading_degrees) - 180.0) < 1.0)

    def test_player_transport_stops_at_end_and_supports_seek(self) -> None:
        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 2)
        sample = RobotSample(
            1.0, 1, "英雄", "红", "red", "blue", 100, 200, 1.0, 1.0, 0.0,
            0.0, 0.0, 50.0, 0.0, 100.0, 0.0, 0.0, 0.0, 400.0, 400.0, False,
        )
        player = ReplayPlayer(DatasetReplay(match, (sample,), ()))
        player.play()
        player.update(3.0)
        self.assertTrue(player.ended)
        self.assertFalse(player.playing)
        self.assertEqual(player.seek(-1.0), 0.0)
        self.assertEqual(player.step(1.0), 1.0)
        self.assertEqual(player.slower(), 0.5)
        self.assertEqual(player.faster(), 1.0)

    def test_dataset_entity_ids_map_to_local_robot_and_building_slots(self) -> None:
        expected = {
            ("红", 1): 1, ("红", 2): 2, ("红", 3): 3, ("红", 4): 4,
            ("红", 6): 5, ("红", 7): 8, ("红", 10): 7, ("红", 11): 6,
            ("蓝", 101): 1, ("蓝", 102): 2, ("蓝", 103): 3, ("蓝", 104): 4,
            ("蓝", 106): 5, ("蓝", 107): 8, ("蓝", 110): 7, ("蓝", 111): 6,
        }
        for (team, dataset_id), local_id in expected.items():
            with self.subTest(team=team, dataset_id=dataset_id):
                self.assertEqual(dataset_local_entity_id(team, dataset_id), local_id)

    def test_event_intervals_are_half_open_to_prevent_duplicate_delivery(self) -> None:
        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 2)
        events = (
            ReplayEvent(1.0, "受击", 1, "英雄", "红", "red", 2, "英雄", "17mm", 20.0, ""),
            ReplayEvent(2.0, "发弹", 1, "英雄", "红", "red", None, "", "17mm", 1.0, ""),
        )
        replay = DatasetReplay(match, (), events)
        self.assertEqual(replay.events_between(0.0, 1.0), (events[0],))
        self.assertEqual(replay.events_between(1.0, 2.0), (events[1],))

    def test_economy_inference_uses_coin_and_cumulative_shot_deltas(self) -> None:
        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 3)

        def sample(time: float, remaining: float, shots_17: float, shots_42: float = 0.0) -> RobotSample:
            return RobotSample(
                time, 3, "步兵3", "红", "red", "blue", 100.0, 200.0,
                1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 50.0, 0.0, 100.0,
                shots_17, shots_42, 400.0, remaining, False,
            )

        replay = DatasetReplay(
            match,
            (sample(0.0, 400.0, 0.0), sample(1.0, 390.0, 10.0), sample(2.0, 240.0, 110.0)),
            (),
        )
        inference = EconomicInference()
        actions = []
        for second in range(3):
            actions.extend(inference.observe(replay.frame_at(second)))
        self.assertEqual(
            [(item.action, item.cost) for item in actions],
            [("规则书初始金币基线", 400.0), ("本地17mm兑换候选", 10.0), ("远程17mm兑换候选", 150.0)],
        )

    def test_remote_heal_is_confirmed_after_rulebook_six_second_delay(self) -> None:
        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 10)

        def sample(time: float, remaining: float, hp: float) -> RobotSample:
            return RobotSample(
                time, 1, "英雄", "红", "red", "blue", hp, 200.0,
                1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 50.0, 0.0, 100.0,
                0.0, 0.0, 400.0, remaining, False,
            )

        replay = DatasetReplay(
            match,
            (sample(0.0, 400.0, 100.0), sample(1.0, 330.0, 100.0), sample(7.0, 330.0, 200.0)),
            (),
        )
        inference = EconomicInference()
        actions = []
        previous = -1e-6
        for second in replay.times:
            actions.extend(inference.observe(
                replay.frame_at(second), replay.events_between(previous, second)
            ))
            previous = second
        self.assertTrue(any("远程回血候选（延迟确认）" == item.action for item in actions))

    def test_assembly_event_enables_rulebook_periodic_income_inference(self) -> None:
        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 20)

        def sample(time: float, total: float, remaining: float) -> RobotSample:
            return RobotSample(
                time, 1, "英雄", "红", "red", "blue", 100.0, 200.0,
                1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 50.0, 0.0, 100.0,
                0.0, 0.0, total, remaining, False,
            )

        assembly = ReplayEvent(2.0, "装配成功", None, "", "红", "red", None, "", "等级1", 8.0, "")
        replay = DatasetReplay(
            match,
            (sample(0.0, 400.0, 400.0), sample(2.0, 400.0, 400.0), sample(12.0, 450.0, 450.0)),
            (assembly,),
        )
        inference = EconomicInference()
        actions = []
        previous = -1e-6
        for second in replay.times:
            actions.extend(inference.observe(
                replay.frame_at(second), replay.events_between(previous, second)
            ))
            previous = second
        self.assertTrue(any(item.action == "装配成功·等级1" for item in actions))
        self.assertTrue(any(item.action == "装配/科技核心周期收入" and item.cost == 50.0 for item in actions))

    def test_assembly_income_uses_first_and_repeat_level_two_rewards(self) -> None:
        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 3)

        def sample(time: float) -> RobotSample:
            return RobotSample(
                time, 1, "英雄", "红", "red", "blue", 100.0, 200.0,
                1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 50.0, 0.0, 100.0,
                0.0, 0.0, 400.0, 400.0, False,
            )

        events = tuple(
            ReplayEvent(time, "装配成功", 2, "工程", "红", "red", None, "", level, 0.0, "")
            for time, level in ((1.0, "等级1"), (2.0, "等级2"), (3.0, "等级2"))
        )
        replay = DatasetReplay(
            match,
            (sample(0.0), sample(1.0), sample(2.0), sample(3.0)),
            events,
        )
        inference = EconomicInference()
        actions = []
        previous = -1e-6
        for time_seconds in replay.times:
            actions.extend(inference.observe(
                replay.frame_at(time_seconds), replay.events_between(previous, time_seconds)
            ))
            previous = time_seconds

        assembly_actions = [item for item in actions if item.action.startswith("装配成功·等级")]
        self.assertIn("每10秒新增50金币，累计50", assembly_actions[0].evidence)
        self.assertIn("每10秒新增25金币，累计75", assembly_actions[1].evidence)
        self.assertIn("每10秒新增10金币，累计85", assembly_actions[2].evidence)

    def test_auto_sentry_command_cost_is_a_low_confidence_candidate(self) -> None:
        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 2)

        def sample(time: float, remaining: float) -> RobotSample:
            return RobotSample(
                time_seconds=time, robot_id=7, robot_type="哨兵", team="红",
                school="red", opponent_school="blue", hp=300.0, max_hp=300.0,
                x=1.0, y=1.0, z=0.0, heading_degrees=0.0,
                chassis_power=50.0, small_heat=0.0, small_heat_limit=100.0,
                large_heat=0.0, large_heat_limit=0.0, shots_17mm=0.0,
                shots_42mm=0.0, team_coins=400.0, remaining_coins=remaining,
                vulnerable=False,
            )

        replay = DatasetReplay(
            match, (sample(0.0, 400.0), sample(1.0, 350.0)), (),
        )
        inference = EconomicInference()
        actions = []
        for time_seconds in replay.times:
            actions.extend(inference.observe(replay.frame_at(time_seconds)))

        candidate = next(item for item in actions if item.action == "自动哨兵指令费候选")
        self.assertEqual(candidate.cost, 50.0)
        self.assertLess(candidate.confidence, 0.5)

    def test_four_radar_countermeasures_enable_aerial_release_cost_candidate(self) -> None:
        match = MatchRecord("东部赛区", 1, "schedule", 1, 1, None, "red", "blue", None, None, 3)

        def sample(time: float, remaining: float) -> RobotSample:
            return RobotSample(
                time_seconds=time, robot_id=6, robot_type="空中", team="红",
                school="red", opponent_school="blue", hp=100.0, max_hp=100.0,
                x=1.0, y=1.0, z=0.0, heading_degrees=0.0,
                chassis_power=50.0, small_heat=0.0, small_heat_limit=100.0,
                large_heat=0.0, large_heat_limit=0.0, shots_17mm=0.0,
                shots_42mm=0.0, team_coins=400.0, remaining_coins=remaining,
                vulnerable=False,
            )

        radar_events = tuple(
            ReplayEvent(1.0, "雷达反制UAV", 6, "空中", "红", "red", None, "", "", None, "")
            for _ in range(4)
        )
        replay = DatasetReplay(
            match,
            (sample(0.0, 400.0), sample(1.0, 400.0), sample(2.0, 200.0)),
            radar_events,
        )
        inference = EconomicInference()
        actions = []
        previous = -1e-6
        for time_seconds in replay.times:
            actions.extend(inference.observe(
                replay.frame_at(time_seconds), replay.events_between(previous, time_seconds)
            ))
            previous = time_seconds

        candidate = next(
            item for item in actions
            if item.action == "反制后解除并呼叫空中支援候选"
        )
        self.assertEqual(candidate.cost, 200.0)
        self.assertEqual(candidate.confidence, 0.62)


if __name__ == "__main__":
    unittest.main()
