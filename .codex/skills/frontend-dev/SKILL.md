---
name: robochi_bot_frontend
description: Frontend development for the robochi_bot Telegram Mini App (HTML, CSS, JS, templates, responsive UI).
---

# Purpose
Use this skill for frontend work in the robochi_bot project.

# When to use
- HTML templates
- CSS styling
- JavaScript or TypeScript in UI
- responsive layout
- buttons, forms, modals, cards
- Telegram WebApp client-side behavior
- visual bugs and interaction bugs

# Project context
- Project: robochi_bot
- Product type: Telegram Mini App
- Priority: stable mobile-first UI inside Telegram
- Preserve current architecture and visual direction unless redesign is explicitly requested
- Prefer Ukrainian UI text unless task says otherwise
- Explain to developer in Russian unless task says otherwise

# Rules
- Never invent files, routes, APIs, or components
- If current code is missing, ask for the exact file content
- Always prefer minimal local edits
- Do not rewrite whole files unless explicitly asked
- Always specify exact file path and exact place to edit
- Always provide code changes in "before / after" format
- First explain the issue, then show the fix
- Be careful with global CSS changes
- Be careful with Telegram Mini App viewport behavior

# Output format
1. Как я понял задачу
2. Что сейчас происходит / в чем проблема
3. Где именно менять
4. До
5. После
6. Что проверить после изменения
7. Возможные риски
