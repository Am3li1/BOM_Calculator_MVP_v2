#!/usr/bin/env bash
# build.sh — Render runs this on every deploy

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate

python manage.py create_default_superuser