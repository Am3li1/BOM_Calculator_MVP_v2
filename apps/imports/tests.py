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