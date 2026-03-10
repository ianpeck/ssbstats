import unittest
from unittest.mock import patch

from ssbstats_app import create_app


class AppFactoryTests(unittest.TestCase):
    """Smoke tests for app creation and route registration."""

    def test_create_app_registers_expected_core_routes(self):
        """The app factory should expose the main page and API routes."""
        app = create_app()
        routes = {str(rule) for rule in app.url_map.iter_rules()}

        self.assertIn("/", routes)
        self.assertIn("/fighter/<name>", routes)
        self.assertIn("/head2head", routes)
        self.assertIn("/fight/<int:fight_id>", routes)
        self.assertIn("/api/fighter/<name>", routes)
        self.assertIn("/api/fight/<int:fight_id>", routes)
        self.assertIn("/api/compare", routes)

    def test_static_version_context_processor_is_available(self):
        """Templates should receive the static asset cache-busting version."""
        app = create_app()
        with app.test_request_context("/"):
            injected = app.template_context_processors[None][-1]()
            self.assertIn("static_v", injected)
            self.assertTrue(injected["static_v"])

    @patch("ssbstats_app.routes.pages.get_fight_detail_payload")
    def test_fight_detail_page_renders_when_payload_exists(self, mock_payload):
        """The fight detail page should render when a fight payload is available."""
        mock_payload.return_value = {
            "fight_id": 123,
            "hero_title": "Mario vs. Bowser",
            "hero_subtitle": "Season 1 · Month 1",
            "fight_type": "Singles",
            "championship": "",
            "ppv": "",
            "location": "Battlefield",
            "result_summary": "Mario def. Bowser",
            "layout": "singles",
            "stage_image": "",
            "participants_raw": [
                {"name": "Mario", "filename": "mario", "decision": "W"},
                {"name": "Bowser", "filename": "bowser", "decision": "L"},
            ],
            "participants": [
                {
                    "name": "Mario",
                    "filename": "mario",
                    "status": "Entrant",
                    "career": {"wins": 1, "losses": 0, "win_pct": "100.00%"},
                    "season": {"wins": 1, "losses": 0},
                    "location": {"wins": 1, "losses": 0},
                    "fight_type": {"wins": 1, "losses": 0},
                    "streak": {"label": "1-fight win streak"},
                    "elo_before": 1500,
                },
                {
                    "name": "Bowser",
                    "filename": "bowser",
                    "status": "Entrant",
                    "career": {"wins": 0, "losses": 1, "win_pct": "0.00%"},
                    "season": {"wins": 0, "losses": 1},
                    "location": {"wins": 0, "losses": 1},
                    "fight_type": {"wins": 0, "losses": 1},
                    "streak": {"label": "1-fight loss streak"},
                    "elo_before": 1500,
                },
            ],
            "matchup_context": None,
            "insights": ["Mario moved +12.5 Elo in this fight."],
            "navigation": {"previous_fight_id": None, "next_fight_id": None},
        }
        app = create_app()
        client = app.test_client()

        response = client.get("/fight/123")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mario vs. Bowser", response.data)

    @patch("ssbstats_app.routes.api.get_fight_detail_payload")
    def test_fight_detail_api_returns_404_for_missing_fight(self, mock_payload):
        """The fight detail API should return 404 when the fight does not exist."""
        mock_payload.return_value = None
        app = create_app()
        client = app.test_client()

        response = client.get("/api/fight/999999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Fight not found"})


if __name__ == "__main__":
    unittest.main()
