from decimal import Decimal

from django.test import TestCase

from apps.core.units import to_inches, to_feet


class UnitConversionTests(TestCase):
    """Locks in the length-unit conversion math used by WoodPart."""

    def test_to_inches_feet(self):
        self.assertEqual(to_inches(1, 'ft'), Decimal('12'))

    def test_to_inches_mm(self):
        self.assertAlmostEqual(float(to_inches(25.4, 'mm')), 1.0, places=9)

    def test_to_feet_inches(self):
        self.assertEqual(to_feet(12, 'in'), Decimal('1'))

    def test_to_feet_metres(self):
        self.assertAlmostEqual(float(to_feet(1, 'm')), 3.28084, places=4)

    def test_invalid_unit_raises(self):
        with self.assertRaises(ValueError):
            to_inches(5, 'sqft')