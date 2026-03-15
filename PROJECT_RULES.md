# PROJECT_RULES.md --- robochi_bot Development Rules

This document defines **rules that AI assistants and developers must
follow** when modifying the robochi_bot repository.

## General Principles

1.  Never break production.
2.  Always explain changes before applying them.
3.  Always give commands that can be executed on the server.
4.  Never expose secrets.

## Server Development Model

All development happens on the server through SSH.

Workflow:

1.  AI explains the task
2.  AI provides bash commands
3.  Artem executes them
4.  Artem returns terminal output
5.  AI analyzes the output

AI must assume it **cannot access the server directly**.

## Git Rules

Development branch:

develop

Typical workflow:

git add `<files>`{=html} git commit -m "description" git push origin
develop

Never push directly to main.

## Security Rules

Never commit:

.env tokens private keys

Never print:

Telegram bot token webhook secret database passwords

## Django Rules

Always run:

python3 manage.py check

When models change:

python3 manage.py makemigrations python3 manage.py migrate

Never modify migrations that were already applied in production.

## Service Restart Rules

If Python code changes:

sudo systemctl restart gunicorn.service

If Celery tasks change:

sudo systemctl restart celery-worker sudo systemctl restart celery-beat

## Logging

Gunicorn logs:

sudo journalctl -u gunicorn.service --since "10 min ago" --no-pager

Celery logs:

sudo journalctl -u celery-worker --since "10 min ago" --no-pager

## AI Behavior Rules

AI must:

explain tasks generate ready commands request output analyze logs

AI must not:

guess server state invent file paths invent secrets
