from decimal import Decimal

from django.test import TestCase

from apps.products.models import Product
from apps.resources.models import Resource
from apps.bom.models import WoodPart


class WoodPartCalculatedQuantityTests(TestCase):
    """
    Regression tests for the CFT (solid_wood) / SFT (sheet) formula
    split introduced when material_type was added to Resource.
    Locks in the exact numbers verified manually during development —
    if any of these change, the formula has regressed.
    """

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            product_code='TEST-01', product_name='Test Product'
        )
        cls.teak = Resource.objects.create(
            resource_name='Teak Wood', category='Carpentry Materials',
            material_type='solid_wood', unit='cft', rate=Decimal('1000'),
        )
        cls.ply = Resource.objects.create(
            resource_name='Plywood 6mm', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('80'),
        )
        cls.other = Resource.objects.create(
            resource_name='Fevicol', category='Miscellaneous',
            material_type='other', unit='kg', rate=Decimal('300'),
        )

    def test_solid_wood_cft_formula(self):
        # (2in * 2in * 8ft * 4pcs) / 144 = 0.888888...
        wp = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg',
            width=2, width_unit='in',
            breadth=2, breadth_unit='in',
            length=8, length_unit='ft',
            pieces=4,
        )
        expected = (Decimal('2') * Decimal('2') * Decimal('8') * Decimal('4')) / Decimal('144')
        self.assertAlmostEqual(
            float(wp.calculated_quantity), float(expected), places=6
        )

    def test_solid_wood_unit_conversion_is_equivalent(self):
        # Same physical dimensions expressed in mm/cm must match the
        # inches/feet version exactly — proves conversion isn't a no-op.
        wp_in = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg A',
            width=2, width_unit='in', breadth=2, breadth_unit='in',
            length=8, length_unit='ft', pieces=4,
        )
        wp_mm = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg B',
            width=50.8, width_unit='mm',    # 50.8mm = 2in
            breadth=5.08, breadth_unit='cm', # 5.08cm = 2in
            length=8, length_unit='ft', pieces=4,
        )
        self.assertAlmostEqual(
            float(wp_in.calculated_quantity),
            float(wp_mm.calculated_quantity),
            places=6,
        )

    def test_sheet_sft_formula_uses_width_times_breadth(self):
        # 1.25ft * 1.25ft * 4pcs = 6.25 — matches the real spreadsheet
        # row this was validated against. No divisor for sheet goods.
        wp = WoodPart(
            product=self.product, resource=self.ply, part_name='Panel',
            width=1.25, width_unit='ft',
            breadth=1.25, breadth_unit='ft',
            length=99, length_unit='ft',   # deliberately absurd — must be ignored
            pieces=4,
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 6.25, places=6)

    def test_sheet_ignores_length_changes(self):
        # Changing Length must NOT change the result for sheet goods —
        # this is the exact bug (Width x Length) that was caught and fixed.
        base_kwargs = dict(
            product=self.product, resource=self.ply, part_name='Panel',
            width=4, width_unit='ft', breadth=8, breadth_unit='ft', pieces=1,
        )
        wp_a = WoodPart(length=1, length_unit='ft', **base_kwargs)
        wp_b = WoodPart(length=500, length_unit='ft', **base_kwargs)
        self.assertEqual(wp_a.calculated_quantity, wp_b.calculated_quantity)
        self.assertAlmostEqual(float(wp_a.calculated_quantity), 32.0, places=6)

    def test_other_material_type_uses_legacy_unit_naive_formula(self):
        # Unclassified resources keep the old raw-number/divisor formula
        # (no unit conversion) — deliberate, so reclassifying nothing
        # doesn't silently change existing costs.
        wp = WoodPart(
            product=self.product, resource=self.other, part_name='Misc',
            width=10, breadth=10, length=10, height=0, pieces=1,
            formula_type='standard',
        )
        expected = (Decimal('10') * Decimal('10') * Decimal('1') * Decimal('10') * Decimal('1')) / Decimal('144')
        self.assertAlmostEqual(
            float(wp.calculated_quantity), float(expected), places=6
        )


class WoodPartCustomFormulaTests(TestCase):
    """
    Regression tests for the per-Resource custom formula_expression
    override — must take priority over the built-in material_type
    formulas, and must fail loudly (not silently) on a bad formula.
    """

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            product_code='TEST-CF', product_name='Custom Formula Product'
        )
        cls.custom_resource = Resource.objects.create(
            resource_name='Special Veneer', category='Carpentry Materials',
            material_type='sheet',  # would normally use SFT (W x B)
            unit='sqft', rate=Decimal('50'),
            formula_expression='width_ft * length_ft * pieces / 2',
        )

    def test_custom_formula_overrides_material_type_default(self):
        # If material_type='sheet' default (W x B) were used, this
        # would ignore Length. The custom formula uses Length instead,
        # proving the override takes priority.
        wp = WoodPart(
            product=self.product, resource=self.custom_resource, part_name='Panel',
            width=4, width_unit='ft',
            breadth=999, breadth_unit='ft',   # deliberately absurd — must be ignored
            length=8, length_unit='ft',
            pieces=1,
        )
        # width_ft * length_ft * pieces / 2 = 4 * 8 * 1 / 2 = 16
        self.assertAlmostEqual(float(wp.calculated_quantity), 16.0, places=6)

    def test_bad_custom_formula_raises_loudly(self):
        from apps.core.safe_eval import FormulaError

        bad_resource = Resource.objects.create(
            resource_name='Broken Formula Resource', category='Miscellaneous',
            material_type='other', unit='nos', rate=Decimal('10'),
            formula_expression='width_in * undefined_variable',
        )
        wp = WoodPart(
            product=self.product, resource=bad_resource, part_name='X',
            width=1, width_unit='in', breadth=1, breadth_unit='in',
            length=1, length_unit='ft', pieces=1,
        )
        with self.assertRaises(FormulaError):
            wp.calculated_quantity

    def test_blank_formula_falls_back_to_material_type_default(self):
        # Sanity check: a resource WITHOUT a custom formula still uses
        # the normal solid_wood/sheet/other branching — the override
        # mechanism doesn't leak into resources that don't set it.
        plain_sheet = Resource.objects.create(
            resource_name='Plain MDF', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('60'),
        )
        wp = WoodPart(
            product=self.product, resource=plain_sheet, part_name='Panel',
            width=4, width_unit='ft', breadth=8, breadth_unit='ft',
            length=999, length_unit='ft', pieces=1,
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 32.0, places=6)


class WoodPartLevelFormulaPrecedenceTests(TestCase):
    """
    Regression tests for the three-tier formula precedence:
    WoodPart.formula_expression > Resource.formula_expression >
    built-in material_type formula.
    """

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            product_code='TEST-WP', product_name='WoodPart Formula Product'
        )
        cls.resource_with_formula = Resource.objects.create(
            resource_name='Veneer With Resource Formula',
            category='Carpentry Materials', material_type='sheet',
            unit='sqft', rate=Decimal('50'),
            formula_expression='width_ft * length_ft * pieces / 2',
        )

    def test_woodpart_formula_overrides_resource_formula(self):
        # Resource formula would give: 4 * 8 * 1 / 2 = 16
        # WoodPart formula must win instead: 4 * 8 * 1 / 4 = 8
        wp = WoodPart(
            product=self.product, resource=self.resource_with_formula,
            part_name='Panel',
            width=4, width_unit='ft', breadth=999, breadth_unit='ft',
            length=8, length_unit='ft', pieces=1,
            formula_expression='width_ft * length_ft * pieces / 4',
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 8.0, places=6)
        self.assertEqual(wp.formula_source, 'woodpart_custom')

    def test_blank_woodpart_formula_falls_back_to_resource_formula(self):
        # No WoodPart-level formula set -> falls through to the
        # resource's formula (not the built-in sheet SFT formula).
        wp = WoodPart(
            product=self.product, resource=self.resource_with_formula,
            part_name='Panel',
            width=4, width_unit='ft', breadth=999, breadth_unit='ft',
            length=8, length_unit='ft', pieces=1,
        )
        # width_ft * length_ft * pieces / 2 = 4 * 8 * 1 / 2 = 16
        self.assertAlmostEqual(float(wp.calculated_quantity), 16.0, places=6)
        self.assertEqual(wp.formula_source, 'resource_custom')

    def test_bad_woodpart_formula_raises_loudly(self):
        from apps.core.safe_eval import FormulaError

        plain_sheet = Resource.objects.create(
            resource_name='Yet Another MDF', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('60'),
        )
        wp = WoodPart(
            product=self.product, resource=plain_sheet, part_name='Panel',
            width=1, width_unit='ft', breadth=1, breadth_unit='ft',
            length=1, length_unit='ft', pieces=1,
            formula_expression='width_ft * nonsense_variable',
        )
        with self.assertRaises(FormulaError):
            wp.calculated_quantity

    def test_no_divisor_variable_available(self):
        # 'divisor' was removed as a formula variable entirely —
        # referencing it must raise, not silently resolve to 144.
        from apps.core.safe_eval import FormulaError

        plain_sheet = Resource.objects.create(
            resource_name='Divisor Test MDF', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('60'),
        )
        wp = WoodPart(
            product=self.product, resource=plain_sheet, part_name='Panel',
            width=1, width_unit='ft', breadth=1, breadth_unit='ft',
            length=1, length_unit='ft', pieces=1,
            formula_expression='width_ft * breadth_ft * pieces / divisor',
        )
        with self.assertRaises(FormulaError):
            wp.calculated_quantity

    def test_formula_source_reflects_precedence_tier(self):
        wp_builtin = WoodPart(
            product=self.product,
            resource=Resource.objects.create(
                resource_name='Plain Sheet 2', category='Carpentry Materials',
                material_type='sheet', unit='sqft', rate=Decimal('60'),
            ),
            part_name='Panel', width=4, breadth=8, length=1, pieces=1,
        )
        wp_resource = WoodPart(
            product=self.product, resource=self.resource_with_formula,
            part_name='Panel', width=4, breadth=8, length=1, pieces=1,
        )
        wp_woodpart = WoodPart(
            product=self.product, resource=self.resource_with_formula,
            part_name='Panel', width=4, breadth=8, length=1, pieces=1,
            formula_expression='width * breadth * pieces',
        )
        self.assertEqual(wp_builtin.formula_source, 'material_type_default')
        self.assertEqual(wp_resource.formula_source, 'resource_custom')
        self.assertEqual(wp_woodpart.formula_source, 'woodpart_custom')