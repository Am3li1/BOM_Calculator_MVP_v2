from django.db import migrations

def merge_duplicate_parts(apps, schema_editor):
    Part = apps.get_model('bom', 'Part')
    WoodPart = apps.get_model('bom', 'WoodPart')

    seen = {}  # normalized name -> canonical Part id
    for part in Part.objects.order_by('id'):
        key = part.name.strip().lower()
        if key not in seen:
            seen[key] = part.id
        else:
            canonical_id = seen[key]
            WoodPart.objects.filter(part_id=part.id).update(part_id=canonical_id)
            part.delete()

class Migration(migrations.Migration):
    dependencies = [
        ('bom', '0006_alter_woodpart_breadth_unit_and_more'),  # fill in your latest
    ]
    operations = [
        migrations.RunPython(merge_duplicate_parts, migrations.RunPython.noop),
    ]