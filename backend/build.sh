#!/usr/bin/env bash
# Render build command. Runs on every deploy.
#
# `set -o errexit` matters: without it a failed migration still produces a
# "successful" deploy that serves a broken app.
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Idempotent - updates existing rows rather than duplicating them, so it is
# safe on every deploy. Also recreates the demo learner on a fresh database,
# which Render's ephemeral disk gives us on each restart when no DATABASE_URL
# is attached.
python manage.py seed_vocab
