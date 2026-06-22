#!/usr/bin/env bash
# build.sh — Render runs this once during every deploy

# Exit immediately if any command fails
set -o errexit

# Install all Python packages
pip install -r requirements.txt

# Collect static files into staticfiles/ folder
# WhiteNoise serves them from there
python manage.py collectstatic --noinput

# Run database migrations
# On SQLite this creates/updates the db.sqlite3 file
python manage.py migrate

# Create superuser automatically if it doesn't exist
# Uses environment variables for credentials
python manage.py shell << 'EOF'
from django.contrib.auth.models import User
username = 'admin'
password = 'changeme123'
email = 'admin@example.com'
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print(f'Superuser "{username}" created.')
else:
    print(f'Superuser "{username}" already exists.')
EOF