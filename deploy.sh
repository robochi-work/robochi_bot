#!/bin/bash
cd ~/robochi_bot
git pull origin develop
source venv/bin/activate
./venv/bin/pip install -r requirements.txt
./venv/bin/python manage.py migrate
./venv/bin/python manage.py collectstatic --noinput
./venv/bin/python manage.py compilemessages
systemctl restart gunicorn
systemctl restart celery-worker
systemctl restart celery-beat
