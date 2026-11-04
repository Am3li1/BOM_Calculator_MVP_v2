# Splits wood / ply / MDF / board out of "Carpentry Materials" into their
# own "Wood and Plywood" category, so carpenters don't have to pick them
# out from among hinges, screws and glue. Moves only resources whose
# material_type is dimensional (sheet / solid_wood); a resource whose
# name already exists in the target category is left where it is, since
# (resource_name, category) is unique.

from django.db import migrations

OLD = 'Carpentry Materials'
NEW = 'Wood and Plywood'
DIMENSIONAL_TYPES = ('sheet', 'solid_wood')


def _move(apps, source, target):
    Resource = apps.get_model('resources', 'Resource')
    taken = set(Resource.objects.filter(category=target).values_list('resource_name', flat=True))
    for resource in Resource.objects.filter(category=source, material_type__in=DIMENSIONAL_TYPES):
        if resource.resource_name in taken:
            continue
        resource.category = target
        resource.save(update_fields=['category'])
        taken.add(resource.resource_name)


def forwards(apps, schema_editor):
    ResourceCategory = apps.get_model('resources', 'ResourceCategory')
    ResourceCategory.objects.get_or_create(name=NEW)
    _move(apps, OLD, NEW)


def backwards(apps, schema_editor):
    _move(apps, NEW, OLD)
    Resource = apps.get_model('resources', 'Resource')
    if not Resource.objects.filter(category=NEW).exists():
        apps.get_model('resources', 'ResourceCategory').objects.filter(name=NEW).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0010_resource_aliases_resource_name_ta'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
