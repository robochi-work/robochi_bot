# backend-dev skill for robochi_bot

## What this folder is for
This folder contains the backend skill files for robochi_bot.

Use this skill when the task is about:
- Python
- Django
- PostgreSQL
- Redis
- Celery
- models
- serializers
- views
- services
- tasks
- migrations
- traceback debugging
- backend business logic
- Telegram-related backend integration

## Files in this folder
- `SKILL.md` — main backend skill instructions
- `PROJECT_NOTES.md` — extra project-specific context
- `EXAMPLES.md` — examples of expected response style

## Where to place this folder
Recommended project location:

```text
<repo-root>/.codex/skills/backend-dev/
```

That means:
- repository root = the top-level folder of your robochi_bot project
- inside it create `.codex`
- inside `.codex` create `skills`
- inside `skills` place this folder as `backend-dev`

Expected result:

```text
<repo-root>/
  .codex/
    skills/
      backend-dev/
        SKILL.md
        PROJECT_NOTES.md
        EXAMPLES.md
```

## What this skill should enforce
- first explain the task understanding
- give exact file and exact place for changes
- use "before / after"
- do not rewrite large modules without request
- do not invent missing structure
- state migrations explicitly
- separate code changes from commands/tests
- preserve integration contracts where present

## How to use
When asking Codex for backend help, provide:
- exact file content
- traceback if there is an error
- exact model / serializer / view / service / task fragment
- settings fragment if relevant
- env-related fragment if relevant
- Telegram integration fragment if the issue touches bot logic

## Good request examples
- "Вот traceback и текущий views.py. Разбери причину и покажи точечное исправление в формате до/после."
- "Вот models.py и serializers.py. Добавь поле и распиши что проверить после миграции."
- "Вот task code и related service code. Исправь баг без переписывания модуля."
