import io
import unittest
from unittest.mock import patch

from PIL import Image

from ssbstats_app import create_app


def _stage(**overrides):
    stage = {"name": "Final Destination", "slug": "finaldestination", "image": "finaldestination", "series": "Smash Bros.",
             "origin": "Brawl", "fights": 3, "title_fights": 1, "title_changes": 1, "ppv_fights": 2, "fighters": 4,
             "first": 1, "last": 7, "king": {"name": "Kirby", "filename": "kirby", "wins": 2, "losses": 0}}
    stage.update(overrides)
    return stage


def _hub():
    kirby = {"name": "Kirby", "filename": "kirby"}
    wario = {"name": "Wario", "filename": "wario"}
    return {
        "stage": _stage(),
        "ppv_nights": 1,
        "most_wins": [{**kirby, "wins": 2, "losses": 0, "total": 2, "win_pct": 100.0}],
        "best": [], "worst": [],
        "upsets": [{"fight_id": 7, "season": 2, "month": 3, "winner": wario, "loser": kirby, "gap": 120, "title": None}],
        "rivalries": [{"a": kirby, "b": wario, "fights": 2, "a_wins": 2, "b_wins": 0, "last_fight_id": 9}],
        "titles": [{"title": "Melee", "slug": "melee", "belt": "melee", "trophy": False, "champions": [kirby], "label": "Kirby",
                    "season": 2, "month": 7, "ppv": "Final Destination Tournament", "fight_id": 9, "fight_type": "Tournament"}],
        "fights": [],
    }


class StagePageTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_routes_registered(self):
        routes = {str(rule) for rule in create_app().url_map.iter_rules()}
        for route in ("/stages", "/stages/<slug>", "/api/search-index", "/share/fighter/<name>.jpg", "/share/fight/<int:fight_id>.jpg"):
            self.assertIn(route, routes)

    @patch("ssbstats_app.routes.pages.get_stage_hub", return_value=None)
    def test_unknown_stage_is_404(self, _hub_mock):
        self.assertEqual(self.client.get("/stages/nowhere").status_code, 404)

    @patch("ssbstats_app.routes.pages.get_stage_hub")
    def test_stage_page_renders(self, hub_mock):
        hub_mock.return_value = _hub()
        response = self.client.get("/stages/finaldestination")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Final Destination", html)
        self.assertIn("Titles won here", html)
        self.assertIn("/head2head?f1=Kirby&amp;f2=Wario", html)

    @patch("ssbstats_app.routes.pages.get_stages_data")
    def test_stage_list_renders(self, data_mock):
        data_mock.return_value = {"stages": [_stage()], "unused": [_stage(name="Mementos", slug="mementos", fights=0, king=None)],
                                  "origins": ["Brawl"]}
        html = self.client.get("/stages").get_data(as_text=True)
        self.assertIn('href="/stages/finaldestination"', html)
        self.assertIn("Not fought on yet", html)


class SearchIndexTests(unittest.TestCase):
    @patch("ssbstats_app.routes.api.get_search_index")
    def test_api_returns_index(self, index_mock):
        index_mock.return_value = [{"type": "Page", "name": "Stages", "sub": "", "url": "/stages", "icon": "map"}]
        response = create_app().test_client().get("/api/search-index")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()[0]["url"], "/stages")
        self.assertIn("max-age", response.headers["Cache-Control"])


class ShareCardTests(unittest.TestCase):
    def test_fighter_card_is_a_1200x630_jpeg(self):
        from ssbstats_app.services.share_cards import render_fighter_card
        data = render_fighter_card(("Kirby", 134, 51, 1, ("Melee",), 9, 29, 4, "brawl"))
        image = Image.open(io.BytesIO(data))
        self.assertEqual((image.format, image.size), ("JPEG", (1200, 630)))

    @patch("ssbstats_app.routes.pages.render_fight_card", return_value=None)
    def test_missing_fight_card_is_404(self, _render_mock):
        self.assertEqual(create_app().test_client().get("/share/fight/999999.jpg").status_code, 404)


if __name__ == "__main__":
    unittest.main()
