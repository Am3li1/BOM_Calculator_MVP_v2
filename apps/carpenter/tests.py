from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bom.models import BOMItem, Part, WoodPart
from apps.products.models import Product
from apps.resources.models import Resource

from .models import BOMSubmission, SubmissionLine

_MODEL_BACKEND = 'django.contrib.auth.backends.ModelBackend'


def _make_admin(username='admin1'):
    return User.objects.create_user(username=username, password='x', is_staff=True)


class _SubmissionFixtures(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(product_code='TABLE-01', product_name='Coffee Table')
        cls.teak = Resource.objects.create(
            resource_name='Teak Wood', name_ta='தேக்கு', category='Carpentry Materials',
            material_type='solid_wood', unit='cft', rate=Decimal('4321.99'),
        )
        cls.hinge = Resource.objects.create(
            resource_name='Hinge', category='Hardware', unit='nos', rate=Decimal('87.65'),
        )

    def _submission(self, **kwargs):
        return BOMSubmission.objects.create(product=self.product, **kwargs)

    def _link(self, submission):
        return reverse('carpenter:link_form', kwargs={'token': submission.token})

    def _valid_post(self, **extra):
        data = {
            'bom_resource': [str(self.hinge.pk)],
            'bom_quantity': ['8'],
            'dim_resource': [str(self.teak.pk)],
            'dim_part': ['Table Top'],
            'dim_width': ['24'], 'dim_width_unit': ['in'],
            'dim_breadth': ['1'], 'dim_breadth_unit': ['in'],
            'dim_height': [''], 'dim_height_unit': ['in'],
            'dim_length': ['3'], 'dim_length_unit': ['ft'],
            'dim_pieces': ['1'],
            'note': 'Use seasoned wood',
        }
        data.update(extra)
        return data


class MagicLinkFormTests(_SubmissionFixtures):
    """The public, no-login carpenter form."""

    def test_token_is_long_and_random(self):
        a, b = self._submission(), self._submission()
        self.assertGreaterEqual(len(a.token), 40)
        self.assertNotEqual(a.token, b.token)

    def test_open_link_renders_without_login(self):
        response = self.client.get(self._link(self._submission()))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Coffee Table')
        self.assertContains(response, 'Teak Wood')

    def test_form_never_shows_rates_or_costs(self):
        # CLAUDE.md Security rule 3 — the public form must not leak pricing.
        content = self.client.get(self._link(self._submission())).content.decode()
        self.assertNotIn('₹', content)
        self.assertNotIn('4321', content)
        self.assertNotIn('87.65', content)
        self.assertNotIn('"rate"', content)            # no rate key in the picker JSON
        self.assertNotIn('effective_rate', content)

    def test_form_offers_existing_part_names(self):
        Part.objects.create(name='Table Top', name_ta='மேசை மேல்', aliases='Top')
        response = self.client.get(self._link(self._submission()))
        self.assertEqual(
            response.context['part_options'],
            [{'name': 'Table Top', 'name_ta': 'மேசை மேல்', 'aliases': 'Top'}],
        )

    def test_tamil_link_shows_tamil_labels_and_names(self):
        response = self.client.get(self._link(self._submission(language='ta')))
        self.assertContains(response, 'தேவையான பொருட்கள்')
        self.assertContains(response, 'தேக்கு')

    def test_unknown_token_is_404(self):
        response = self.client.get(reverse('carpenter:link_form', kwargs={'token': 'not-a-real-token'}))
        self.assertEqual(response.status_code, 404)

    def test_expired_link_is_closed(self):
        submission = self._submission(expires_at=timezone.now() - timedelta(minutes=1))
        response = self.client.get(self._link(submission))
        self.assertTemplateUsed(response, 'carpenter/link_closed.html')
        self.client.post(self._link(submission), self._valid_post())
        self.assertFalse(SubmissionLine.objects.exists())

    def test_revoked_link_is_closed(self):
        submission = self._submission(status=BOMSubmission.STATUS_REVOKED)
        self.client.post(self._link(submission), self._valid_post())
        self.assertFalse(SubmissionLine.objects.exists())

    def test_link_on_deleted_product_is_404(self):
        submission = self._submission()
        Product.objects.filter(pk=self.product.pk).update(is_deleted=True)
        self.assertEqual(self.client.get(self._link(submission)).status_code, 404)

    def test_submit_stages_lines_and_marks_pending(self):
        submission = self._submission()
        response = self.client.post(self._link(submission), self._valid_post(), follow=True)
        self.assertTemplateUsed(response, 'carpenter/link_closed.html')
        self.assertTrue(response.context['thanks'])

        submission.refresh_from_db()
        self.assertEqual(submission.status, BOMSubmission.STATUS_PENDING)
        self.assertEqual(submission.note, 'Use seasoned wood')
        self.assertIsNotNone(submission.submitted_at)

        bom_line = submission.lines.get(line_type='bom')
        self.assertEqual((bom_line.resource, bom_line.quantity), (self.hinge, Decimal('8')))
        dim_line = submission.lines.get(line_type='dimension')
        self.assertEqual(dim_line.part_name, 'Table Top')
        self.assertEqual(dim_line.length_unit, 'ft')

        # Staged only — the real BOM is untouched.
        self.assertFalse(BOMItem.objects.exists())
        self.assertFalse(WoodPart.objects.exists())

    def test_link_is_single_use(self):
        submission = self._submission()
        self.client.post(self._link(submission), self._valid_post())
        self.client.post(self._link(submission), self._valid_post(bom_quantity=['99']))
        self.assertEqual(submission.lines.count(), 2)
        self.assertFalse(submission.lines.filter(quantity=99).exists())

    def test_invalid_lines_save_nothing_and_keep_input(self):
        submission = self._submission()
        response = self.client.post(self._link(submission), self._valid_post(bom_quantity=['abc']))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['errors'])
        self.assertEqual(response.context['initial_rows']['bom'][0]['quantity'], 'abc')
        submission.refresh_from_db()
        self.assertEqual(submission.status, BOMSubmission.STATUS_OPEN)
        self.assertFalse(SubmissionLine.objects.exists())

    def test_empty_submission_is_rejected(self):
        submission = self._submission()
        response = self.client.post(self._link(submission), {
            'bom_resource': [''], 'bom_quantity': [''], 'dim_pieces': ['1'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['errors'])
        self.assertFalse(SubmissionLine.objects.exists())

    def test_duplicate_material_is_rejected(self):
        submission = self._submission()
        response = self.client.post(self._link(submission), self._valid_post(
            bom_resource=[str(self.hinge.pk), str(self.hinge.pk)], bom_quantity=['2', '3'],
        ))
        self.assertTrue(response.context['errors'])
        self.assertFalse(SubmissionLine.objects.exists())

    def test_inactive_resource_is_rejected(self):
        Resource.objects.filter(pk=self.hinge.pk).update(active=False)
        submission = self._submission()
        response = self.client.post(self._link(submission), self._valid_post())
        self.assertTrue(response.context['errors'])
        self.assertFalse(SubmissionLine.objects.exists())


class SubmissionReviewTests(_SubmissionFixtures):
    """Admin side: link creation, approve / reject / revoke."""

    def setUp(self):
        self.admin = _make_admin()
        self.client.force_login(self.admin, backend=_MODEL_BACKEND)

    def _pending(self):
        submission = self._submission()
        self.client.logout()
        self.client.post(self._link(submission), self._valid_post())
        self.client.force_login(self.admin, backend=_MODEL_BACKEND)
        submission.refresh_from_db()
        return submission

    def _approve_data(self, submission, **overrides):
        data = {'review_note': 'ok'}
        for line in submission.lines.all():
            data[f'include_{line.pk}'] = 'on'
            if line.line_type == 'bom':
                data[f'quantity_{line.pk}'] = str(line.quantity)
            else:
                data.update({
                    f'part_{line.pk}': line.part_name,
                    f'width_{line.pk}': '24', f'width_unit_{line.pk}': 'in',
                    f'breadth_{line.pk}': '1', f'breadth_unit_{line.pk}': 'in',
                    f'height_{line.pk}': '', f'height_unit_{line.pk}': 'in',
                    f'length_{line.pk}': '3', f'length_unit_{line.pk}': 'ft',
                    f'pieces_{line.pk}': '1',
                })
        data.update(overrides)
        return data

    def test_create_link(self):
        response = self.client.post(
            reverse('bom:submission_link_create', args=[self.product.pk]),
            {'carpenter_name': 'Murugan', 'carpenter_phone': '98765 43210',
             'language': 'ta', 'expiry_days': '3'},
        )
        submission = BOMSubmission.objects.get()
        self.assertRedirects(response, reverse('bom:submission_detail', args=[submission.pk]))
        self.assertEqual(submission.created_by, self.admin)
        self.assertEqual(submission.language, 'ta')
        self.assertAlmostEqual(
            (submission.expires_at - timezone.now()).total_seconds(), 3 * 86400, delta=60
        )

        detail = self.client.get(response.url)
        self.assertContains(detail, submission.token)
        self.assertContains(detail, 'https://wa.me/919876543210?text=')
        # The test client's host is "testserver" — a real-looking name,
        # so no "points to your own computer" warning.
        self.assertFalse(detail.context['link_is_local'])

    @override_settings(ALLOWED_HOSTS=['127.0.0.1', 'testserver'])
    def test_local_link_shows_warning(self):
        submission = self._submission()
        detail = self.client.get(
            reverse('bom:submission_detail', args=[submission.pk]), HTTP_HOST='127.0.0.1:8000',
        )
        self.assertTrue(detail.context['link_is_local'])
        self.assertContains(detail, 'points to your own computer')

    def test_expiry_is_clamped(self):
        self.client.post(
            reverse('bom:submission_link_create', args=[self.product.pk]), {'expiry_days': '365'},
        )
        submission = BOMSubmission.objects.get()
        self.assertLessEqual((submission.expires_at - timezone.now()).days, 30)

    def test_detail_shows_current_bom_quantity(self):
        BOMItem.objects.create(product=self.product, resource=self.hinge, quantity=Decimal('4'))
        submission = self._pending()
        response = self.client.get(reverse('bom:submission_detail', args=[submission.pk]))
        self.assertEqual(response.context['bom_rows'][0]['current_qty'], Decimal('4'))

    def test_approve_upserts_bom_and_creates_wood_parts(self):
        BOMItem.objects.create(product=self.product, resource=self.hinge, quantity=Decimal('4'))
        submission = self._pending()
        bom_line = submission.lines.get(line_type='bom')

        response = self.client.post(
            reverse('bom:submission_approve', args=[submission.pk]),
            self._approve_data(submission, **{f'quantity_{bom_line.pk}': '10'}),
        )
        self.assertRedirects(response, reverse('bom:list', args=[self.product.pk]))

        # Existing item updated in place (admin's edited qty), not duplicated.
        item = BOMItem.objects.get(product=self.product, resource=self.hinge)
        self.assertEqual(item.quantity, Decimal('10'))
        wood = WoodPart.objects.get(product=self.product)
        self.assertEqual((wood.part_name, wood.part.name), ('Table Top', 'Table Top'))

        submission.refresh_from_db()
        self.assertEqual(submission.status, BOMSubmission.STATUS_APPROVED)
        self.assertEqual(submission.reviewed_by, self.admin)

        # Read-only once reviewed.
        detail = self.client.get(reverse('bom:submission_detail', args=[submission.pk]))
        self.assertFalse(detail.context['editable'])
        self.assertNotContains(detail, 'Approve ticked lines')

    def test_unticked_lines_are_skipped(self):
        submission = self._pending()
        dim_line = submission.lines.get(line_type='dimension')
        data = self._approve_data(submission)
        del data[f'include_{dim_line.pk}']
        self.client.post(reverse('bom:submission_approve', args=[submission.pk]), data)
        self.assertTrue(BOMItem.objects.exists())
        self.assertFalse(WoodPart.objects.exists())

    def test_approve_with_bad_line_writes_nothing(self):
        submission = self._pending()
        dim_line = submission.lines.get(line_type='dimension')
        response = self.client.post(
            reverse('bom:submission_approve', args=[submission.pk]),
            self._approve_data(submission, **{f'width_{dim_line.pk}': 'oops'}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['errors'])
        self.assertFalse(BOMItem.objects.exists())
        self.assertFalse(WoodPart.objects.exists())
        submission.refresh_from_db()
        self.assertEqual(submission.status, BOMSubmission.STATUS_PENDING)

    def test_approve_twice_does_not_double_write(self):
        submission = self._pending()
        url = reverse('bom:submission_approve', args=[submission.pk])
        self.client.post(url, self._approve_data(submission))
        self.client.post(url, self._approve_data(submission))
        self.assertEqual(WoodPart.objects.count(), 1)

    def test_reject_leaves_bom_untouched(self):
        submission = self._pending()
        self.client.post(reverse('bom:submission_reject', args=[submission.pk]), {'review_note': 'wrong product'})
        submission.refresh_from_db()
        self.assertEqual(submission.status, BOMSubmission.STATUS_REJECTED)
        self.assertEqual(submission.review_note, 'wrong product')
        self.assertFalse(BOMItem.objects.exists())
        self.assertEqual(submission.lines.count(), 2)   # kept for history

    def test_revoke_kills_open_link(self):
        submission = self._submission()
        self.client.post(reverse('bom:submission_revoke', args=[submission.pk]))
        submission.refresh_from_db()
        self.assertEqual(submission.status, BOMSubmission.STATUS_REVOKED)
        self.client.logout()
        response = self.client.get(self._link(submission))
        self.assertTemplateUsed(response, 'carpenter/link_closed.html')

    def test_list_puts_pending_first(self):
        self._submission()
        pending = self._pending()
        response = self.client.get(reverse('bom:submission_list'))
        self.assertEqual(list(response.context['submissions'])[0], pending)

    def test_viewer_cannot_review(self):
        submission = self._pending()
        viewer = User.objects.create_user(username='viewer1', password='x')
        self.client.force_login(viewer, backend=_MODEL_BACKEND)
        for url in (reverse('bom:submission_list'),
                    reverse('bom:submission_detail', args=[submission.pk]),
                    reverse('bom:submission_approve', args=[submission.pk])):
            self.assertEqual(self.client.post(url).status_code, 403)
        self.assertFalse(BOMItem.objects.exists())
