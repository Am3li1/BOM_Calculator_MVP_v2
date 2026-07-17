import os
import tempfile
from django.test import SimpleTestCase, TestCase
from decimal import Decimal
from apps.resources.models import Resource, ResourceCategory
from apps.products.models import Product
from apps.suppliers.models import Supplier, ResourceSupplier
from apps.bom.models import BOMItem
import pandas as pd
from .services import _sheet_exists

class ImportServicesTests(SimpleTestCase):
    def test_sheet_exists_closes_temp_file(self):
        fd, path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        df = pd.DataFrame({'A': [1, 2, 3]})
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

        self.assertTrue(_sheet_exists(path, 'Sheet1'))

        os.remove(path)
        self.assertFalse(os.path.exists(path))

class EffectiveRateTest(TestCase):

    def setUp(self):
        ResourceCategory.objects.create(name='Wood')
        self.resource = Resource.objects.create(
            resource_name='Teak', category='Wood',
            unit='SFT', rate=Decimal('500.00'),
        )
        self.supplier = Supplier.objects.create(supplier_name='ABC Wood')

    def test_master_rate_when_no_suppliers(self):
        self.assertEqual(self.resource.effective_rate, Decimal('500.00'))

    def test_preferred_supplier_rate_wins(self):
        ResourceSupplier.objects.create(
            resource=self.resource, supplier=self.supplier,
            supplier_rate=Decimal('420.00'), preferred=True, active=True,
        )
        self.assertEqual(self.resource.effective_rate, Decimal('420.00'))

    def test_manual_override_beats_supplier(self):
        ResourceSupplier.objects.create(
            resource=self.resource, supplier=self.supplier,
            supplier_rate=Decimal('420.00'), preferred=True, active=True,
        )
        self.resource.manual_override_rate = Decimal('380.00')
        self.resource.save()
        self.assertEqual(self.resource.effective_rate, Decimal('380.00'))


class BOMItemCostTest(TestCase):

    def setUp(self):
        ResourceCategory.objects.create(name='Wood')
        self.resource = Resource.objects.create(
            resource_name='Teak', category='Wood',
            unit='SFT', rate=Decimal('500.00'),
        )
        self.product = Product.objects.create(
            product_name='Test Table', product_code='TEST-TABLE',
        )
        self.bom_item = BOMItem.objects.create(
            product=self.product, resource=self.resource,
            quantity=Decimal('10.00'),
        )
        self.supplier = Supplier.objects.create(supplier_name='ABC Wood')

    def test_cost_uses_master_rate_when_no_supplier(self):
        # 10 × 500 = 5000
        self.assertEqual(self.bom_item.cost, Decimal('5000.00'))

    def test_cost_uses_preferred_supplier_rate(self):
        ResourceSupplier.objects.create(
            resource=self.resource, supplier=self.supplier,
            supplier_rate=Decimal('420.00'), preferred=True, active=True,
        )
        # After fix: 10 × 420 = 4200
        # This FAILS before the fix — proving the bug exists
        self.assertEqual(self.bom_item.cost, Decimal('4200.00'))

class ValidateWoodUnitTests(TestCase):
    """
    Regression tests for the WU/BU/LU unit validation added to
    validate_wood. Covers the two real bugs found against the actual
    production spreadsheet: garbage/blank units must be rejected, but
    LU='no' on a sheet-material row must NOT be (Length is genuinely
    unused there, per the Width x Breadth SFT formula).
    """

    def setUp(self):
        from .services import validate_wood
        self.validate_wood = validate_wood

        self.product = Product.objects.create(
            product_name='Test Table', product_code='TEST-TABLE',
        )
        self.teak = Resource.objects.create(
            resource_name='Teak Wood', category='Carpentry Materials',
            material_type='solid_wood', unit='cft', rate=Decimal('1000'),
        )
        self.ply = Resource.objects.create(
            resource_name='Plywood 6mm', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('80'),
        )

    def _write_wood_sheet(self, rows):
        """rows: list of dicts with Product/Resource/Width/Breath/Length/WU/BU/LU/Parts"""
        df = pd.DataFrame(rows)
        fd, path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Wood, Ply MDF', index=False)
            # validate_wood cross-references these via helper functions
            # that read from the same file
            pd.DataFrame({0: ['Test Table']}).to_excel(
                writer, sheet_name='Products', index=False, header=False
            )
            pd.DataFrame({
                'Resource': ['Teak Wood', 'Plywood 6mm'],
                'Category': ['Carpentry Materials', 'Carpentry Materials'],
                'Units': ['cft', 'sqft'],
                'Rate': [1000, 80],
            }).to_excel(writer, sheet_name='Resource', index=False)
        return path

    def test_valid_solid_wood_row_passes(self):
        path = self._write_wood_sheet([{
            'Product': 'Test Table', 'Resource': 'Teak Wood', 'Parts': 'Leg 1',
            'Width': 2, 'Breath': 2, 'Length': 8,
            'WU': 'in', 'BU': 'in', 'LU': 'ft',
        }])
        errors = self.validate_wood(path)
        os.remove(path)
        self.assertEqual(errors, [])

    def test_garbage_unit_is_rejected(self):
        path = self._write_wood_sheet([{
            'Product': 'Test Table', 'Resource': 'Teak Wood', 'Parts': 'Leg 1',
            'Width': 2, 'Breath': 2, 'Length': 8,
            'WU': '0.5', 'BU': 'in', 'LU': 'ft',   # garbage WU
        }])
        errors = self.validate_wood(path)
        os.remove(path)
        self.assertTrue(any('Width Unit' in e['message'] for e in errors))

    def test_sheet_row_with_lu_no_is_not_rejected(self):
        # This is the real production pattern: sheet-material rows use
        # LU='no' as a placeholder since Length isn't used in the SFT
        # formula. This must NOT be flagged as an error.
        path = self._write_wood_sheet([{
            'Product': 'Test Table', 'Resource': 'Plywood 6mm', 'Parts': 'Top Panel',
            'Width': 4, 'Breath': 8, 'Length': 1,
            'WU': 'ft', 'BU': 'ft', 'LU': 'no',
        }])
        errors = self.validate_wood(path)
        os.remove(path)
        self.assertEqual(errors, [])

    def test_sheet_row_with_bad_breadth_unit_is_still_rejected(self):
        # Sanity check: relaxing the Length check for sheet goods must
        # NOT relax the Breadth check — Breadth is load-bearing for SFT.
        path = self._write_wood_sheet([{
            'Product': 'Test Table', 'Resource': 'Plywood 6mm', 'Parts': 'Top Panel',
            'Width': 4, 'Breath': 8, 'Length': 1,
            'WU': 'ft', 'BU': 'garbage', 'LU': 'no',
        }])
        errors = self.validate_wood(path)
        os.remove(path)
        self.assertTrue(any('Breath Unit' in e['message'] for e in errors))