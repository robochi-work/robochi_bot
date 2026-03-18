---
name: robochi_bot_backend
description: Backend development for robochi_bot using Python, Django, PostgreSQL, Redis, and Celery.
---

# Purpose
Use this skill for backend work in the robochi_bot project.

# When to use
- Python or Django logic
- models, serializers, views, services
- Celery tasks
- Redis-related background processing
- PostgreSQL-related logic
- API behavior
- validation and backend bugs
- migrations and traceback analysis

# Project context
- Project: robochi_bot
- Product type: backend for Telegram Mini App and related platform logic
- Priority: correctness, explicit logic, minimal regressions
- Preserve current architecture unless refactor is explicitly requested
- Explain to developer in Russian unless task says otherwise

# Rules
- Never invent models, endpoints, settings, or env variables
- If current code or traceback is missing, ask for the exact file/log
- Always prefer minimal local edits
- Do not rewrite large modules unless explicitly asked
- Always specify exact file path and exact place to edit
- Always provide changes in "before / after" format
- If migration is needed, say this explicitly
- Separate code changes from commands and test steps
- First explain root cause, then show the fix

# Output format
1. Как я понял задачу
2. Причина проблемы / что нужно изменить
3. Где именно менять
4. До
5. После
6. Миграции / команды / тесты
7. Что проверить после изменения
8. Возможные риски
