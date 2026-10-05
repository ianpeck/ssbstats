import unittest

from ssbstats_app import create_app
from ssbstats_app.services.records import _ranked


class RankedTests(unittest.TestCase):
    """Record Book ranks: tied values share a rank, the next distinct value skips ahead."""

    def test_ties_share_rank(self):
        entries = _ranked([{"sort": v} for v in (29, 17, 17, 17, 16)])
        self.assertEqual([e["rank"] for e in entries], [1, 2, 2, 2, 5])
        self.assertEqual([e["tied"] for e in entries], [False, True, True, True, False])

    def test_tie_for_first(self):
        entries = _ranked([{"sort": v} for v in (5, 5, 3)])
        self.assertEqual([e["rank"] for e in entries], [1, 1, 3])
        self.assertTrue(entries[0]["tied"])


class RecordRoutesTests(unittest.TestCase):
    def test_routes_registered(self):
        routes = {str(rule) for rule in create_app().url_map.iter_rules()}
        self.assertIn("/records", routes)
        self.assertIn("/favicon.ico", routes)


if __name__ == "__main__":
    unittest.main()


class ChampionshipSlugTests(unittest.TestCase):
    def test_slugs_and_tag_halves(self):
        from ssbstats_app.services.championships import display_name, title_slug
        self.assertEqual(title_slug("Smash Bros."), "smashbros")
        self.assertEqual(display_name("Unified Tag 1"), "Unified Tag")
        self.assertEqual(display_name("Unified Tag 2"), "Unified Tag")
        self.assertEqual(title_slug("Unified Tag 2"), "unifiedtag")

    def test_title_route_registered(self):
        routes = {str(rule) for rule in create_app().url_map.iter_rules()}
        self.assertIn("/championships/<slug>", routes)
