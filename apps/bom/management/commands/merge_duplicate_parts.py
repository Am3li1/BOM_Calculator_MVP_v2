# apps/bom/management/commands/merge_duplicate_parts.py
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.bom.models import Part, WoodPart


class Command(BaseCommand):
    help = "Merges Part rows that differ only by case/whitespace, per product."

    def handle(self, *args, **options):
        with transaction.atomic():
            for product_id in Part.objects.values_list('product_id', flat=True).distinct():
                seen = {}  # normalized_name -> canonical Part
                for part in Part.objects.filter(product_id=product_id).order_by('pk'):
                    key = part.name.strip().lower()
                    if key not in seen:
                        seen[key] = part
                    else:
                        canonical = seen[key]
                        moved = WoodPart.objects.filter(part=part).update(part=canonical)
                        self.stdout.write(
                            f"Merged '{part.name}' (pk={part.pk}) into "
                            f"'{canonical.name}' (pk={canonical.pk}) — {moved} rows moved"
                        )
                        part.delete()