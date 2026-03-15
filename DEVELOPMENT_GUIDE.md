# DEVELOPMENT_GUIDE.md --- robochi_bot Development Guide

This document explains how to safely develop the robochi_bot system.

## Server Paths

Project directory:

/home/webuser/robochi_bot/

Virtualenv:

/home/webuser/robochi_bot/venv/

Env files:

/home/webuser/robochi_bot/.env /etc/robochi_bot.env

## Running Django Commands

cd /home/webuser/robochi_bot

source venv/bin/activate

set -a; source .env; set +a

python3 manage.py check

## Deployment Steps

cd /home/webuser/robochi_bot

git pull origin develop

source venv/bin/activate

pip install -r requirements.txt

python3 manage.py migrate

python3 manage.py collectstatic --noinput

python3 manage.py compilemessages

sudo systemctl restart gunicorn sudo systemctl restart celery-worker
sudo systemctl restart celery-beat

## Git Rules

All work happens in branch:

develop

Example:

git add `<files>`{=html}

git commit -m "description"

git push origin develop

Main branch updated manually.

## Debugging

Check services:

sudo systemctl status gunicorn

Check logs:

sudo journalctl -u gunicorn.service --since "10 min ago"
