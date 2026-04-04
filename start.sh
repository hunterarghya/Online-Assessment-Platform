#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files (Django needs this to serve Admin CSS/JS)
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start Gunicorn
# config.wsgi refers to config/wsgi.py
echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT