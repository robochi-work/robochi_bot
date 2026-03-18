---
name: robochi_bot_django_debug
description: Debug Django tracebacks and backend failures in robochi_bot with step-by-step root cause analysis.
---

# Purpose
Use this skill for traceback-driven debugging in Django parts of robochi_bot.

# When to use
- Django traceback
- server-side exception
- failing form save
- serializer or view crash
- migration or model mismatch
- import/config/runtime backend errors

# Rules
- Start from the first relevant project frame in traceback
- Separate symptom from root cause
- Do not guess missing code
- Ask for exact traceback and exact file when needed
- Prefer minimal patch fixes
- State clearly if migration or restart is required

# Output format
1. Как я понял задачу
2. Разбор traceback по шагам
3. Корневая причина
4. Где именно менять
5. До
6. После
7. Что проверить после исправления
