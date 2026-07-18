from django.test import TestCase

from apps.resources.forms import ResourceForm


class ResourceFormFormulaExpressionTests(TestCase):
    """
    Tests the save-time validation of the custom formula field —
    the actual entry point an admin hits when typing a formula in
    the Resource create/edit form.
    """

    def _base_data(self, formula=''):
        return {
            'resource_name': 'Test Resource',
            'category': 'Carpentry Materials',
            'material_type': 'other',
            'unit': 'nos',
            'rate': '100',
            'active': 'on',
            'formula_expression': formula,
        }

    def test_blank_formula_is_valid(self):
        form = ResourceForm(data=self._base_data(''), categories=[])
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_formula_is_accepted(self):
        form = ResourceForm(
            data=self._base_data('width_in * breadth_in * length_ft / divisor'),
            categories=[],
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_unknown_variable_is_rejected_with_clear_error(self):
        form = ResourceForm(
            data=self._base_data('width_in * bogus_variable'),
            categories=[],
        )
        self.assertFalse(form.is_valid())
        self.assertIn('formula_expression', form.errors)
        self.assertIn('bogus_variable', str(form.errors['formula_expression']))

    def test_malicious_formula_is_rejected(self):
        form = ResourceForm(
            data=self._base_data('__import__("os").system("echo hi")'),
            categories=[],
        )
        self.assertFalse(form.is_valid())
        self.assertIn('formula_expression', form.errors)