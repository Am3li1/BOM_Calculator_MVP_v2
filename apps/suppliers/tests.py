from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import Supplier


class SupplierViewsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('tester', 'tester@example.com', 'password')
        self.client.force_login(self.user)
        self.supplier = Supplier.objects.create(
            supplier_name='Test Co', phone_number='9999999999', gst_number='GST123', active=True
        )

    def test_supplier_list_has_view_button_and_link(self):
        url = reverse('suppliers:supplier_list')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        detail_url = reverse('suppliers:supplier_detail', args=[self.supplier.pk])
        # list page should contain a link to detail
        self.assertContains(resp, detail_url)
        # and a visible 'View' button text
        self.assertContains(resp, 'View')

    def test_supplier_detail_shows_empty_resources_message(self):
        url = reverse('suppliers:supplier_detail', args=[self.supplier.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.supplier.supplier_name)
        self.assertContains(resp, 'No resources linked to this supplier')
