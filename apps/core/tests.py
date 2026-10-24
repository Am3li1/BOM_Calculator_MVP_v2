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


class SearchByNameTests(TestCase):
    """apps.core.search.search_by_name — English name, name_ta and aliases."""

    def setUp(self):
        from apps.resources.models import Resource
        from apps.bom.models import Part

        self.Resource = Resource
        self.Part = Part
        self.teak = Resource.objects.create(
            resource_name='Teak Wood', category='Carpentry Materials',
            unit='cft', rate=Decimal('1000'),
            name_ta='தேக்கு மரம்', aliases='Burma Teak\nசாகுவான்',
        )
        self.ply = Resource.objects.create(
            resource_name='Plywood 6mm', category='Carpentry Materials',
            unit='sqft', rate=Decimal('80'),
            name_ta='ஒட்டு பலகை',
        )
        self.leg = Part.objects.create(name='Leg 1', name_ta='கால் 1', aliases='Front leg')
        Part.objects.create(name='Table Top', name_ta='மேசை மேல்பகுதி')

    def _search(self, query, model=None, field='resource_name'):
        from apps.core.search import search_by_name
        model = model or self.Resource
        return list(search_by_name(model.objects.all(), query, field))

    def test_english_name_is_case_insensitive(self):
        self.assertEqual(self._search('teak'), [self.teak])
        self.assertEqual(self._search('TEAK WOOD'), [self.teak])

    def test_tamil_name_exact_and_substring(self):
        self.assertEqual(self._search('தேக்கு மரம்'), [self.teak])
        self.assertEqual(self._search('தேக்கு'), [self.teak])
        self.assertEqual(self._search('பலகை'), [self.ply])

    def test_alias_match_english_and_tamil(self):
        self.assertEqual(self._search('burma'), [self.teak])
        self.assertEqual(self._search('சாகுவான்'), [self.teak])

    def test_decomposed_tamil_query_matches_composed_value(self):
        import unicodedata
        # The vowel sign in கொ (U+0BCA) decomposes under NFD into
        # U+0BC6 + U+0BBE — visually identical, different code points.
        word = 'கொட்டை'
        nfd = unicodedata.normalize('NFD', word)
        self.assertNotEqual(nfd, unicodedata.normalize('NFC', word))

        nut = self.Resource.objects.create(
            resource_name='Nut', category='Hardware', unit='nos',
            rate=Decimal('2'), name_ta=nfd,
        )
        nut.refresh_from_db()
        self.assertEqual(nut.name_ta, unicodedata.normalize('NFC', word))
        self.assertEqual(self._search(nfd), [nut])

    def test_query_whitespace_is_trimmed(self):
        self.assertEqual(self._search('  teak   wood '), [self.teak])

    def test_empty_query_returns_everything(self):
        self.assertEqual(len(self._search('')), 2)
        self.assertEqual(len(self._search(None)), 2)

    def test_no_match_returns_nothing(self):
        self.assertEqual(self._search('steel'), [])
        self.assertEqual(self._search('இரும்பு'), [])

    def test_works_on_part(self):
        self.assertEqual(self._search('கால்', self.Part, 'name'), [self.leg])
        self.assertEqual(self._search('front', self.Part, 'name'), [self.leg])
        self.assertEqual(self._search('leg 1', self.Part, 'name'), [self.leg])
