#!/usr/bin/env bash
# Render build step. Exits non-zero on any failure so a bad deploy never goes live.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
