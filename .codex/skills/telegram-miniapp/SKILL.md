---
name: robochi_bot_telegram_miniapp
description: Telegram Mini App specific guidance for robochi_bot, including WebApp behavior, viewport, init data, and client integration.
---

# Purpose
Use this skill when the task is specifically about Telegram Mini App behavior.

# When to use
- Telegram WebApp integration
- MainButton / BackButton behavior
- WebApp viewport issues
- initData / launch context
- Telegram-specific client-side restrictions
- differences between browser and Telegram in-app webview

# Rules
- Do not assume Telegram WebApp is initialized unless code shows it
- Be careful with fixed positioning and 100vh
- Separate Telegram-specific behavior from general frontend issues
- If integration code is missing, ask for the exact snippet
- Prefer minimal safe changes
- Keep explanations simple and step-by-step

# Output format
1. Как я понял задачу
2. Что относится именно к Telegram Mini App
3. Где именно менять
4. До
5. После
6. Что проверить именно внутри Telegram
