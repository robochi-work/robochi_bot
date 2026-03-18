# frontend-dev skill for robochi_bot

## What this folder is for
This folder contains the frontend skill files for robochi_bot.

Use this skill when the task is about:
- templates
- HTML
- CSS
- JavaScript / TypeScript in UI
- responsive layout
- modals, buttons, forms
- Telegram Mini App frontend behavior
- Telegram WebApp client-side integration

## Files in this folder
- `SKILL.md` — main frontend skill instructions
- `PROJECT_NOTES.md` — extra project-specific context
- `EXAMPLES.md` — examples of expected response style

## Where to place this folder
Recommended project location:

```text
<repo-root>/.codex/skills/frontend-dev/
```

That means:
- repository root = the top-level folder of your robochi_bot project
- inside it create `.codex`
- inside `.codex` create `skills`
- inside `skills` place this folder as `frontend-dev`

Expected result:

```text
<repo-root>/
  .codex/
    skills/
      frontend-dev/
        SKILL.md
        PROJECT_NOTES.md
        EXAMPLES.md
```

## What this skill should enforce
- first explain the task understanding
- give exact file and exact place for changes
- use "before / after"
- do not rewrite full files without request
- do not invent missing structure
- preserve Telegram Mini App behavior
- preserve analytics hooks where present

## How to use
When asking Codex for frontend help, provide:
- exact file content
- screenshot if visual issue exists
- exact block to change if known
- current Telegram WebApp snippet if integration is involved

## Good request examples
- "Вот текущий HTML и CSS блока выбора роли. Покажи точечные изменения в формате до/после."
- "Вот шаблон и CSS модалки. Исправь отображение в Telegram Mini App."
- "Вот текущий JS. Подключи кнопку к Telegram WebApp MainButton без переписывания всего файла."
