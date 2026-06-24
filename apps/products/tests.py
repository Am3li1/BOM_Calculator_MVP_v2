from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Product


User = get_user_model()


class ProductListPaginationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pass')
        Product.objects.bulk_create([
            Product(product_name=f'Product {i}', product_code=f'PROD{i}')
            for i in range(1, 28)
        ])

    def test_pagination_controls_appear_when_more_than_page_size(self):
        self.client.login(username='tester', password='pass')
        response = self.client.get(reverse('products:list'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['page_obj'].has_other_pages())
        self.assertContains(response, 'Page 1 of')
        self.assertContains(response, 'page=2')

    def test_filters_are_preserved_when_navigating_pages(self):
        self.client.login(username='tester', password='pass')
        response = self.client.get(
            reverse('products:list') + '?search=Product&status=active&page=2'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertContains(response, 'search=Product&amp;status=active&amp;page=1')
        self.assertContains(response, 'search=Product&amp;status=active')
