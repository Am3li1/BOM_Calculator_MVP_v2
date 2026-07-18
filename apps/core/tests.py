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


class SafeEvalTests(TestCase):
    """Tests for the safe formula expression evaluator."""

    def setUp(self):
        from apps.core.safe_eval import evaluate_formula, FormulaError
        self.evaluate_formula = evaluate_formula
        self.FormulaError = FormulaError
        self.vars = {
            'width_in': 2, 'breadth_in': 2, 'length_ft': 8,
            'pieces': 4, 'divisor': 144, 'height_in': 0,
        }

    def test_basic_arithmetic(self):
        result = self.evaluate_formula(
            'width_in * breadth_in * length_ft * pieces / divisor', self.vars
        )
        self.assertAlmostEqual(result, (2 * 2 * 8 * 4) / 144, places=9)

    def test_unknown_variable_raises(self):
        with self.assertRaises(self.FormulaError):
            self.evaluate_formula('width_in * nonexistent_var', self.vars)

    def test_syntax_error_raises(self):
        with self.assertRaises(self.FormulaError):
            self.evaluate_formula('width_in * * breadth_in', self.vars)

    def test_division_by_zero_raises(self):
        with self.assertRaises(self.FormulaError):
            self.evaluate_formula('width_in / 0', self.vars)

    def test_max_function_works(self):
        result = self.evaluate_formula('max(height_in, 1)', self.vars)
        self.assertEqual(result, 1)

    def test_disallowed_function_call_raises(self):
        with self.assertRaises(self.FormulaError):
            self.evaluate_formula('__import__("os")', self.vars)

    def test_attribute_access_raises(self):
        # Blocks the classic sandbox-escape pattern
        # (''.__class__.__mro__[1].__subclasses__() etc)
        with self.assertRaises(self.FormulaError):
            self.evaluate_formula('width_in.__class__', self.vars)

    def test_empty_formula_raises(self):
        with self.assertRaises(self.FormulaError):
            self.evaluate_formula('   ', self.vars)