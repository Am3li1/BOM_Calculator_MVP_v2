# apps/bom/management/commands/find_mislabeled_parts.py
from django.core.management.base import BaseCommand
from apps.bom.models import Part, WoodPart


class Command(BaseCommand):
    help = "Lists Parts whose name matches their resource's name — fingerprint of the blank-Parts import bug."

    def handle(self, *args, **options):
        flagged = {}

        for wp in WoodPart.objects.select_related('product', 'resource', 'part'):
            if wp.part and wp.part.name.strip().lower() == wp.resource.resource_name.strip().lower():
                flagged.setdefault(wp.product.product_name, set()).add(wp.part.name)

        if not flagged:
            self.stdout.write(self.style.SUCCESS("No mislabeled parts found."))
            return

        for product_name, part_names in sorted(flagged.items()):
            self.stdout.write(f"\n{product_name}:")
            for name in sorted(part_names):
                self.stdout.write(f"  - '{name}'")

        self.stdout.write(self.style.WARNING(
            f"\n{len(flagged)} product(s) affected. Fix the source Excel Parts column for these, then re-import."
        ))