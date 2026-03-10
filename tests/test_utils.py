import unittest
from decimal import Decimal

from ssbstats_app.utils import (
    fighter_to_filename,
    normalize_champ_name,
    serialize_value,
    stage_to_filename,
)


class UtilsTests(unittest.TestCase):
    """Validate the small pure helpers used across routes and services."""

    def test_serialize_value_converts_decimal(self):
        """Decimal values should be converted to floats for JSON payloads."""
        self.assertEqual(serialize_value(Decimal("12.5")), 12.5)

    def test_fighter_to_filename_handles_banjo_override(self):
        """Known fighter aliases should map to the expected asset filename."""
        self.assertEqual(fighter_to_filename("Banjo & Kazooie"), "banjoandkazooie")

    def test_stage_to_filename_strips_punctuation_and_accents(self):
        """Stage names should normalize to ASCII-safe asset filename stems."""
        self.assertEqual(stage_to_filename("Pokémon Stadium 2"), "pokemonstadium2")

    def test_normalize_champ_name_collapses_unified_tag_variant(self):
        """Unified Tag title variants should render with the cleaned display name."""
        self.assertEqual(normalize_champ_name("Unified Tag 1"), "Unified Tag")


if __name__ == "__main__":
    unittest.main()

