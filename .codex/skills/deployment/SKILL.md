---
name: robochi_bot_deployment
description: Deployment and server-side operational guidance for robochi_bot on Linux/VPS environments.
---

# Purpose
Use this skill for deployment, server setup, process management, environment variables, and operational troubleshooting.

# When to use
- VPS or Linux deployment
- environment variables
- systemd / service restart logic
- gunicorn / uvicorn / nginx related tasks
- static files / collectstatic
- migrations on server
- Redis / Celery worker operational checks
- path, shell, permission, or service issues

# Rules
- Prefer safe step-by-step commands
- Separate diagnosis from fix
- Do not assume service names unless shown
- Ask for exact output if a command result is needed
- Warn before destructive commands
- Keep commands copy-paste ready

# Output format
1. Как я понял задачу
2. Что проверяем сначала
3. Команды по шагам
4. Что должно получиться
5. Что делать, если результат другой
