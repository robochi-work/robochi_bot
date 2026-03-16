# Инструкция для работы с Claude по проекту robochi_bot

## Схема работы

Артем работает над проектом robochi_bot. Claude помогает с разработкой, давая команды для выполнения на сервере. Артем копирует команды в терминал SSH и возвращает вывод в Claude.

## Важно: используй ClaudeCode везде где возможно

Под "ClaudeCode" подразумевается следующий рабочий цикл:
1. Claude формулирует задачу
2. Claude даёт готовые bash-команды для выполнения на сервере
3. Артем копирует команды в SSH-терминал и выполняет
4. Артем копирует вывод терминала обратно в Claude
5. Claude анализирует результат и даёт следующие команды

Claude НЕ имеет прямого доступа к серверу. Все команды выполняются Артемом вручную.

## Проект

- **Что это**: Django + Telegram Bot + Telegram Mini App (WebApp) для поиска подработки
- **Репозиторий**: github.com/robochi-work/robochi_bot (приватный)
- **Сервер**: `/home/webuser/robochi_bot/`
- **Домен**: robochi.pp.ua
- **Рабочая ветка**: `develop` (main синхронизируется вручную)

## Стек

Python 3.11, Django, pyTelegramBotAPI, PostgreSQL, Celery+Redis, Gunicorn (unix socket)+Nginx+systemd, WhiteNoise, django-formtools, django-parler, Sentry.

## Ключевые пути

- Код проекта: `/home/webuser/robochi_bot/`
- Контекст проекта: `docs/PROJECT_CONTEXT.md` — загружать в начале каждого диалога
- Env production: `/etc/robochi_bot.env` (нужен sudo для чтения)
- Env проект: `/home/webuser/robochi_bot/.env` (доступен без sudo)
- Gunicorn socket: `/home/webuser/robochi_bot/gunicorn.sock`
- Systemd unit: `/etc/systemd/system/gunicorn.service`
- Venv: `/home/webuser/robochi_bot/venv/`

## Как запускать manage.py на сервере

```bash
cd /home/webuser/robochi_bot
source venv/bin/activate
set -a; source .env; set +a
python3 manage.py shell -c "..."
```

## Как применять изменения

После редактирования Python-файлов:
```bash
sudo systemctl restart gunicorn.service
sudo systemctl status gunicorn.service --no-pager
```

## Как смотреть логи

```bash
sudo journalctl -u gunicorn.service --since "5 min ago" --no-pager
```

## Как коммитить

Все изменения — в ветку develop:
```bash
cd /home/webuser/robochi_bot
git add <файлы>
git commit -m "описание"
git push origin develop
```

## Рабочий цикл диалога

1. В начале диалога Артем загружает `docs/PROJECT_CONTEXT.md`
2. Claude читает контекст и понимает текущее состояние проекта
3. Работаем над задачами через ClaudeCode (команды → вывод → анализ → команды)
4. В конце сессии Claude готовит обновлённый PROJECT_CONTEXT.md
5. Артем заменяет файл через WinSCP и коммитит

## Обновление PROJECT_CONTEXT.md

Способ 1 — через WinSCP:
1. Claude генерирует файл для скачивания
2. Артем загружает через WinSCP в `/home/webuser/robochi_bot/docs/PROJECT_CONTEXT.md`
3. `git add docs/PROJECT_CONTEXT.md && git commit -m "docs: update" && git push origin develop`

Способ 2 — через скрипт:
```bash
cd /home/webuser/robochi_bot
./update_context.sh
```
(открывает nano, после сохранения автоматически делает commit и push в develop)

## Общие правила

- Перед каждым шагом формулируй задачу, чтоб мы правильно понимали друг друга
- Давай команды на русском языке (комментарии в коде — на английском)
- Все команды давай готовыми для копирования в терминал
- Если нужно отредактировать файл — используй `cat >`, `sed`, или `python3 /tmp/patch.py`
- Не забывай рестартовать gunicorn после изменений Python-файлов
- Для просмотра файлов используй `cat`, для проверки результата — `grep` или `head/tail`

## Новые приложения (добавлены 16.03.2026)

### api/ — REST API
- DRF приложение, БЕЗ моделей (без миграций). Только views, serializers, urls, permissions.
- Все endpoints под /api/v1/. JWT аутентификация через SimpleJWT.
- Для добавления нового endpoint: создай serializer в api/serializers/, view в api/views/, зарегистрируй в api/urls.py в v1_urlpatterns.
- Бизнес-логику НЕ писать в api/views — вызывай сервисы из соответствующих apps (vacancy/services/, user/services.py, payment/services.py).

### payment/ — Monobank платежи
- MonobankPayment модель. Суммы в копейках (4200 = 42.00 UAH).
- payment/services.py: create_invoice(), process_webhook(), verify_monobank_signature().
- Webhook Monobank не гарантирует порядок доставки — process_webhook() использует modifiedDate для идемпотентности.
- MONOBANK_API_TOKEN в .env (пока пустой).

### user/models.py — AuthIdentity
- При создании нового пользователя ОБЯЗАТЕЛЬНО создавать AuthIdentity запись.
- user/services.py: get_or_create_user_from_telegram() уже делает это автоматически.
- Для будущих провайдеров (email, google): добавить значение в AuthIdentity.Provider и реализовать auth flow.

### Принципы архитектуры
- Django views + templates = для Telegram Mini App (существующий функционал)
- DRF views + serializers = для REST API (новые клиенты: мобильные, SPA)
- Бизнес-логика живёт в services.py КАЖДОГО app, НЕ в views
- Оба механизма аутентификации (Session + JWT) работают параллельно
