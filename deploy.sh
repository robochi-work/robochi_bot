#!/bin/bash
cd ~/robochi_bot
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py compilemessages
systemctl restart robochi_site
systemctl restart celery-worker
systemctl restart celery-beat
