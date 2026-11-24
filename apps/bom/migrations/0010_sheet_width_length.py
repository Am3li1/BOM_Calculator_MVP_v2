# Sheet materials (plywood / MDF) are now measured Width × Length instead
# of Width × Breadth. Moves the second measurement of every existing sheet
# WoodPart from Breadth into Length so its SFT (and cost) is unchanged.

import re
from decimal import Decimal

from django.db import migrations

_SWAP = re.compile(r'\b(breadth|length)(?=_in\b|_ft\b|\b)')


def _swap_formula(text):
    return _SWAP.sub(lambda m: 'length' if m.group(1) == 'breadth' else 'breadth', text)


def forwards(apps, schema_editor):
    WoodPart = apps.get_model('bom', 'WoodPart')
    for wp in WoodPart.objects.filter(resource__material_type='sheet', breadth__gt=0):
        formula = (wp.formula_expression or '').strip()
        if formula and re.search(r'\blength', formula):
            # A custom formula used both — swap the two fields exactly.
            wp.breadth, wp.length = wp.length, wp.breadth
            wp.breadth_unit, wp.length_unit = wp.length_unit, wp.breadth_unit
        else:
            wp.length, wp.length_unit = wp.breadth, wp.breadth_unit
            wp.breadth = Decimal('0')
        if formula:
            wp.formula_expression = _swap_formula(formula)
        wp.save(update_fields=['breadth', 'breadth_unit', 'length', 'length_unit',
                               'formula_expression'])


def backwards(apps, schema_editor):
    WoodPart = apps.get_model('bom', 'WoodPart')
    for wp in WoodPart.objects.filter(resource__material_type='sheet', length__gt=0):
        wp.breadth, wp.breadth_unit = wp.length, wp.length_unit
        if wp.formula_expression:
            wp.formula_expression = _swap_formula(wp.formula_expression)
        wp.save(update_fields=['breadth', 'breadth_unit', 'formula_expression'])


class Migration(migrations.Migration):

    dependencies = [
        ('bom', '0009_part_aliases_part_name_ta'),
        ('resources', '0011_wood_and_plywood_category'),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
