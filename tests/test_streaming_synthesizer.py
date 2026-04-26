import unittest
from pathlib import Path

from streaming_jobs.synthesizer.config import load_physics
from streaming_jobs.synthesizer.match import MatchConfig, StockTarget, run_match
from streaming_jobs.synthesizer.model import normal_damage_cap


class StreamingSynthesizerTests(unittest.TestCase):
    """Regression tests for believable Gamecast simulation output."""

    @classmethod
    def setUpClass(cls):
        config_path = (
            Path(__file__).resolve().parents[1]
            / "streaming_jobs"
            / "config"
            / "fighter_physics.yaml"
        )
        cls.physics = load_physics(config_path)

    def test_normal_phase_damage_stays_weight_capped(self):
        """Light fighters should not linger near 200% in normal play."""
        scenarios = [
            ("Pichu", "Bowser", "Bowser", 3, 1),
            ("Pichu", "Mario", "Pichu", 3, 1),
            ("Jigglypuff", "DK", "DK", 3, 2),
            ("Fox", "Bowser", "Fox", 3, 1),
            ("Mario", "Pichu", "Mario", 5, 2),
            ("Pichu", "Bowser", "Pichu", 3, 0),
        ]

        for fa_name, fb_name, winner_name, total_stocks, winner_result in scenarios:
            with self.subTest(fa=fa_name, fb=fb_name, winner=winner_name, result=winner_result):
                target = StockTarget.from_match_result(total_stocks, winner_result)
                for seed in range(5):
                    cfg = MatchConfig(
                        match_id=f"test-{seed}",
                        fighter_a=self.physics[fa_name],
                        fighter_b=self.physics[fb_name],
                        winner_name=winner_name,
                        target=target,
                        seed=seed,
                    )
                    final = None
                    for event in run_match(cfg):
                        payload = event.to_dict()
                        final = payload
                        if payload["phase"] != "normal":
                            continue

                        for fighter in payload["fighters"]:
                            cap = normal_damage_cap(self.physics[fighter["name"]].weight)
                            self.assertLessEqual(fighter["damage"], cap + 0.1)

                    self.assertIsNotNone(final)
                    stocks = {fighter["name"]: fighter["stocks"] for fighter in final["fighters"]}
                    expected_winner_stocks = 1 if target.is_sudden_death else winner_result
                    loser_name = fb_name if winner_name == fa_name else fa_name
                    self.assertEqual(stocks[winner_name], expected_winner_stocks)
                    self.assertEqual(stocks[loser_name], 0)

    def test_damage_caps_are_weight_sensitive(self):
        self.assertLess(normal_damage_cap(self.physics["Pichu"].weight), 160)
        self.assertLess(normal_damage_cap(self.physics["Mario"].weight), 200)
        self.assertGreater(normal_damage_cap(self.physics["Bowser"].weight), 200)

    def test_known_distance_stall_seeds_finish_cleanly(self):
        """Late forced attacks should close distance instead of whiffing forever."""
        cases = [
            ("Corrin", "Shulk", "Shulk", 1, 471208634),
            ("Diddy Kong", "Luigi", "Diddy Kong", 2, 936212605),
            ("Isabelle", "Ridley", "Ridley", 1, 831320096),
            ("Chrom", "Fox", "Fox", 1, 19257122),
        ]

        for fa_name, fb_name, winner_name, winner_result, seed in cases:
            with self.subTest(fa=fa_name, fb=fb_name, winner=winner_name, seed=seed):
                target = StockTarget.from_match_result(3, winner_result)
                cfg = MatchConfig(
                    match_id=f"stall-{seed}",
                    fighter_a=self.physics[fa_name],
                    fighter_b=self.physics[fb_name],
                    winner_name=winner_name,
                    target=target,
                    seed=seed,
                )

                final = None
                for event in run_match(cfg):
                    final = event.to_dict()

                self.assertIsNotNone(final)
                self.assertLess(final["elapsed_sec"], 300)
                stocks = {fighter["name"]: fighter["stocks"] for fighter in final["fighters"]}
                loser_name = fb_name if winner_name == fa_name else fa_name
                self.assertEqual(stocks[winner_name], winner_result)
                self.assertEqual(stocks[loser_name], 0)


if __name__ == "__main__":
    unittest.main()
