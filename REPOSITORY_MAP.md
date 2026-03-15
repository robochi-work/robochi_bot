# REPOSITORY_MAP.md --- robochi_bot Repository Map

This file describes the structure of the robochi_bot repository so that
AI assistants understand where code and configuration live.

## Root

robochi_bot/

Important files:

AGENTS.md ARCHITECTURE.md DEVELOPMENT_GUIDE.md PROJECT_RULES.md
REPOSITORY_MAP.md

## Django Core

manage.py

Main Django entry point.

## Applications

apps/

Typical structure:

apps/ users/ jobs/ telegram/

Responsibilities:

users --- authentication and profiles

jobs --- job listings and worker matching

telegram --- bot integration

## Templates

templates/

Django templates used for the web interface and Telegram Mini App pages.

## Static Files

static/

CSS JavaScript images

## Documentation

docs/

PROJECT_CONTEXT.md

This file stores the **current state of the project** and should be
loaded at the start of AI sessions.

## Configuration

config/

Django settings environment configuration

## Deployment Environment

Server path:

/home/webuser/robochi_bot/

Virtual environment:

/home/webuser/robochi_bot/venv/

Environment variables:

/home/webuser/robochi_bot/.env

System environment:

/etc/robochi_bot.env

## Services

Gunicorn --- Django application server

Celery worker --- background tasks

Celery beat --- scheduled tasks

Redis --- Celery broker

PostgreSQL --- database

Nginx --- HTTP reverse proxy
