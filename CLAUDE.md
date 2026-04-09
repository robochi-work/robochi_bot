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

После изменения Celery tasks:
```bash
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat
```

Перед применением изменений — проверка:
```bash
python3 manage.py check
```

## Как смотреть логи

```bash
# Gunicorn
sudo journalctl -u gunicorn.service --since "5 min ago" --no-pager
# Celery worker
sudo journalctl -u celery-worker --since "5 min ago" --no-pager
# Celery beat
sudo journalctl -u celery-beat --since "5 min ago" --no-pager
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

## Как запускать тесты

Тесты используют SQLite (настройки `config/django/test.py`) — не нужны права CREATEDB в PostgreSQL:
```bash
cd /home/webuser/robochi_bot
source venv/bin/activate
set -a; source .env; set +a
DJANGO_SETTINGS_MODULE=config.django.test python manage.py test tests.<имя_модуля> --verbosity=2
```

Файл тест-настроек: `config/django/test.py` — переопределяет DATABASE на SQLite `/tmp/test_robochi.sqlite3`.

## Django settings файлы

- `config/django/base.py` — базовые настройки
- `config/django/production.py` — продакшн (используется по умолчанию, задан в `.env`)
- `config/django/local.py` — локальная разработка
- `config/django/test.py` — тесты с SQLite
- `DJANGO_SETTINGS_MODULE=config.django.production` задан в `.env`

## Pre-commit hooks

При коммите автоматически запускаются:
- `ruff` — линтер Python
- `ruff-format` — форматтер (может изменить файлы, нужен второй проход)
- `django-upgrade` — апгрейд синтаксиса Django

Если ruff-format изменил файлы — pre-commit сделает второй проход автоматически.

## Полный деплой (после git pull)

```bash
cd /home/webuser/robochi_bot
source venv/bin/activate
set -a; source .env; set +a
pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py collectstatic --noinput
python3 manage.py compilemessages
sudo systemctl restart gunicorn
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat
```

## Общие правила

- Перед каждым шагом формулируй задачу, чтоб мы правильно понимали друг друга
- Давай команды на русском языке (комментарии в коде — на английском)
- Все команды давай готовыми для копирования в терминал
- Не забывай рестартовать gunicorn после изменений Python-файлов
- Если менялись Celery tasks — рестартовать celery-worker и celery-beat

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

## Frontend стиль (обновлено 18.03.2026)

### CSS архитектура
- **Основной CSS**: `telegram/static/css/styles.css` — это ЕДИНСТВЕННЫЙ источник стилей. Копия в `static/css/styles.css` синхронизируется вручную.
- **WhiteNoise** собирает статику из `telegram/static/` (app static dir) — он имеет приоритет над `static/` (project static dir). При изменении CSS нужно обновить ОБА файла.
- Стиль проекта: neumorphism (стальной градиент `#a6a9ab → #6d7074`, выпуклые кнопки с тенями).
- Dark theme: `@media (prefers-color-scheme: dark)` — переключает переменные на тёмные значения.
- НЕ используем: glass-morphism карточки, цветные рамки вокруг контента, `backdrop-filter`.

### Обновление CSS — обязательный порядок
1. Редактируем `telegram/static/css/styles.css`
2. Копируем: `cp telegram/static/css/styles.css static/css/styles.css`
3. `python3 manage.py collectstatic --clear --noinput`
4. `sudo systemctl restart gunicorn.service`

### Обновлённые шаблоны (18.03.2026)
- `vacancy/templates/vacancy/pre_call.html` — добавлены классы `btn-primary`, `btn-secondary`
- `vacancy/templates/vacancy/vacancy_form.html` — убран inline `style="background-color: blue"`
- `vacancy/templates/vacancy/vacancy_feedback.html` — обёрнут в `.vacancy-feedback`
- `vacancy/templates/vacancy/call.html`, `call_confirm.html`, `refind_start.html` — обёрнуты в `.call`

## Локализация / i18n (добавлено 19.03.2026)

### Как добавлять новые тексты
- Python код: `from django.utils.translation import gettext as _` → `_('English key text')`
- Шаблоны: `{% load i18n %}` → `{% trans "English key text" %}`
- НЕ писать hardcoded кириллические строки — всегда через `_()`

### Обновление переводов
```bash
set -a; source .env; set +a
python manage.py makemessages -l uk -l ru --no-wrap
# Заполнить переводы в locale/uk/ и locale/ru/ .po файлов
python manage.py compilemessages -l uk -l ru
sudo systemctl restart gunicorn.service
```

### Команды бота
При изменении описаний команд — вызвать из shell:
```bash
python manage.py shell -c "from telegram.handlers.set_commands import setup_bot_commands; setup_bot_commands()"
```

### Где хранятся переводы
- `locale/uk/LC_MESSAGES/django.po` — украинский
- `locale/ru/LC_MESSAGES/django.po` — русский
- User.language_code — поле в модели пользователя ('uk' по умолчанию)
- UserLanguageMiddleware активирует перевод по user.language_code

### Особенности
- vacancy_formatter.py: `with override('uk')` — тексты вакансий в каналах всегда на украинском
- Кнопка "Открыть приложение" в Telegram — системная, НЕ контролируется разработчиком

### Новые страницы и views (добавлено 20.03.2026)
- `work/views/legal.py` — legal_offer_view, отображает AgreementText type=offer
- `work/views/phone_required.py` — phone_required_view + resend_phone_request (API для повторной отправки кнопки телефона)
- `work/templates/work/legal_offer.html` — страница договора оферти
- `work/templates/work/phone_required.html` — страница "подтвердите телефон" с JS close WebApp + resend

### Проверка phone_number (добавлено 20.03.2026)
- `work/views/index.py` — редирект на phone_required если нет phone_number
- `work/views/work_profile.py` — questionnaire_redirect: редирект на phone_required если нет phone_number
- `telegram/views.py` — authenticate_web_app: редирект на /work/phone-required/ если нет phone_number

## ЛК Администратора и ЛК Employer (добавлено 25.03.2026)

### work/views/admin_panel.py — 6 views ЛК Администратора
- `admin_dashboard` — главный дашборд с табами Користувачі / Вакансії, карта вакансий
- `admin_search_users` — поиск пользователей (AJAX, по имени/username/phone)
- `admin_search_vacancies` — поиск вакансий (AJAX, по заголовку/работодателю)
- `admin_vacancy_card` — детальная карточка вакансии для администратора
- `admin_block_user` — блокировка/разблокировка пользователя (POST)
- `admin_moderate_vacancy` — форма модерации вакансии (approve/reject)

Доступ: только `user.is_staff == True`. Все views проверяют это условие.

### work/views/employer.py — views ЛК Employer
- `employer_reviews` — страница отзывов работодателя
- `employer_faq` — страница FAQ для работодателя

### Маршрутизация index.py (обновлено 25.03.2026)
`work/views/index.py` — логика редиректа в зависимости от роли:
- `user.is_staff` → redirect `work:admin_dashboard`
- Employer + 0 вакансий → redirect `vacancy:create`
- Employer + есть вакансии → render `employer_dashboard.html`
- Worker → render `worker_dashboard.html`

### Шаблоны ЛК Администратора
- `work/templates/work/admin_dashboard.html` — дашборд с табами, поиск, карта вакансий
- `work/templates/work/admin_search_results.html` — результаты поиска (partial для AJAX)
- `work/templates/work/admin_vacancy_card.html` — карточка вакансии
- `work/templates/work/admin_moderate_vacancy.html` — форма модерации

### Шаблоны ЛК Employer
- `work/templates/work/employer_dashboard.html` — главный дашборд работодателя
- `work/templates/work/employer_reviews.html` — отзывы
- `work/templates/work/employer_faq.html` — FAQ

### service/telegram_markup_factory.py (обновлено 25.03.2026)
- `admin_vacancy_reply_markup` — кнопка "Модерувати" теперь ведёт на ЛК Администратора
  (`/work/admin-panel/vacancy/<id>/moderate/`), а НЕ на `/admin/vacancy/vacancy/<id>/change/`

## Безопасность — важно для разработки (06.04.2026)

- **Django admin URL**: `/taya-panel/` — НЕ стандартный `/admin/`. Всегда давай именно этот URL.
- **Корневой URL `/`**: редирект неавторизованных пользователей на `https://robochi.work` (не страница входа).
- **Redis broker**: требует пароль — формат `redis://:PASSWORD@localhost:6379/0`. Пароль в `.env` как `REDIS_PASSWORD`.
- **auth_date expiry**: 7200 секунд (2 часа). Учитывай при отладке проблем аутентификации WebApp.

## Деплой — обязательный порядок (ВАЖНО!)

После КАЖДОГО изменения Python/HTML/CSS файлов на сервере — обязательно выполнить:
```bash
cd /home/webuser/robochi_bot
source venv/bin/activate
set -a; source .env; set +a
python3 manage.py collectstatic --clear --noinput
sudo systemctl restart gunicorn.service
```

Без collectstatic + restart изменения НЕ применятся! Это касается:
- HTML шаблонов (Django рендерит из рабочей директории — restart gunicorn обновляет процесс)
- CSS файлов (WhiteNoise отдаёт из staticfiles/)
- Python файлов (gunicorn кеширует в памяти)

## Кнопка Назад — единый стиль (06.04.2026)

Все кнопки "Назад" на страницах мини-приложения используют единый CSS-класс `page-back-btn`:
- Цвет: чёрный (светлая тема) / белый (тёмная тема)
- font-size: 15px, font-weight: 600, text-decoration: none
- Стиль определён в telegram/static/css/styles.css
- На странице "Поточні вакансії" (vacancy_my_list.html) — текст "← На головну" вместо "← Назад"

## Форма создания вакансии — ограничения времени (06.04.2026)

### Серверная логика (vacancy/views.py):
- По умолчанию date_choice = "now" (На сьогодні)
- При GET-запросе читается параметр ?date=now|tomorrow
- Для "now": start_time автоматически = now+1h (округлено до 15мин)
- Для "now": end_time автоматически = start_time+3h если текущее end_time невалидно
- Для "tomorrow": start_time и end_time = 00:00 по умолчанию

### Клиентская логика (vacancy_form.html JS):
- При переключении date_choice radio — JS делает redirect с ?date=now|tomorrow (страница перезагружается, Django рендерит правильные initial)
- НЕ используем JS для фильтрации <select> options (display:none / disabled / DOM rebuild) — это ломает Android Telegram WebApp native picker
- Валидация при submit через модальные окна:
  - time-modal: "Оберіть час початку роботи не раніше ніж через годину" (только для "На сьогодні")
  - time-min-modal: "Мінімальний робочий час — 3 години"
  - time-max-modal: "Максимальний робочий час — 12 годин"
  - phone-modal: "Введіть коректний номер телефону!"

### Бэкенд валидация (vacancy/forms.py):
- clean() — min 3h, max 12h длительность смены
- clean() — start_time >= now+1h для "На сьогодні"
- clean_contact_phone() — regex маска украинского номера

## Валидация телефона (06.04.2026)

### Employer (форма вакансии):
- JS валидация + модальное окно phone-modal при submit
- Бэкенд: clean_contact_phone() в VacancyForm

### Worker (бот):
- telegram/handlers/messages/worker_phone.py — regex валидация при вводе
- Сообщение: "Введіть коректний номер телефону!"
- Маска: +380XXXXXXXXX | 380XXXXXXXXX | 0XXXXXXXXX (пробелы/дефисы/скобки убираются)

## Модерация вакансии — кнопка удаления (06.04.2026)

- work/views/admin_panel.py: admin_delete_vacancy — POST view, удаляет вакансию + освобождает группу
- work/urls.py: path admin-panel/vacancy/<id>/delete/
- admin_moderate_vacancy.html: кнопка "ВИДАЛИТИ" с модальным окном подтверждения

## ЛК Employer — кнопка каналов (09.04.2026)

### Переименование и унификация
- Кнопка «Мої міста» переименована в «Загальна стрічка вакансій» во всех шаблонах
- Для ВСЕХ заказчиков (и с мультигородом, и без) кнопка ведёт на страницу employer_cities (work:employer_cities)
- Раньше для заказчиков без мультигорода кнопка вела напрямую по channel.invite_link — это ломалось в Telegram WebApp (ссылки t.me открывались во внутреннем WebView, а не в Telegram)

### Telegram.WebApp.openTelegramLink()
- Ссылки на каналы в employer_cities.html используют Telegram.WebApp.openTelegramLink() вместо target=_blank
- Это единственный правильный способ открыть t.me ссылку из Mini App — через JS SDK Telegram

### Кнопка на странице деталей вакансии
- На vacancy_detail.html добавлена кнопка «Загальна стрічка вакансій» между «Закрити вакансію» и «Перекличка»
- В контекст vacancy_detail view добавлены channel_invite_link и channel_title

### Затронутые файлы
- work/templates/work/employer_dashboard.html — унификация кнопки
- work/templates/work/employer_cities.html — переименование + openTelegramLink
- vacancy/templates/vacancy/vacancy_detail.html — новая кнопка
- vacancy/views.py — channel context в vacancy_detail
- work/views/employer.py — view без изменений (уже поддерживал single-city)
