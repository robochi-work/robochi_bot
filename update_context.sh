#!/bin/bash
echo "📝 Открываю файл для редактирования..."
nano docs/PROJECT_CONTEXT.md

echo "📦 Добавляю в git..."
git add docs/PROJECT_CONTEXT.md
git commit -m "docs: update PROJECT_CONTEXT $(date '+%Y-%m-%d %H:%M')"
git push origin develop

echo "✅ Контекст обновлён и запушен в develop!"
