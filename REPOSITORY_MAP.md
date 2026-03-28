# REPOSITORY_MAP.md --- robochi_bot Repository Map

This file describes the structure of the robochi_bot repository so that
AI assistants understand where code and configuration live.

Last updated: 25.03.2026

## Root

robochi_bot/

Important files:

AGENTS.md ARCHITECTURE.md DEVELOPMENT_GUIDE.md PROJECT_RULES.md
REPOSITORY_MAP.md CLAUDE.md AI_QUICK_START.md AI_ARCHITECTURE_MAP.md
DJANGO_CODE_MAP.md TELEGRAM_MINIAPP_FLOW.md

## Django Core

manage.py

Main Django entry point.

## Applications (9 total)

### config/
Django settings and configuration.
- config/django/base.py, local.py, production.py --- settings files
- config/settings/celery.py, sentry.py, telegram_bot.py --- service configs
- config/urls.py --- root URL routing
- config/wsgi.py

### user/
User accounts, authentication, and identity management.
- User model (PK = Telegram ID, extends AbstractUser)
- AuthIdentity model --- links users to auth providers (telegram, phone, email, google)
- user/services.py --- get_or_create_user_from_telegram(), find_user_by_phone()
- UserFeedback model

### city/
Cities (TranslatableModel via django-parler).
Current cities: Київ(1), Одеса(2), Дніпро(3), Харків(4)

### work/
Work profiles, registration wizard, dashboard blocks, admin panel.
- UserWorkProfile, AgreementText models
- wizard (django-formtools): role → city → agreement steps
- block_registry: ChannelPreviewBlock, VacancyCreateFormBlock, ActiveVacanciesPreviewBlock
- work/service/: work_profile.py, publisher.py, events.py, subscriber_setup.py
- work/views/admin_panel.py — ЛК Администратора (6 views):
  admin_dashboard, admin_search_users, admin_search_vacancies,
  admin_vacancy_card, admin_block_user, admin_moderate_vacancy
- work/views/employer.py — ЛК Employer: employer_reviews, employer_faq
- work/views/index.py — роутинг по роли: admin→admin_dashboard, employer→employer_dashboard, worker→worker_dashboard
- work/templates/work/admin_dashboard.html — дашборд с табами и картой вакансий
- work/templates/work/admin_search_results.html — partial результаты поиска (AJAX)
- work/templates/work/admin_vacancy_card.html — карточка вакансии для админа
- work/templates/work/admin_moderate_vacancy.html — форма модерации вакансии
- work/templates/work/employer_dashboard.html — дашборд работодателя
- work/templates/work/employer_reviews.html — отзывы работодателя
- work/templates/work/employer_faq.html — FAQ для работодателя

### telegram/
Telegram bot integration and WebApp authentication.
- Channel, Group, ChannelMessage, GroupMessage, UserInGroup models
- Bot handlers (webhook, /start, contact, etc.)
- WebApp initData verification (HMAC-SHA256)
- Two auth endpoints: check-web-app/ and authenticate-web-app/

### vacancy/
Vacancy lifecycle, worker matching, call-checks.
- Vacancy, VacancyUser, VacancyUserCall, VacancyStatusHistory models
- Observer/Publisher pattern for vacancy events
- Celery tasks for call-checks and rotation
- vacancy/services/: call.py, vacancy_status.py, vacancy_formatter.py
- vacancy/templates/vacancy/vacancy_my_list.html — список вакансий работодателя
- vacancy/templates/vacancy/vacancy_detail.html — детальная страница вакансии

### payment/
Monobank Acquiring payment integration.
- MonobankPayment model (amounts in kopecks)
- payment/services.py: create_invoice(), process_webhook(), verify_monobank_signature()
- Telegram Payments have been REMOVED

### api/
REST API built with Django REST Framework.
- No models, no migrations (business logic stays in other apps)
- JWT authentication via Telegram initData (SimpleJWT)
- Swagger/OpenAPI docs via drf-spectacular
- api/serializers/, api/views/, api/permissions/, api/urls.py
- All endpoints under /api/v1/

### service/
Shared services used across apps.
- notifications.py, broadcast_service.py
- telegram_strategies.py, telegram_markup_factory.py
  (admin_vacancy_reply_markup: кнопка "Модерувати" → /work/admin-panel/vacancy/<id>/moderate/)

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

Gunicorn --- Django application server (unix socket, restart after any Python change)

Celery worker --- background tasks (vacancy tasks, rotation)

Celery beat --- scheduled tasks

Redis --- Celery broker (redis://localhost:6379/0)

PostgreSQL --- database

Nginx --- HTTP reverse proxy

## Static Files Architecture (updated 18.03.2026)

Primary CSS source: telegram/static/css/styles.css
Synced copy: static/css/styles.css

Both files must be identical. WhiteNoise collects from telegram/static/ (app priority).

After CSS changes:
1. Edit telegram/static/css/styles.css
2. cp telegram/static/css/styles.css static/css/styles.css
3. python3 manage.py collectstatic --clear --noinput
4. sudo systemctl restart gunicorn.service

JS files:
telegram/static/js/telegram.js --- WebApp init, theme, auth helper
telegram/static/js/menu.js --- menu toggle
