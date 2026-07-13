from django.db import migrations


def backfill_parts(apps, schema_editor):
    WoodPart = apps.get_model('bom', 'WoodPart')
    Part = apps.get_model('bom', 'Part')

    for wp in WoodPart.objects.all():
        name = (wp.part_name or '').strip() or wp.resource.resource_name
        part, _ = Part.objects.get_or_create(
            product=wp.product,
            name=name,
        )
        wp.part = part
        wp.save(update_fields=['part'])


def noop_reverse(apps, schema_editor):
    pass  # data migration — nothing to undo structurally


class Migration(migrations.Migration):

    dependencies = [
        ('bom', '0003_part_woodpart_part'),
    ]

    operations = [
        migrations.RunPython(backfill_parts, noop_reverse),
    ]