# robochi_bot — Project Context
## Общая информация
- Сервер: /home/webuser/robochi_bot/ на Fornex VPS, домен robochi.pp.ua
- GitHub: github.com/robochi-work/robochi_bot, рабочая ветка: develop
- main синхронизируется: git reset --hard origin/develop && git push origin main --force

## Стек технологий
- Python 3.11, Django 5.2, pyTelegramBotAPI 4.27
- Django REST Framework 3.15 + SimpleJWT 5.4 (JWT-аутентификация для REST API)
- django-cors-headers (CORS ограничен /api/*), drf-spectacular 0.28 (Swagger/OpenAPI)
- PostgreSQL (psycopg2-binary), Celery 5.5 + Redis (redis://localhost:6379/0)
- Gunicorn (unix socket, 1 worker) + Nginx + systemd
- WhiteNoise, django-formtools, django-parler, Sentry
- httpx (HTTP-клиент для Monobank API), ecdsa (ECDSA-подписи Monobank webhook)
- Monobank Acquiring — платёжная интеграция (модель и сервис готовы, токен мерчанта пока не настроен)

## Django-приложения (9 штук)
- config/ — settings (base, local, production), urls, wsgi, celery config
- user/ — User (extends AbstractUser, PK=Telegram ID), UserFeedback, AuthIdentity, user/services.py
- city/ — City (TranslatableModel, django-parler). Текущие: Київ(1), Одеса(2), Дніпро(3), Харків(4)
- work/ — UserWorkProfile, AgreementText, wizard (formtools), dashboard blocks (block_registry)
- telegram/ — Channel, Group, ChannelMessage, GroupMessage, UserInGroup, bot handlers, webhook, WebApp auth
- vacancy/ — Vacancy, VacancyUser, VacancyUserCall, VacancyStatusHistory, Observer/Publisher, Celery tasks
- payment/ — MonobankPayment модель, payment/services.py (create_invoice, process_webhook, verify_monobank_signature)
- api/ — REST API (DRF). JWT через Telegram initData, Swagger docs. Без моделей (без миграций)
- service/ — общие сервисы (notifications, broadcast, telegram markup/strategies)

## URL-маршруты
Существующие (Django views + templates для Mini App):
- / → dashboard (index)
- /admin/ → Django Admin
- /telegram/webhook-{SECRET}/ → Telegram bot webhook (POST, csrf_exempt)
- /telegram/check-web-app/ → WebApp initData check
- /telegram/authenticate-web-app/ → WebApp auth + Django session
- /work/wizard/<step>/ → Registration wizard (role → city → agreement)
- /work/profile/ → legacy (НА УДАЛЕНИЕ)
- /vacancy/create/ → создание вакансии
- /vacancy/<pk>/call/<type>/ → переклички
- /vacancy/<pk>/refind/ → повторный поиск
- /vacancy/<pk>/feedback/ → отзывы

Новые (DRF REST API):
- /api/v1/auth/telegram/ → POST, получение JWT по Telegram initData
- /api/v1/auth/token/refresh/ → POST, обновление JWT
- /api/v1/users/me/ → GET, профиль текущего пользователя
- /api/v1/vacancies/ → GET, список вакансий заказчика
- /api/v1/vacancies/<pk>/ → GET, детали вакансии
- /api/v1/payments/webhook/monobank/ → POST, webhook Monobank (csrf_exempt, без авторизации, верификация ECDSA)
- /api/docs/ → Swagger UI
- /api/schema/ → OpenAPI schema

## Аутентификация (два параллельных механизма)
1. Django Session (текущий) — для Mini App. authenticate-web-app/ проверяет HMAC-SHA256 initData, создаёт Django session. Используется template views. Проверка phone_number убрана (телефон сохраняется до открытия WebApp).
2. JWT (новый) — для REST API. /api/v1/auth/telegram/ принимает initData, валидирует, выдаёт access+refresh токены. Для будущих мобильных клиентов.

AuthIdentity модель (user/models.py) — связывает User с провайдерами аутентификации:
- provider: telegram, phone, email, google
- provider_uid: уникальный идентификатор у провайдера
- unique_together: (provider, provider_uid)
Позволяет аутентификацию по номеру телефона для Android/iOS без Telegram.

## Платежи
- Telegram Payments УДАЛЕНЫ (PreCheckoutLog, Payment, handlers/invoice/)
- Monobank Acquiring: MonobankPayment в payment/models.py. Статусы: created→processing→hold→success/failure/reversed/expired.
  payment/services.py: create_invoice(), process_webhook() (с modifiedDate идемпотентностью), verify_monobank_signature() (ECDSA).
  Webhook: /api/v1/payments/webhook/monobank/. Env: MONOBANK_API_TOKEN (пока пустой).

## Локализация (i18n) — обновлено 19.03.2026
Основной язык: украинский (uk). Дополнительный: русский (ru).

### Инфраструктура
- USE_I18N=True, LANGUAGE_CODE='uk', LANGUAGES=[('ru','Русский'),('uk','Українська')]
- django-parler: PARLER_DEFAULT_LANGUAGE_CODE='uk', City — TranslatableModel
- Middleware: django.middleware.locale.LocaleMiddleware + user.middleware.UserLanguageMiddleware (читает user.language_code из БД)
- User.language_code — поле модели (choices=LANGUAGES, default='uk')
- locale/uk/LC_MESSAGES/django.po|mo, locale/ru/LC_MESSAGES/django.po|mo — заполнены, скомпилированы
- Все тексты в Python: gettext/_(), в шаблонах: {% trans %}. Нет hardcoded строк.

### Telegram Bot
- Команды бота (setMyCommands) зарегистрированы на uk, ru и default (fallback=uk)
- setup_bot_commands() в telegram/handlers/set_commands.py — вызывать из shell при деплое
- MenuButton текст ('Start') — через _(), зависит от активного языка
- Кнопка "Открыть приложение" на профиле бота — системная кнопка Telegram, зависит от языка клиента пользователя, НЕ контролируется разработчиком

### Известные особенности
- vacancy_formatter.py: with override('uk') — тексты вакансий для каналов принудительно на украинском
- 3 msgid на украинском в commands.py ('Надіслати номер телефону' и др.) — работают, но нестандартные ключи
- Fuzzy-строки в .po: только 1/1 (заголовок файла) — норма

## Сервисный слой
- user/services.py: get_or_create_user_from_telegram(), find_user_by_phone()
- payment/services.py: create_invoice(), process_webhook(), verify_monobank_signature(), get_monobank_pubkey()
- vacancy/services/: call.py, vacancy_status.py, vacancy_formatter.py, invoice.py + observers/
- work/service/: work_profile.py, publisher.py, events.py
- service/: notifications.py, broadcast_service.py, telegram_strategies.py

## Observer/Publisher
- VacancyEventPublisher — VACANCY_CREATED, APPROVED, REJECTED, NEW_MEMBER, LEFT_MEMBER, CALL events, REFIND, CLOSE, DELETE, FEEDBACK
- WorkEventPublisher — WORK_PROFILE_COMPLETED
- Подписки: vacancy/services/observers/subscriber_setup.py, work/service/subscriber_setup.py

## Celery Tasks (vacancy/tasks/)
- before_start_call_task — перекличка за 2 часа
- start_call_check_task — начало работы
- final_call_check_task — окончание работы
- after_first_call_check_task — проверка через 20 мин
- close_vacancy_task — закрытие вакансии +2ч после окончания
- resend_vacancies_to_channel_task — ротация каждые 5 мин
- test_heartbeat — health check

## БД (текущее состояние)
- 5 пользователей, все language_code='uk'
- Каналы: Харків ✓, Одеса ✓, Дніпро — нет invite_link, Київ — нет канала

## Окружение и деплой
- Env: /etc/robochi_bot.env (systemd) или .env в корне
- Перед manage.py: set -a; source .env; set +a
- После Python: sudo systemctl restart gunicorn
- После i18n: python manage.py compilemessages -l uk -l ru && sudo systemctl restart gunicorn
- Логи: sudo journalctl -u gunicorn -f
- & в .env — всегда кавычить

## История изменений

### 19.03.2026 — Локализация (i18n) — полная настройка
- Все hardcoded тексты заменены на gettext/_() и {% trans %}: telegram_markup_factory.py (5 строк, 3 были на русском), common.py (кнопка 'Подтвердить'), commands.py (приветствие + MenuButton), user_phone_number.py (приветствие + MenuButton), pre_call.html (текстовый блок)
- set_commands.py переписан: setup_bot_commands() регистрирует команды на uk/ru/default
- Починена кодировка в telegram/handlers/__init__.py и contact/__init__.py (Windows-1251 → UTF-8)
- locale/uk и locale/ru: заполнены все переводы, скомпилированы .mo
- Fuzzy-строки очищены: с 38/37 до 1/1 (только заголовок .po)
- Коммиты: 6bf8402, 38b4632, 11a72a2

### 18.03.2026 — Настройка входа из бота в Mini App + уведомления админов
- MenuButton «ПОЧАТИ» (setChatMenuButton type=web_app) вместо inline-кнопки «Відкрити кабінет»
- После сохранения контакта: delete_message первым (до DB-операций), затем «Вітаємо у нашому сервісі!», затем set_chat_menu_button
- Убрана проверка phone_number в authenticate_web_app (телефон сохраняется до открытия WebApp)
- Уведомление админов о новых пользователях: notify_admins_new_user() в telegram/utils.py
- ADMIN_TELEGRAM_IDS в .env и config/django/base.py (460011962, 1401489055)
- Глобальный MenuButton сброшен на default (type=commands), персональный устанавливается после контакта
- has_main_web_app отключён в BotFather

### 16.03.2026 — Рефакторинг архитектуры (коммит 9b8e1fc)
- Добавлен DRF + SimpleJWT + corsheaders + drf-spectacular + ecdsa + httpx
- Создано api/ app: JWT auth через Telegram initData, endpoints для user/vacancies/payments
- Создано payment/ app: MonobankPayment модель + сервисы
- Добавлена AuthIdentity модель в user/ + data migration из существующих пользователей
- Удалены telegram.Payment, telegram.PreCheckoutLog, telegram/handlers/invoice/
- Добавлен user/services.py

### 11.03.2026 — Стабилизация core flow
- Исправлена кодировка step_agreement.html (UnicodeDecodeError)
- Исправлен TEMPLATES dict (role→role.html)
- Исправлен work/views/__init__.py (typo)
- Исправлен UserWorkProfileCompleteObserver
- Wizard done() → redirect /
- get_or_create_user() обновлён

## На горизонте (приоритеты)
1. Admin data: каналы для Київ, invite_link для Дніпро, AgreementText
2. Legacy cleanup: удалить work_profile_detail, ContactForm, work_profile.html
3. Agreement fix: role из wizard data
4. Wizard: добавить шаг выбора пола (М/Ж) для Рабочего, шаг анкеты пользователя
5. ЛК Рабочего и Заказчика: новый дизайн по ТЗ (без анкеты, с кнопками Мої відгуки, Вакансії, Моя робота)
6. Бизнес-логика: форма заявки полная, переклички, ротация, автоматический/ручной поиск
7. Monobank: получить токен мерчанта, тестировать оплату
8. Мобильные клиенты: Android/iOS через /api/v1/
9. i18n: перевести msgid на английский (commands.py), убрать override('uk') в vacancy_formatter для личных сообщений

### Сессия 18.03.2026 (CSS)
1. Полная переработка CSS — единый стиль с robochi.work (neumorphism, стальной градиент).
2. Dark theme — добавлен @media (prefers-color-scheme: dark) с тёмными переменными.
3. Обнаружен и задокументирован дубль CSS — telegram/static/css/styles.css и static/css/styles.css.
4. Обновлены шаблоны: pre_call, vacancy_form, vacancy_feedback, call, call_confirm, refind_start.
5. Убраны glass-morphism карточки.
