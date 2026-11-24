# Sheet materials are now Width × Length (see bom.0010). Moves Breadth
# into Length on staged dimension lines that are still open or pending,
# so they approve with the right size.

from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    SubmissionLine = apps.get_model('carpenter', 'SubmissionLine')
    lines = SubmissionLine.objects.filter(
        line_type='dimension', resource__material_type='sheet', breadth__gt=0,
        submission__status__in=['open', 'pending'],
    )
    for line in lines:
        line.length, line.length_unit = line.breadth, line.breadth_unit
        line.breadth = Decimal('0')
        line.save(update_fields=['breadth', 'length', 'length_unit'])


class Migration(migrations.Migration):

    dependencies = [
        ('carpenter', '0003_ai_review'),
        ('resources', '0011_wood_and_plywood_category'),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
