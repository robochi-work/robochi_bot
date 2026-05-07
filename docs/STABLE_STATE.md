# STABLE STATE — НЕ ЛОМАТЬ

Этот файл описывает текущую рабочую конфигурацию.
Claude ОБЯЗАН прочитать этот файл перед любыми изменениями.

## .env — обязательные переменные
- REDIS_PASSWORD (hex, 64 символа) — без него Celery не работает
- DJANGO_SETTINGS_MODULE=config.django.production
- DATABASE_URL — PostgreSQL порт 5432 (НЕ 5433!)
- BOT_TOKEN — Telegram Bot API token

## Роли в группе вакансии (Вариант Б)
- Рабочий: promote can_manage_chat=True → title «Працівник»
- Заказчик: promote can_manage_chat=True + can_restrict_members=True → title «Роботодавець»
- Кик рабочего: ТОЛЬКО через бота/ЛК (оба юзера — админы группы)
- set_default_worker_permissions() — для рабочих
- set_default_owner_permissions() — для заказчиков

## Перекличка before_start
- check_before_start() пропускает рабочих с join_confirm после (start_time - 2h)
- check_before_20_start() кикает + блокирует через 20 мин без ответа

## Invite links
- Бот НИКОГДА не создаёт invite-ссылки
- can_invite_users=False во всех группах
- Ссылки только через Django admin

## Деплой
- set -a; source .env; set +a
- python3 manage.py collectstatic --clear --noinput
- sudo systemctl restart gunicorn.service
- Celery: sudo systemctl restart celery-worker.service celery-beat.service

## Тесты
- DJANGO_SETTINGS_MODULE=config.django.test (SQLite)
- pytest tests/ -x --timeout=60
- Все 225+ тестов должны проходить перед push
