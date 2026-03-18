---
name: robochi_router
description: Route robochi_bot tasks to the most relevant specialized skill.
---

# Purpose
Use this skill to decide which specialized skill fits the task best.

# Routing
Use `frontend-dev` for:
- HTML
- CSS
- layout
- UI
- templates
- JavaScript
- responsive bugs
- visual issues

Use `backend-dev` for:
- Python
- Django
- models
- serializers
- views
- services
- API
- Celery
- Redis
- PostgreSQL

Use `telegram-miniapp` for:
- Telegram WebApp behavior
- MainButton
- BackButton
- viewport inside Telegram
- initData and launch context

Use `django-debug` for:
- traceback analysis
- runtime exceptions
- debugging backend failures

Use `deployment` for:
- VPS/server setup
- service restarts
- env vars
- deployment issues

# Rules
- Do not solve the task directly if a specialized skill clearly fits
- First choose the best specialized skill
- If task mixes multiple areas, start with the primary requested area
