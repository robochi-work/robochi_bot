# AGENTS.md --- robochi_bot AI Agent Instructions

This file explains how AI assistants must work with the **robochi_bot**
repository.

The project is developed directly on a production server using SSH
commands. AI agents do not have direct access to the server.

Development follows a command-response workflow described in the project
instructions fileciteturn0file0.

## Project

Repository: https://github.com/robochi-work/robochi_bot\
Branch: develop\
Server path: /home/webuser/robochi_bot/

Stack: - Python 3.11 - Django - pyTelegramBotAPI - PostgreSQL - Redis -
Celery - Gunicorn - Nginx - systemd

## AI Workflow

1.  AI explains the task
2.  AI provides ready-to-run bash commands
3.  Artem runs them on the server
4.  Artem sends terminal output
5.  AI analyzes results

AI must always assume it has **no server access**.

## Safety Rules

Never expose secrets. Never print bot tokens. Never commit `.env`. Never
disable Telegram WebApp verification.

## Restart After Changes

If Python code changes:

sudo systemctl restart gunicorn.service

If Celery tasks change:

sudo systemctl restart celery-worker sudo systemctl restart celery-beat

## Logs

Gunicorn:

sudo journalctl -u gunicorn.service --since "10 min ago" --no-pager

Celery:

sudo journalctl -u celery-worker --since "10 min ago" --no-pager
