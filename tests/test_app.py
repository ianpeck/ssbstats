import unittest

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
        self.assertIn("/api/fighter/<name>", routes)
        self.assertIn("/api/compare", routes)

    def test_static_version_context_processor_is_available(self):
        """Templates should receive the static asset cache-busting version."""
        app = create_app()
        with app.test_request_context("/"):
            injected = app.template_context_processors[None][-1]()
            self.assertIn("static_v", injected)
            self.assertTrue(injected["static_v"])


if __name__ == "__main__":
    unittest.main()
