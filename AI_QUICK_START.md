# AI_QUICK_START.md — robochi_bot

## Purpose

This file allows any AI assistant (Codex, Claude, ChatGPT, Cursor, etc.) to quickly understand
the robochi_bot project in under one minute.

It provides the minimum essential context required to start working safely with the repository.

---

# Project Summary

Project name: robochi_bot

Purpose:
Telegram-based platform that connects workers and employers for temporary jobs.

Main components:

- Django backend
- Telegram Bot
- Telegram Mini App (WebApp)
- PostgreSQL database
- Redis
- Celery workers
- Gunicorn
- Nginx
- systemd

Repository:

https://github.com/robochi-work/robochi_bot

Primary development branch:

develop

Production server path:

/home/webuser/robochi_bot/

---

# Development Model

Development occurs directly on the production server via SSH.

AI agents do NOT have server access.

Workflow:

1. AI explains the task
2. AI generates ready-to-run bash commands
3. Artem runs commands via SSH
4. Artem sends terminal output
5. AI analyzes results and continues

This is called the **command-response workflow**.

---

# Essential Documentation Files

AI agents must read these files before working:

AGENTS.md  
docs/PROJECT_CONTEXT.md  
ARCHITECTURE.md  
PROJECT_RULES.md  
REPOSITORY_MAP.md  
DJANGO_CODE_MAP.md  
TELEGRAM_MINIAPP_FLOW.md  

These files describe:

- project rules
- architecture
- repository structure
- Telegram Mini App authentication
- Django code organization

---

# Running Django Commands

cd /home/webuser/robochi_bot

source venv/bin/activate

set -a; source .env; set +a

python3 manage.py check

---

# Restarting Services

If backend code changes:

sudo systemctl restart gunicorn.service

If Celery tasks change:

sudo systemctl restart celery-worker
sudo systemctl restart celery-beat

---

# Logs

Gunicorn:

sudo journalctl -u gunicorn.service --since "10 min ago" --no-pager

Celery:

sudo journalctl -u celery-worker --since "10 min ago" --no-pager

---

# Git Workflow

All development occurs in branch:

develop

Typical workflow:

git add <files>
git commit -m "description"
git push origin develop

Main branch is updated manually.

---

# Telegram Mini App Security

The backend must validate Telegram WebApp initData.

Verification must check:

- hash
- auth_date
- bot token

Reference:

https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app

Never trust initDataUnsafe.

---

# Safety Rules

AI must never:

- expose secrets
- print tokens
- commit .env
- disable Telegram validation

AI must always:

- explain tasks
- generate executable commands
- request terminal output
- verify results

---

# Quick Mental Model

User → Telegram Bot → WebApp → Django → Database
                                  → Redis → Celery

Infrastructure:

Telegram → Nginx → Gunicorn → Django

---

# AI Working Rule

Before proposing any changes:

1. Read AGENTS.md
2. Read docs/PROJECT_CONTEXT.md
3. Identify affected system layer:
   - Telegram
   - Django
   - Database
   - Celery
   - Infrastructure

Then propose a solution using AI_TASK_TEMPLATE.md.