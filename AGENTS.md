# AGENTS.md — robochi_bot AI Agent Instructions

Version: 3.0

This document defines how AI assistants (Codex, Claude, ChatGPT, Cursor, etc.) must work with the **robochi_bot** repository.

The goal is to ensure that AI agents:
- understand the project architecture
- follow the correct development workflow
- avoid breaking production
- generate commands that can be executed on the server

This file must remain in the **root of the repository**.

Example path:
/home/webuser/robochi_bot/AGENTS.md


------------------------------------------------------------
MANDATORY PROJECT CONTEXT LOADING
------------------------------------------------------------

Before starting any task, AI agents must first read:

docs/PROJECT_CONTEXT.md

This file contains the **current state of the project** and must be treated as the primary source of truth.

Agents must:

- read docs/PROJECT_CONTEXT.md before proposing changes
- use it to understand current architecture and implementation state
- verify that proposed changes do not contradict the current project state
- re-check it when tasks affect architecture, Telegram flows, authentication, deployment, or background jobs

If the context file appears outdated or incomplete, the agent must explicitly warn about it.


------------------------------------------------------------
PROJECT OVERVIEW
------------------------------------------------------------

Project: robochi_bot

Repository:
https://github.com/robochi-work/robochi_bot

Primary development branch:
develop

Production server:
/home/webuser/robochi_bot/

Stack:

Python 3.11
Django
pyTelegramBotAPI
PostgreSQL
Redis
Celery
Gunicorn
Nginx
systemd


------------------------------------------------------------
DEVELOPMENT MODEL
------------------------------------------------------------

Development is performed directly on the **production server via SSH**.

AI agents do not have server access.

Workflow:

1. AI explains the task
2. AI produces ready-to-run bash commands
3. Artem executes commands via SSH
4. Artem returns terminal output
5. AI analyzes the output and continues

Agents must assume **no direct server access**.


------------------------------------------------------------
GIT WORKFLOW
------------------------------------------------------------

All development occurs in the branch:

develop

Typical workflow:

git add <files>
git commit -m "description"
git push origin develop

The main branch is updated manually after verification.

Agents must never push directly to main.


------------------------------------------------------------
RUNNING DJANGO COMMANDS
------------------------------------------------------------

cd /home/webuser/robochi_bot

source venv/bin/activate

set -a; source .env; set +a

Examples:

python3 manage.py check
python3 manage.py migrate
python3 manage.py shell
python3 manage.py collectstatic --noinput


------------------------------------------------------------
SERVICE RESTART RULES
------------------------------------------------------------

If Python backend code changes:

sudo systemctl restart gunicorn.service

If Celery tasks change:

sudo systemctl restart celery-worker
sudo systemctl restart celery-beat


------------------------------------------------------------
LOGS
------------------------------------------------------------

Gunicorn logs:

sudo journalctl -u gunicorn.service --since "10 min ago" --no-pager

Celery worker logs:

sudo journalctl -u celery-worker --since "10 min ago" --no-pager

Celery beat logs:

sudo journalctl -u celery-beat --since "10 min ago" --no-pager


------------------------------------------------------------
TELEGRAM MINI APP SECURITY
------------------------------------------------------------

Never trust initDataUnsafe.

The backend must verify Telegram WebApp initData using HMAC validation.

Verification must check:

- hash
- auth_date
- bot token

Reference:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app


------------------------------------------------------------
AI SAFETY RULES
------------------------------------------------------------

AI agents must:

- explain the task before executing commands
- provide ready-to-run commands
- request terminal output
- analyze logs when debugging
- avoid destructive operations

AI agents must never:

- expose secrets
- print bot tokens
- commit .env files
- disable Telegram WebApp verification


------------------------------------------------------------
SUMMARY
------------------------------------------------------------

robochi_bot is a Telegram Mini App platform built on Django.

Development happens directly on a Linux server through SSH commands.

AI assistants must follow the workflow and security rules defined in this file.