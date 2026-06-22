# apps/core/management/commands/create_default_superuser.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Creates a default superuser if none exists'

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Superuser already exists — skipping.')
            return

        User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='changeme123',
        )
        self.stdout.write(
            self.style.SUCCESS('Superuser "admin" created successfully.')
        )