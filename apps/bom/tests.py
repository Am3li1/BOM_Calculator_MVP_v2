from decimal import Decimal

from django.test import TestCase

from apps.products.models import Product
from apps.resources.models import Resource
from apps.core.models import SystemConfig
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
        # wood_divisor defaults to 144 — confirm rather than assume,
        # since these expected values are hardcoded against it.
        cfg = SystemConfig.get_config()
        assert cfg.wood_divisor == 144, (
            f'Expected default wood_divisor=144, got {cfg.wood_divisor}. '
            f'These tests hardcode 144 into their expected values.'
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