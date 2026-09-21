#!/usr/bin/env bash
# Render build step. Exits non-zero on any failure so a bad deploy never goes live.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Render's free plan has no Shell tab, so the first administrator is created
# here instead of interactively. Set DJANGO_SUPERUSER_USERNAME, _EMAIL and
# _PASSWORD in the dashboard. createsuperuser exits non-zero once the account
# exists, which is the normal case on every redeploy -- so swallow that.
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --no-input ||
    echo "Superuser already exists -- skipping."
fi

# One-off demo clinic (patients, appointments, treatments, bills). Set
# SEED_DEMO=true for a single deploy, then delete the variable again.
if [ "${SEED_DEMO:-}" = "true" ]; then
  python manage.py seed_demo
fi
