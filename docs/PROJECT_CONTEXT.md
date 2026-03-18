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
- 6 пользователей, 11 AuthIdentity (6 telegram + 5 phone)
- Каналы: Харків ✓, Одеса ✓, Дніпро — нет invite_link, Київ — нет канала

## Окружение и деплой
- Env: /etc/robochi_bot.env (systemd) или .env в корне
- Перед manage.py: set -a; source .env; set +a
- После Python: sudo systemctl restart gunicorn
- Логи: sudo journalctl -u gunicorn -f
- & в .env — всегда кавычить

## История изменений
### 18.03.2026 — Настройка входа из бота в Mini App + уведомления админов
- MenuButton «ПОЧАТИ» (setChatMenuButton type=web_app) вместо inline-кнопки «Відкрити кабінет»
- После сохранения контакта: delete_message первым (до DB-операций), затем «Вітаємо у нашому сервісі!», затем set_chat_menu_button
- Убрана проверка phone_number в authenticate_web_app (телефон сохраняется до открытия WebApp)
- ask_phone текст: «Для продовження надішліть ваш номер телефону:»
- default_start: устанавливает MenuButton web_app вместо InlineKeyboardButton
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

### 9.3. Сессия 18.03.2026 (Claude)
1. **Полная переработка CSS** — единый стиль с robochi.work (neumorphism, стальной градиент).
2. **Dark theme** — добавлен `@media (prefers-color-scheme: dark)` с тёмными переменными.
3. **Обнаружен и задокументирован дубль CSS** — `telegram/static/css/styles.css` (приоритетный для WhiteNoise) и `static/css/styles.css`. Оба файла должны быть синхронизированы.
4. **Обновлены шаблоны**: `pre_call.html`, `vacancy_form.html`, `vacancy_feedback.html`, `call.html`, `call_confirm.html`, `refind_start.html` — убраны inline стили, добавлены единые CSS-классы.
5. **Убраны glass-morphism карточки** — контент отображается прямо на основном фоне без обрамлений.
