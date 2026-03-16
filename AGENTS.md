# AGENTS.md — robochi_bot AI Agent Instructions

Version: 4.0

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
AI QUICK START LOADING RULE
------------------------------------------------------------

AI agents should first read:

AI_QUICK_START.md

before loading any other documentation.

This file provides a rapid overview of the project architecture, workflow, and server environment.

After reading AI_QUICK_START.md, agents must then load:

docs/PROJECT_CONTEXT.md

which contains the **current state of the project** and must be treated as the primary source of truth.


------------------------------------------------------------
MANDATORY PROJECT CONTEXT LOADING
------------------------------------------------------------

Before starting any task, AI agents must read:

docs/PROJECT_CONTEXT.md

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
Django 5.2
pyTelegramBotAPI 4.27
Django REST Framework 3.15 + SimpleJWT 5.4 (JWT auth for REST API)
django-cors-headers (CORS restricted to /api/*)
drf-spectacular 0.28 (Swagger/OpenAPI)
PostgreSQL
Redis
Celery
Gunicorn
Nginx
systemd
httpx (HTTP client for Monobank API)
ecdsa (ECDSA signatures for Monobank webhook)

Django applications (9):

config/        --- settings (base, local, production), urls, wsgi, celery
user/          --- User model (PK=Telegram ID), AuthIdentity, user/services.py
city/          --- City (TranslatableModel, django-parler)
work/          --- UserWorkProfile, AgreementText, wizard, dashboard blocks
telegram/      --- bot handlers, webhook, WebApp auth, Channel/Group models
vacancy/       --- Vacancy, VacancyUser, Celery tasks, Observer/Publisher
payment/       --- MonobankPayment model, payment/services.py
api/           --- REST API (DRF), no models, no migrations
service/       --- shared services (notifications, broadcast, telegram markup)


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

If Python backend code changes (Django views, models, serializers, services, api/):

sudo systemctl restart gunicorn.service

IMPORTANT: Any change to Python files requires gunicorn restart to take effect.

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
REST API (added 16.03.2026)
------------------------------------------------------------

New DRF-based REST API under /api/v1/:

- /api/v1/auth/telegram/        POST  --- get JWT from Telegram initData
- /api/v1/auth/token/refresh/   POST  --- refresh JWT
- /api/v1/users/me/             GET   --- current user profile
- /api/v1/vacancies/            GET   --- employer vacancies list
- /api/v1/vacancies/<pk>/       GET   --- vacancy detail
- /api/v1/payments/webhook/monobank/  POST  --- Monobank webhook (ECDSA verified)
- /api/docs/                          Swagger UI
- /api/schema/                        OpenAPI schema

Authentication:
- Session auth (existing) --- for Telegram Mini App (template views)
- JWT auth (new) --- for REST API (mobile clients, SPA)

Both mechanisms work in parallel.

Business logic must live in services.py of each app, NOT in api/views/.

------------------------------------------------------------
PAYMENTS (updated 16.03.2026)
------------------------------------------------------------

Telegram Payments have been REMOVED (PreCheckoutLog, Payment, handlers/invoice/).

Monobank Acquiring is the payment system:
- Model: payment/models.py (MonobankPayment)
- Services: payment/services.py (create_invoice, process_webhook, verify_monobank_signature)
- Webhook: /api/v1/payments/webhook/monobank/
- Env var: MONOBANK_API_TOKEN (currently empty, merchant token not yet configured)
- Amounts are in kopecks (4200 = 42.00 UAH)

------------------------------------------------------------
SUMMARY
------------------------------------------------------------

robochi_bot is a Telegram Mini App platform built on Django with a REST API layer.

Development happens directly on a Linux server through SSH commands.

AI assistants must follow the workflow and security rules defined in this file.