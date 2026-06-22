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