# Changelog — 29.03.2026

## 1. Ротация вакансий — привязка к кнопке (search_active)

### Проблема
Ротация была привязана к количеству людей в группе, а не к наличию кнопки «Я ГОТОВИЙ ПРАЦЮВАТИ».

### Решение
- Добавлено поле `Vacancy.search_active` (BooleanField, default=False)
- Миграция: `vacancy/migrations/0025_add_search_active_field.py`

### Кто управляет флагом search_active:
- True при: публикации (approved_channel_observer), повторном поиске (refind_observer), выходе рабочего (member_observer VacancySlotFreedObserver)
- False при: заполнении группы (VacancyIsFullObserver), остановке поиска (vacancy_stop_search)

### Изменённые файлы:
- vacancy/models.py, vacancy/tasks/resend.py, vacancy/views.py
- vacancy/services/observers/member_observer.py, approved_channel_observer.py, refind_observer.py, resend_channel_observer.py

## 2. Celery Worker/Beat — перенастройка

Перенастроены systemd-сервисы с /root/robochi_bot/ на /home/webuser/robochi_bot/ (User=webuser, EnvironmentFile, правильный venv).

## 3. Очистка неактивных пользователей

- user/tasks.py — cleanup_inactive_users_task (ежедневно 03:00 Киев)
- Удалённые Telegram аккаунты: bot.get_chat() проверка
- Неактивные 180 дней: Worker без VacancyUser, Employer без Vacancy
- config/settings/celery.py — задача в beat_schedule

## 4. Lifecycle Manager — зависание Mini App после сворачивания

- telegram/static/js/lifecycle.js — 4 сигнала обнаружения resume (activated, visibilitychange, focus, heartbeat)
- При resume: re-expand, disableVerticalSwipes, DOM reflow, CustomEvent tma:resumed
- templates/base.html — подключение lifecycle.js

## 5. Webhook и безопасность токена

### Проблема
Webhook сбрасывался через 1 секунду после установки. Причина: старый токен использовался другим процессом.

### Решение
- Перегенерирован токен через BotFather (старый утёк в git)
- .env убран из git (.gitignore)
- Gunicorn EnvironmentFile перенаправлен с /etc/robochi_bot.env на /home/webuser/robochi_bot/.env
- Токены в /root/robochi_bot/.env и /etc/robochi_bot.env заменены на DISABLED

## 6. Команда /help и MenuButton

- /help — inline-кнопка "Написати адміністратору" (ссылка на @robochi_work_admin)
- В группах: отправляет в личку пользователю, удаляет команду из группы
- Старые команды /start и /info заменены на одну /help
- MenuButton по умолчанию → /telegram/check-web-app/ (auth endpoint)
