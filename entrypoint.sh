#!/bin/bash
set -e

echo "🔄 Running migrations for SofizAdmin..."
python manage.py migrate --noinput

echo "🚀 Starting server..."
exec python manage.py runserver 0.0.0.0:8000
