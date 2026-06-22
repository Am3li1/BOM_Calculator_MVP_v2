#!/usr/bin/env bash
# build.sh — Render runs this on every deploy

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate

# Create superuser using Django's built-in environment variable approach
# Django reads these three variables automatically
DJANGO_SUPERUSER_USERNAME=admin \
DJANGO_SUPERUSER_EMAIL=admin@example.com \
DJANGO_SUPERUSER_PASSWORD=changeme123 \
python manage.py createsuperuser --noinput || true