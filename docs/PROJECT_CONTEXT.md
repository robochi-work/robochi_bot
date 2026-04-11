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
- user/ — User (extends AbstractUser, PK=Telegram ID), UserFeedback (rating: like/dislike/none, is_auto: bool), AuthIdentity, user/services.py
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
- /vacancy/<pk>/feedback/<user_id>/ → форма відгуку (лайк/дизлайк + текст)
- /vacancy/<pk>/users/ → список учасників з модальним вікном
- /vacancy/<pk>/user/<user_id>/reviews/ → рейтинг + відгуки конкретного користувача
- /vacancy/<pk>/send-contact/ → POST, worker отримує телефон замовника в бот
- /work/employer/cities/ → страница каналов города (Загальна стрічка вакансій)

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
- AutoRatingObserver (`vacancy/services/observers/auto_rating.py`) — автоматические UserFeedback (is_auto=True):
  - Worker: +like за успешное завершение вакансии (AFTER_START_CALL_SUCCESS), +dislike за провал переклички
  - Employer: +like за оплату, +dislike за отмену/непоявление
- VacancyCreatedAdminObserver (`vacancy/services/observers/created_admin_observer.py`) — отправляет уведомления админам поштучно (не через broadcast), сохраняет message_id в vacancy.extra['admin_moderation_messages'] = {admin_chat_id: msg_id} для последующего удаления при approve/delete
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
- Каналы: Харків ✓, Одеса ✓, Дніпро ✓, Київ ✓, Буча ✓ — все с invite_link и bot_admin
- Группы: 11 групп в пуле, все available, active, с invite_link

## Окружение и деплой
- Env: /etc/robochi_bot.env (systemd) или .env в корне
- Перед manage.py: set -a; source .env; set +a
- После Python: sudo systemctl restart gunicorn
- После i18n: python manage.py compilemessages -l uk -l ru && sudo systemctl restart gunicorn
- Логи: sudo journalctl -u gunicorn -f
- & в .env — всегда кавычить

## История изменений

### 01.04.2026 (вечер) — Аудит 10 функциональных блоков + критический баг-фикс

**Полный аудит кода подтвердил реализацию всех заявленных функций:**
1. ✅ Відзиви/рейтинг — UserFeedback модель, лайк/дизлайк, модалка зі списком юзерів, ЛК Мій рейтинг
2. ✅ Заборона телефонів у групах — PHONE_PATTERNS (+380, 380, 0XX), delete + повідомлення юзеру
3. ✅ ЖЦВ — всі кнопки (ЗАКРИТИ, ПЕРЕКЛИЧКА if/elif, ЗУПИНИТИ/ПОНОВИТИ, ГРУПА), таймер 3г
4. ✅ Блокування — UserBlock, BlockService, chat_join_request перевірки, UI-банер у ЛК worker
5. ✅ ЛК Адміністратора — 7 views (dashboard, search_users, search_vacancies, vacancy_card, moderate, close, block)
6. ✅ Канали/групи в адмінці — ChannelProxy у city/admin, GroupAdmin у telegram/admin (редагувати можна, додавати — тільки ботом)
7. ✅ Мультиміста для Employer — multi_city_enabled + allowed_cities (M2M) в UserWorkProfile, employer_cities view, форма вакансії враховує allowed_cities
8. ✅ Ротація — resend_vacancies_to_channel_task, 5 хв, видаляє старе й перепублікує
9. ✅ Переклички (4 типи) — before_start, start_call, final, after_first + renewal_offer + worker_join_confirm
10. ✅ Групи вакансій — chat_join_request: is_staff → block → owner → already_in_vacancy → full → gender

**Критичний баг-фікс (коміт d49c40e):**
- `vacancy/tasks/call.py` — `_escalate_rollcall()` використовувала `bot.delete_message()` без імпорту `bot` → `NameError` при ескалації (6 нагадувань без відповіді заказчика)
- Фікс: додано `from telegram.handlers.bot_instance import bot` всередині `if msg_id:` блоку
- Регресійний тест: `tests/test_tasks.py::test_escalate_rollcall_bot_import` (коміт cd36123)

**Інші правки (коміт d49c40e):**
- `approved_group_observer.py` — `import logging` винесено на рівень модуля (ruff I001)
- `vacancy_close.py` — `VacancyDeleteEmployerInviteObserver` зареєстровано на VACANCY_CLOSE та VACANCY_DELETE
- `DJANGO_SECRET_KEY` у `.env` — замінено на production-safe (прибрано `django-insecure-` префікс)
- `ruff check .` → 0 errors

### 01.04.2026 — check_system: фикс констант + регрессионные тесты

1. **Баг**: `check_system.py` использовал `Group.STATUS_AVAILABLE` и `Vacancy.STATUS_APPROVED` как атрибуты классов моделей — они там не определены. Правильно: импортировать из `telegram/choices.py` и `vacancy/choices.py`.
2. **Фикс**: `_check_groups()` теперь `from telegram.choices import STATUS_AVAILABLE`, `_check_approved_vacancies()` — `from vacancy.choices import STATUS_APPROVED`.
3. **Регрессионные тесты**: `work/tests.py` — 5 тестов без `@pytest.mark.django_db`, с мокированием queryset через `unittest.mock.patch`. Запускаются на продакшн сервере без привилегий CREATEDB.
4. **Каналы**: исправлены 2 канала без `invite_link`/`has_bot_administrator` — добавлены вручную через Django Admin.
5. **check_system** теперь проходит все 7 проверок зелёным.

**Шаблон регрессионных тестов (для будущих багов):**
- Тест вызывает функцию с замоканным queryset
- Проверяет что не падает с AttributeError/ImportError
- Не требует создания тестовой БД
- Запускать: `python3 -m pytest work/tests.py -v`

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

### 24.03.2026 — Настройка БД каналов/групп, admin restructure
- **Webhook**: allowed_updates расширен — добавлены my_chat_member, chat_member, chat_join_request (без них бот не получал события добавления в каналы/группы)
- **load_handlers_once()**: добавлены все недостающие импорты хэндлеров (member.bot.channel/group, member.user.group, callbacks, messages.group). Было 0 my_chat_member хэндлеров, стало 2
- **Автоматическое создание каналов/групп** восстановлено: при добавлении бота в канал/группу в Telegram запись создаётся в БД автоматически через my_chat_member хэндлер
- **Канал Києва** — создан и привязан к городу
- **Канал Дніпро** — invite_link добавлен
- **Канал Буча** — создан (тестовый)
- **Admin restructure**: раздел Канали перенесён из ТЕЛЕГРАМ в МІСТО (через proxy model ChannelProxy). Кнопки "Додати Канал/Групу" убраны (создаются только ботом). Город можно создать из формы канала через "+" у поля Місто
- **City.__str__**: добавлен safe fallback для отсутствующих переводов (parler DoesNotExist)
- Коммиты в develop

### Сессия 24.03.2026 (вечер) — ЛК Рабочего (Worker dashboard)
1. **Разделение dashboard по ролям** — index view теперь маршрутизирует: Worker → worker_dashboard.html, Employer → index.html (block_registry), Admin → admin_dashboard.html
2. **worker_dashboard.html** — 5 кнопок в neumorphic стиле:
   - Мої вакансії → ссылка на канал города (Channel по city)
   - Моя робота → ссылка на группу текущей вакансии (VacancyUser status=MEMBER + Vacancy status in approved/active). Если нет активной вакансии → модальное окно «Спочатку оберіть вакансію» с кнопкой «Зрозуміло»
   - Мої відгуки → /work/reviews/ (UserFeedback.filter(user=user) + vacancy info из extra.vacancy_id)
   - Що робити якщо? → /work/faq/ (статические FAQ с <details>)
   - Допомога адміністратора → https://t.me/robochi_work_admin
3. **worker_reviews.html** — страница просмотра отзывов с адресом вакансии из extra.vacancy_id
4. **worker_faq.html** — FAQ страница (6 вопросов, accordion на <details>/<summary>)
5. **Новые файлы**: work/views/worker.py, work/templates/work/worker_dashboard.html, worker_reviews.html, worker_faq.html
6. **Обновлены**: work/views/index.py (маршрутизация по role), work/urls.py (+ worker_reviews, worker_faq)

## Система блокировок (UserBlock)

### Модель и сервис
- **UserBlock** (user/models.py): поля block_type (permanent/temporary), reason (manual/rollcall_reject/employer_uncheck/unpaid/other), blocked_by (FK nullable), blocked_until, comment, is_active, created_at
- **BlockService** (user/services.py): is_blocked, is_permanently_blocked, is_temporarily_blocked, get_active_block, block_user, unblock_user, auto_block_rollcall_reject, auto_block_employer_unpaid
- Постоянный блок: user.is_active=False, кик из всех групп и каналов (ban+unban, без ЧС)
- Временный блок: запрет входа в группу вакансии через auto_approve, запрет создания вакансий. Кнопка «Мої вакансії» остаётся активной — рабочий видит канал.

### Типы блокировок
1. **Permanent manual** — админ блокирует вручную через ЛК. Модальное окно с выбором типа (Тимчасове/Постійне). Кик из всех групп+каналов. /start отклоняется.
2. **Temporary manual** — админ блокирует вручную. Запрет создания вакансий (employer), участия в вакансиях (worker).
3. **Temporary rollcall_reject** — авто, рабочий проигнорировал перекличку за 2ч до старта (VacancyBeforeCallObserver, 20 мин таймаут). Кик + блок + сообщение.
4. **Temporary employer_uncheck** — заказчик снял галочку на перекличке «Начало работы» (VacancyStartCallFailObserver). Кик из группы + блок, blocked_by=vacancy.owner.
5. **Temporary employer_uncheck** — заказчик снял галочку на перекличке «Окончание работы» (VacancyAfterStartCallFailObserver). Кик + блок + уведомление админу.
6. **Temporary unpaid** — авто, после переклички окончания формируется счёт, заказчик блокируется до оплаты. Авто-разблокировка через Monobank webhook.

### Дополнительные проверки в auto_approve (chat_join_request)
- Незарегистрированный пользователь (нет work_profile/role) → decline + ссылка на /start
- Заказчик в чужую группу вакансии → decline + сообщение
- Порядок: is_staff → permanent → temporary → is_active → not_registered → vacancy lookup → owner → employer_not_owner → already_in_vacancy → capacity → gender → approve

### Кнопка «Повернути до групи»
- Админ может вернуть кикнутого рабочего: view vacancy_reinvite_worker → снять блокировку + отправить invite в бот
- Страница «Додавання/Видалення працівників» (бывшая «Група з працівниками»)

### Оплата и блокировка unpaid
- После 2-й переклички VacancyAfterStartCallSuccessObserver → send_vacancy_invoice → сообщение в бот с WebApp-кнопкой оплаты + auto_block_employer_unpaid
- Monobank webhook (process_webhook) при SUCCESS → is_paid=True, unblock unpaid, удаление сообщения из бота
- Telegram Payments больше не используется — только Monobank эквайринг

### Защита админов в Django admin
- Суперюзер: полный доступ
- Обычный staff: не видит других staff, не может менять is_staff/is_superuser/is_active, не может удалять staff-пользователей
- Кнопка ЗАБЛОКУВАТИ скрыта для is_staff в admin_search_results

## Реалізовано та підтверджено в роботі

- **Жизненный цикл вакансии (ЖЦВ):** полная реализация по ТЗ
  - Новые статусы: STATUS_SEARCH_STOPPED, STATUS_AWAITING_PAYMENT
  - Новые поля: closed_at, search_stopped_at, first_rollcall_passed, second_rollcall_passed
  - Керування вакансією: единая страница с переключающимися кнопками (ЗУПИНИТИ/ПОНОВИТИ ПОШУК, ПЕРЕКЛИЧКА ПОЧАТОК/КІНЕЦЬ)
  - ЗАКРИТИ ВАКАНСІЮ: 3ч таймер → обнуление группы (close_lifecycle_timer_task)
  - Подтверждение рабочего: 5 мин таймер + напоминания + запрос телефона (worker_join_confirm)
  - Автоостановка поиска при начале рабочего времени
  - Переклички заказчика: напоминания каждые 5 мин × 6 → эскалация админу
  - Оплата: vacancy_payment view → create_invoice → Monobank redirect → webhook → is_paid
  - Продление на завтра: опрос заказчика → форма (дата=завтра) → модерация → опрос рабочих → сравнение количества
  - Все уведомления на украинском языке (call_formatter.py — централизованные тексты)
  - Celery tasks: close_lifecycle_timer_task, worker_join_confirm_check_task, renewal_offer_task, renewal_worker_check_task
- **Invite links management:** Bot NEVER creates invite links — all links managed manually via Django admin. `GroupService.update_invite_link` and `ChannelService.update_invite_link` are no-ops. `group_handle_bot_added` and `channel_handle_bot_added` only set `has_bot_administrator`, do not touch `invite_link`. Employer receives existing `group.invite_link` from DB (not a new one-time link). `employer_invite_msg_id` saved in `vacancy.extra` — message deleted on vacancy close/delete (`VacancyDeleteEmployerInviteObserver`) and on owner kick (`_escalate_rollcall`). Bot must NOT have `can_invite_users` right in groups (removed manually in Telegram group settings) to prevent Telegram from auto-creating admin links.

## Key learnings & principles

- **Invite links:** Bot must never call `create_chat_invite_link` or `export_chat_invite_link`. Links are set manually in Django admin. If bot has `can_invite_users` right, Telegram auto-creates primary links for it — this right must be disabled manually in group settings. `revoke_chat_invite_link` deactivates a link but Telegram creates a replacement — the only way to have zero bot links is to remove `can_invite_users`.
- **Group cleanup (ЖЦВ):** `kick_all_users` relies on `UserInGroup` records in DB. If users joined outside normal flow (test users), they won't be in DB and won't be kicked. Telegram Bot API cannot delete messages older than 48 hours (except bot's own messages). For full group reset, delete messages within 48h window during normal ЖЦВ closure.
- **Bot cannot promote/demote itself** — `promote_chat_member` with bot's own ID returns "can't promote self". Admin rights changes for the bot must be done manually by group owner.
- **chat_member / chat_join_request events can arrive with chat.type="channel"** (linked discussion groups). Handlers `auto_approve` and `handle_user_status_change` in `telegram/handlers/member/user/group.py` MUST check `chat.type == "supergroup"` before any access to the Group model, otherwise channel IDs leak into the Group table. Fix: 09.04.2026.

## На горизонте (приоритеты)
1. AgreementText для employer/worker в admin
2. ЛК администратора — наполнить функционалом
3. ЛК Employer — Фаза 2: управление заявками из ЛК — **DONE** (ЖЦВ)
4. ЛК Worker — доработка: блокировка UI при блокировке, запрос телефона после подтверждения вакансії
5. Ротация вакансий — **DONE**
6. Monobank інтеграція — **DONE** (ЖЦВ: vacancy_payment + webhook)
7. Переклички рабочих — **DONE** (ЖЦВ)
8. Переклички заказчика — **DONE** (ЖЦВ)
9. Повторный поиск / продление на завтра — **DONE** (ЖЦВ)
10. Уведомления по ТЗ — **DONE** (call_formatter.py)

### Сессия 18.03.2026 (CSS)
1. Полная переработка CSS — единый стиль с robochi.work (neumorphism, стальной градиент).
2. Dark theme — добавлен @media (prefers-color-scheme: dark) с тёмными переменными.
3. Обнаружен и задокументирован дубль CSS — telegram/static/css/styles.css и static/css/styles.css.
4. Обновлены шаблоны: pre_call, vacancy_form, vacancy_feedback, call, call_confirm, refind_start.
5. Убраны glass-morphism карточки.

### Сессия 20.03.2026 (Frontend pages + bot flow)
1. **Страница role** — big-btn стиль как robochi.work, auto-submit по клику, ссылка "Договір оферти" внизу
2. **Страница city** — прокрутка списка, фиксированная кнопка ПРОДОВЖИТИ внизу, заголовок "Оберіть Ваше місто", ссылка на админа в конце списка
3. **Страница agreement** — прокрутка текста, фиксированная кнопка ЗГОДЕН внизу, заголовок "Правила користування сервісом:"
4. **Страница legal_offer** — новая: /work/legal/offer/, отображает AgreementText type=offer из админки
5. **Страница phone_required** — новая: /work/phone-required/, показывается при открытии WebApp без подтверждённого телефона, кнопка "Повернутися в бот" + resend phone request
6. **AgreementText модель** — добавлен тип `offer` (Договір оферти та Політика конфіденційності), admin с list_editable
7. **Bot flow** — ask_phone сбрасывает MenuButton, проверка phone_number в questionnaire_redirect и index view
8. **i18n** — добавлены переводы для role, city, agreement, legal, phone_required страниц
9. **Новые файлы**: work/views/legal.py, work/views/phone_required.py, work/templates/work/legal_offer.html, work/templates/work/phone_required.html
10. **Миграция** — AgreementText.role choices расширен (employer, worker, offer)

### Сессия 24.03.2026 — Реорганізація бази даних користувачів та адмін-панелі
**5 этапов выполнено:**

1. **Объединение админки пользователей** — 3 раздела (Користувачі, Робочі профілі, Відгуки) слиты в один UserAdmin:
   - list_display: ID, Telegram, Full name, Phone, Role, City, Gender, is_staff, is_active
   - Фильтры: RoleFilter, CityFilter, Gender, is_staff, is_active
   - Inlines: UserWorkProfileInline, AuthIdentityInline, UserFeedbackReceivedInline
   - Удалены: UserWorkProfileInUserAdmin, UserFeedbackAdmin, proxy UserWorkProfileInUser, дублирующий UserWorkProfileAdmin из work/admin.py

2. **Шаг выбора пола в wizard для Worker** — форма GenderForm, шаблон step_gender.html:
   - Wizard: role → gender (только для Worker, condition_dict) → city → agreement
   - Дизайн: копия role.html, без политики конфиденциальности, текст "Оберіть Вашу стать:", кнопки "Я ЧОЛОВІК" / "Я ЖІНКА"
   - Gender сохраняется в User.gender только для Worker; для Employer пол не запрашивается

3. **Роль Administrator** — добавлена в WorkProfileRole choices + миграция:
   - is_staff=True автоматически синхронизирует role=administrator (через UserAdmin.save_model)
   - При снятии is_staff → role=None, is_completed=False (пользователь проходит wizard заново)
   - index view: is_staff=True → admin_dashboard.html (заглушка, функционал позже)
   - authenticate_web_app: is_staff=True → пропуск wizard, redirect на /
   - Administrator НЕ совмещается с Worker/Employer — отдельная роль

4. **Блокировка по полу при "Я ГОТОВИЙ ПРАЦЮВАТИ"** — обновлён chat_join_request handler:
   - Последовательные проверки: is_staff → is_active → owner → участие в другой вакансии → лимит людей → пол
   - Каждый отказ: decline_chat_join_request + сообщение Worker в бот с причиной
   - Проверка пола: vacancy.gender != GENDER_ANY and vacancy.gender != user.gender → "Ця вакансія призначена для іншої статі"
   - Проверка участия: VacancyUser.filter(status=MEMBER, vacancy__status__in=[APPROVED,ACTIVE]).exclude(vacancy) → "Ви вже берете участь в іншій вакансії"

5. **Удаление legacy-кода:**
   - Удалены: ContactForm, CitySelectForm, work_profile_detail(), work_profile.html, URL profile/
   - Удалено поле birth_year из User + миграция remove_birth_year
   - Удалён неиспользуемый импорт UserWorkProfile из user/models.py

**Текущее состояние БД:**
- 5 городов: Київ(1), Одеса(2), Дніпро(3), Харків(4), Буча(9)
- 6 пользователей, роли: Employer, Worker, Administrator
- Wizard flow: role → gender (Worker only) → city → agreement → /

**Файлы изменены/созданы:**
- user/admin.py — полностью переписан (единый UserAdmin с inlines и фильтрами)
- user/models.py — удалены birth_year, proxy UserWorkProfileInUser, unused import
- user/forms.py — убрано поле email
- work/forms.py — удалены ContactForm, CitySelectForm; добавлена GenderForm
- work/views/work_profile.py — удалён work_profile_detail; добавлен шаг gender в wizard с condition_dict
- work/views/index.py — маршрутизация по is_staff для ЛК админа
- work/admin.py — убран дублирующий UserWorkProfileAdmin
- work/choices.py — добавлен ADMINISTRATOR в WorkProfileRole
- work/urls.py — убран URL profile/
- work/templates/work/work_profile/step_gender.html — новый шаблон выбора пола
- work/templates/work/work_profile/work_profile.html — удалён
- work/templates/work/admin_dashboard.html — заглушка ЛК администратора
- telegram/handlers/member/user/group.py — расширенные проверки в chat_join_request
- telegram/views.py — пропуск wizard для is_staff

**Приоритеты (после сессии 24.03.2026):**
1. AgreementText для employer/worker в admin
2. ЛК администратора — наполнить функционалом (модерация, пользователи, каналы, оплаты)
3. ЛК Employer — дизайн и кнопки по ТЗ (Мої відгуки, Мої міста, Створити вакансію, Поточні заявки)
4. ЛК Worker — дизайн и кнопки по ТЗ (Мої відгуки, Мої вакансії, Моя робота)
5. Ротация вакансий
6. Monobank интеграция

### Сессия 24.03.2026 (вечер, часть 2) — ЛК Заказчика (Employer dashboard)
1. **employer_dashboard.html** — новый шаблон ЛК Заказчика, 6 кнопок в neumorphic стиле (аналогично Worker):
   - Створити вакансію → /vacancy/create/ (с border-left accent)
   - Поточні заявки → /vacancy/my/ (показывает count активных)
   - Мої відгуки → /work/employer/reviews/
   - Мої міста → ссылка на канал города (Channel по city)
   - Що робити якщо? → /work/employer/faq/
   - Допомога адміністратора → https://t.me/robochi_work_admin

2. **vacancy_my_list.html** — страница «Поточні заявки»:
   - Карточки вакансий: адрес, дата, время, люди (N/M), статус-бейдж
   - Статусы: Очікує модерації (pending/yellow), Активна (approved/green), Йде зміна (active/blue)
   - Клик → детальная страница вакансии

3. **vacancy_detail.html** — детальная страница вакансии:
   - Полная информация: адрес, дата, час, люди, оплата, спосіб, стать, паспорт, опис роботи
   - Кнопка «Група з робітниками» → invite_link группы
   - Кнопка «Управління вакансією» → модальное окно с: Повторний пошук, Перекличка Початок/Кінець роботи
   - Список робітників (VacancyUser members)
   - **Скрытие кнопок по статусу (09.04.2026):** для pending и closed статусов ВСЕ кнопки действий скрыты (is_pending, is_closed_lifecycle из view); отображается только карточка и статус-бейдж

4. **Маршрутизация Employer в index.py**:
   - Первый вход (нет ни одной вакансии) → redirect на /vacancy/create/ (без кнопки «Назад»)
   - Повторный вход → employer_dashboard.html
   - Контекст: channel, active_vacancies_count, reviews_count

5. **vacancy_create view** — добавлен флаг is_first_visit (Vacancy.objects.filter(owner).exists()), передаётся в шаблон для скрытия кнопки «Назад»

6. **vacancy_form_page.html** — убран header с меню, добавлена кнопка «← Назад» (скрыта при первом входе через is_first_visit)

7. **employer_reviews.html** — страница просмотра отзывов (аналог worker_reviews)

8. **employer_faq.html** — FAQ страница для заказчиков (5 вопросов: создание заявки, модерация, переклички, неявка рабочего, связь с админом)

9. **CSS вынесен в глобальный styles.css** (telegram/static/css/styles.css):
   - worker-btn, worker-btn__icon/text/title/sub, worker-btn--accent
   - modal-overlay, modal-card, modal-text, modal-title
   - page--worker-dashboard, page--employer-dashboard
   - Убраны дублирующие <style> из worker_dashboard.html и employer_dashboard.html

10. **Block registry** — больше не используется для Employer (заменён на прямой рендер employer_dashboard.html). Блоки VacancyCreateFormBlock, ActiveVacanciesPreviewBlock, ChannelPreviewBlock остаются как fallback

**Новые файлы:**
- work/views/employer.py (employer_reviews, employer_faq)
- work/templates/work/employer_dashboard.html
- work/templates/work/employer_reviews.html
- work/templates/work/employer_faq.html
- vacancy/templates/vacancy/vacancy_my_list.html
- vacancy/templates/vacancy/vacancy_detail.html

**Обновлённые файлы:**
- work/views/index.py — маршрутизация Employer
- work/urls.py — +employer_reviews, employer_faq
- vacancy/views.py — +vacancy_my_list, vacancy_detail, is_first_visit в vacancy_create
- vacancy/urls.py — +my/, <pk>/detail/
- vacancy/templates/vacancy/vacancy_form_page.html — убран header, кнопка Назад
- telegram/static/css/styles.css — глобальные стили кнопок и модалок
- work/templates/work/worker_dashboard.html — убраны дублирующие <style>

**Важно:** CSS живёт в telegram/static/css/styles.css (не в static/css/). STATICFILES_DIRS пуст, collectstatic берёт из app static/ папок. После изменений CSS: rm -rf staticfiles && collectstatic --noinput && restart gunicorn.

**Приоритеты (обновлены):**
1. AgreementText для employer/worker в admin
2. ЛК администратора — наполнить функционалом
3. ЛК Employer — Фаза 2: управление заявками (зупинити пошук, повторний пошук из ЛК, страница учасників, оплата)
4. ЛК Worker — доработка: блокировка UI, запрос телефона
5. Ротация вакансий
6. Monobank интеграция

### Сессия 25.03.2026 (вечер) — ЛК Адміністратора (Admin dashboard)
1. **Полноценный ЛК Администратора** — work/views/admin_panel.py, 6 views:
   - `admin_dashboard` — главная страница: кнопка «Відкрити Django Admin» + два таба (Користувачі / Вакансії) с фильтрами и поиском
   - `admin_search_users` — поиск пользователей: карточки с Ім'я, ID (ссылка → Django admin), Username (ссылка → Telegram), Телефон, кнопка блокировки
   - `admin_search_vacancies` — карта вакансий: Employer с вакансиями по городам, кнопка ГРУПА (invite_link), кнопка МОДЕРАЦІЯ для pending
   - `admin_vacancy_card` — карточка вакансий пользователя (по user_id)
   - `admin_block_user` — блокировка/разблокировка пользователя (POST, toggle is_active)
   - `admin_moderate_vacancy` — форма модерации вакансии: данные вакансии + кнопка ЗАТВЕРДИТИ → status=approved + вызов Observer'ов (notify channels/group)

2. **Кнопка в боте** — `service/telegram_markup_factory.py`: `admin_vacancy_reply_markup` теперь ведёт на `work:admin_moderate_vacancy` (ЛК), а не на Django admin `/admin/vacancy/vacancy/<id>/change/`. Кнопка переименована: «🔍 Посмотреть вакансию» → «Переглянути вакансію».

3. **Employer dashboard** — подключён `employer_dashboard.html` через прямой рендер; redirect на `vacancy:create` при первом входе (нет вакансий).

4. **index.py обновлён** — маршрутизация: admin → `admin_dashboard`, employer без вакансий → `vacancy:create`, employer с вакансиями → `employer_dashboard.html`.

5. **work/urls.py расширен** — новые маршруты:
   - `admin-panel/` → `admin_dashboard`
   - `admin-panel/users/` → `admin_search_users`
   - `admin-panel/vacancies/` → `admin_search_vacancies`
   - `admin-panel/user/<int:user_id>/vacancies/` → `admin_vacancy_card`
   - `admin-panel/user/<int:user_id>/block/` → `admin_block_user`
   - `admin-panel/vacancy/<int:vacancy_id>/moderate/` → `admin_moderate_vacancy`
   - `employer/reviews/` → `employer_reviews`
   - `employer/faq/` → `employer_faq`
   - `employer/cities/` → `employer_cities`

**Новые/обновлённые файлы:**
- work/views/admin_panel.py — все admin views
- work/templates/work/admin_dashboard.html — dashboard с табами
- work/templates/work/admin_moderate_vacancy.html — форма модерации
- work/urls.py — расширен
- work/views/index.py — обновлена маршрутизация
- service/telegram_markup_factory.py — кнопка ведёт в ЛК

**Приоритеты (обновлены 25.03.2026):**
1. AgreementText для employer/worker в admin
2. ЛК Employer — Фаза 2: управление заявками (зупинити пошук, повторний пошук из ЛК, страница учасників, оплата)
3. ЛК Worker — доработка: блокировка UI, запрос телефона
4. Ротация вакансий
5. Monobank інтеграція

### Сессия 28.03.2026 — ЛК Заказчика (Фаза 2) + баг-фиксы + правки

**Фаза 2 — Управление заявками из ЛК:**
1. `vacancy_stop_search` view — зупинити пошук з ЛК (заменяет кнопку в канале на «Пошук завершено»)
2. `vacancy_members` view — страница учасників групи: ім'я, телефон, статус, кількість відгуків
3. `vacancy_kick_member` view — видалення робітника з групи через ЛК (POST + confirm)
4. Модалка «Управління вакансією» на vacancy_detail оновлена: Повторний пошук, Зупинити пошук (approved), Переклички Початок/Кінець (approved/active), Учасники групи
5. URL: vacancy/my/, vacancy/<pk>/detail/, vacancy/<pk>/stop-search/, vacancy/<pk>/members/, vacancy/<pk>/kick/<user_id>/

**Критичний баг-фікс:**
6. `admin_moderate_vacancy` не назначала группу з пулу при approve → кнопка «Я ГОТОВИЙ ПРАЦЮВАТИ» не з'являлась в каналі. Додано `GroupService.get_available_group()` + STATUS_PROCESS перед approve
7. Кнопка в каналі перейменована: «Відгукнутися на вакансію» → «Я ГОТОВИЙ ПРАЦЮВАТИ» (locale/uk)

**Правки тексту вакансії в каналі:**
8. Динамічна дата: vacancy_formatter тепер порівнює vacancy.date з date.today() → показує «Сьогодні» або «Завтра» динамічно (замість збереженого date_choice)
9. Динамічна кількість: for_channel(show_needed=True) показує скільки ще потрібно робітників (needed / total), а не загальну кількість
10. Локалізація: Sex→Стать (msgid "Gender"), Work time→Час роботи (msgid "Working hours"), Payment→Оплата, Need passport→Потрібен паспорт — розкоментовані та додані переводи в django.po

**Автодобавлення Employer в групу:**
11. `VacancyApprovedGroupObserver._add_employer_to_group()` — після модерації створює одноразове invite-посилання (member_limit=1, creates_join_request=False) та відправляє Employer кнопку «Перейти в групу вакансії» в бот

**Інші правки:**
12. `contact_phone` — додано в initial та save в admin_moderate_vacancy
13. `input[type="tel"]` — додано в CSS форми модерації (admin_moderate_vacancy.html)
14. `vacancy_feedback.html` — додано {% block header %}{% endblock %} (прибрано старий header з Меню)

**Нові файли:**
- vacancy/templates/vacancy/vacancy_members.html

**Оновлені файли:**
- vacancy/views.py — +vacancy_stop_search, vacancy_members, vacancy_kick_member
- vacancy/urls.py — +stop-search/, members/, kick/
- vacancy/services/vacancy_formatter.py — повністю переписаний (динамічна дата, кількість, нові msgid)
- vacancy/services/observers/approved_group_observer.py — +_add_employer_to_group()
- vacancy/templates/vacancy/vacancy_detail.html — оновлена модалка управління
- vacancy/templates/vacancy/vacancy_feedback.html — прибрано header
- work/views/admin_panel.py — +GroupService при approve, +contact_phone
- work/templates/work/admin_moderate_vacancy.html — +input[type="tel"] CSS
- locale/uk/LC_MESSAGES/django.po — нові та розкоментовані переводи

**Пріоритети (оновлені):**
1. Пункт 3 — Кольорові кнопки: Bot API додав style для InlineKeyboardButton — перевірити підтримку pyTelegramBotAPI
2. Пункт 5 — Віджет часу: заміна на custom select
3. Пункт 7 — Мультимісто для Employer (M2M, admin UI, форма)
4. Фаза 3 — Оплата monobank UI в ЛК
5. Блокування — модель (тип, термін, причина), автоблокування
6. Продовження на завтра — розсилка, очікування, перестворення

### Сессия 28.03.2026 (вечер) — Допрацювання ЛК Employer + аудит шаблонів

**4 задачі виконано:**

1. **Аудит header** — у 7 шаблонах, що наслідують base.html, додано порожній {% block header %}{% endblock %} для приховання старого header з кнопкою «Меню»:
   - vacancy/: call.html, call_confirm.html, pre_call.html, refind_start.html, vacancy_feedback.html
   - work/: index.html
   - telegram/: check.html

2. **Права Employer в групі вакансії** — в auto_approve() (chat_join_request handler) додано автоматичний промоут Employer до адміністратора групи при join:
   - bot.approve → time.sleep(1) → GroupService.set_default_owner_permissions() → set_admin_custom_title('Роботодавець')
   - Раніше промоут був тільки в chat_member_handler, який міг не спрацювати при join через chat_join_request
   - import time перенесено в блок імпортів файлу

3. **Аудит форми модерації** — admin_moderate_vacancy:
   - Додано захист POST від повторної модерації: якщо vacancy.status вже APPROVED або ACTIVE → redirect на admin_vacancy_card
   - Шаблон: кнопка submit замінюється на повідомлення «Вакансія вже пройшла модерацію» + всі поля disabled через JS
   - Перевірено: contact_phone, map_link, date з date_choice — все коректно

4. **Віджет вибору часу** — замінено нативний input type=time на custom select:
   - TimeSelectWidget(forms.MultiWidget) — два select: години (00-23) та хвилини (00/15/30/45)
   - TimeSelectField(forms.MultiValueField) — compress() збирає datetime.time
   - Шаблон: vacancy/templates/vacancy/widgets/time_select.html
   - CSS: .time-select-widget в telegram/static/css/styles.css
   - VacancyAdminForm не зачіпалась
   - Виправлено: format_output замінено на template_name (Django 5.x сумісність)

**Нові файли:**
- vacancy/templates/vacancy/widgets/time_select.html

**Оновлені файли:**
- vacancy/forms.py — +TimeSelectWidget, +TimeSelectField, start_time/end_time замінені
- telegram/handlers/member/user/group.py — промоут owner в auto_approve(), +import time
- work/views/admin_panel.py — +is_already_moderated, захист POST
- work/templates/work/admin_moderate_vacancy.html — disabled form + повідомлення
- telegram/static/css/styles.css — +.time-select-widget стилі
- 7 шаблонів — додано {% block header %}{% endblock %}

### Сессия 28.03.2026 (ніч, частина 3) — Баг-фікси та доопрацювання

**Виконано:**

1. **Права Employer в групі — фікс promote 400** — set_default_owner_permissions оновлено:
   - can_promote_members=False (було True → HTTP 400 'not enough rights')
   - can_restrict_members=True, can_delete_messages=True, can_pin_messages=True (нові права для Employer)
   - bare except замінено на except Exception as e з logging.warning
   - **Важливо:** бот повинен мати право 'Додавати нових адміністраторів' (can_promote_members) у кожній групі пулу — налаштовується вручну в Telegram

2. **Фільтр admin_vacancy_card** — додано status__in=[STATUS_PENDING, STATUS_APPROVED, STATUS_ACTIVE]:
   - Раніше показувались ВСІ вакансії (включаючи closed/deleted)
   - Тепер адміністратор бачить тільки актуальні вакансії (як заказчик)

3. **Auto-pin вакансії в групі** — approved_group_observer.py:
   - Замість self.notifier.notify() використовується bot.send_message() напряму
   - Після відправки — bot.pin_chat_message(disable_notification=True)
   - Повідомлення з текстом вакансії автоматично закріплюється в групі

4. **Адмін: примусове закриття вакансії** — admin_close_vacancy view:
   - POST endpoint для закриття вакансії з ЛК адміністратора
   - Якщо вакансія не closed → VACANCY_CLOSE event (повний lifecycle)
   - Якщо вже closed але група stuck → звільнення групи (status=available)
   - Кнопка ЗАКРИТИ на admin_vacancy_card для approved/active вакансій
   - URL: /work/admin-panel/vacancy/<id>/close/

5. **Звільнення stuck груп** — 10 груп зі статусом process без активної вакансії звільнено вручну через shell. Причина: close_vacancy_task не звільняє групи для неоплачених вакансій (by design per ТЗ)

6. **Кольорові кнопки в групі** — style параметр для InlineKeyboardButton:
   - style='danger' залишено (pinned bar показує синім, тіло повідомлення — outline)
   - Обмеження платформи: Telegram ігнорує style для url-кнопок в групах
   - В каналах style='danger' працює коректно (червона кнопка «Я ГОТОВИЙ ПРАЦЮВАТИ»)

**Відомі обмеження платформи (задокументовано):**
- Pinned bar в Telegram завжди рендерить inline-кнопки синім кольором незалежно від style
- url-кнопки в групах завжди відображаються в outline-стилі (прозорі)
- style працює тільки для кнопок в каналах

**Оновлені файли:**
- telegram/service/group.py — set_default_owner_permissions з правильними правами
- work/views/admin_panel.py — +admin_close_vacancy, фільтр admin_vacancy_card
- work/urls.py — +admin-panel/vacancy/<id>/close/
- work/templates/work/admin_vacancy_card.html — кнопка ЗАКРИТИ + CSS btn-danger
- vacancy/services/observers/approved_group_observer.py — bot.send_message + pin_chat_message
- service/telegram_markup_factory.py — style='danger' для group feedback кнопок

### Сессия 28.03.2026 (ніч, частина 2) — Мультимісто для Employer

**Реалізовано повну підтримку розміщення вакансій в різних містах:**

1. **Модель** — `UserWorkProfile` розширено:
   - `multi_city_enabled` (BooleanField) — прапорець активації мультимісто
   - `allowed_cities` (M2M → City) — дозволені міста для розміщення вакансій
   - Міграція: work/migrations/0005_add_multi_city_fields.py

2. **Адмін-панель** — `UserWorkProfileInline` в UserAdmin:
   - Додано поля `multi_city_enabled` та `allowed_cities` (filter_horizontal)
   - Адміністратор вмикає функцію та обирає міста для конкретного Employer

3. **Форма створення вакансії** — `VacancyForm`:
   - Додано поле `city` (ModelChoiceField)
   - При мультимісті: `<select>` зі списком дозволених міст (allowed_cities + основне місто)
   - Без мультимісто: HiddenInput з містом із профілю
   - `save()` використовує обране місто для визначення каналу: `Channel.objects.get(city=selected_city)`
   - Конструктор приймає `work_profile` kwarg

4. **Шаблон форми** — `vacancy_form.html`:
   - Вгорі під заголовком: поточне місто (текст) або випадаючий список міст

5. **Дашборд Employer** — `employer_dashboard.html` + `index.py`:
   - Кнопка «Мої міста» при мультимісті → окрема сторінка зі списком міст
   - При одному місті → пряме посилання на канал

6. **Сторінка «Мої міста»** — нова:
   - View: `employer_cities` в work/views/employer.py
   - Шаблон: work/templates/work/employer_cities.html
   - URL: /work/employer/cities/ (work:employer_cities)
   - Список міст з посиланнями на канали, основне місто позначено "(основне)"

7. **Картки вакансій** — `vacancy_my_list.html`:
   - Кожна картка підписана: місто + адреса (channel.city · address)

8. **Модерація** — `admin_moderate_vacancy`:
   - Форма отримує `work_profile` власника вакансії (не адміністратора)
   - GET: `initial['city']` = vacancy.channel.city_id → правильне місто в формі
   - POST: `vacancy.channel` оновлюється з обраного міста

9. **Критичний фікс — публікація в правильний канал**:
   - `approved_channel_observer.py` — замінено `Channel.objects.filter(city=vacancy.owner.work_profile.city)` → `vacancy.channel`
   - `refind_observer.py` — аналогічно
   - `vacancy/tasks/resend.py` (ротація) — аналогічно
   - `vacancy/admin.py` (Django Admin save_model) — `Channel.objects.get(city=work_profile.city)` → використовує існуючий `vacancy.channel` якщо він вже встановлений

**Нові файли:**
- work/migrations/0005_add_multi_city_fields.py
- work/templates/work/employer_cities.html

**Оновлені файли:**
- work/models.py — +multi_city_enabled, +allowed_cities
- user/admin.py — UserWorkProfileInline +multi_city_enabled, +allowed_cities, +filter_horizontal
- vacancy/forms.py — +city field, +City import, +work_profile kwarg, save() uses selected city
- vacancy/views.py — vacancy_create передає work_profile в VacancyForm
- vacancy/templates/vacancy/vacancy_form.html — city selector вгорі
- vacancy/templates/vacancy/vacancy_my_list.html — місто в картках
- work/views/index.py — city_channels контекст для мультимісто
- work/views/employer.py — +employer_cities view
- work/views/admin_panel.py — work_profile owner для модерації, city в initial, channel update
- work/templates/work/employer_dashboard.html — мультимісто кнопка
- work/urls.py — +employer/cities/
- vacancy/services/observers/approved_channel_observer.py — vacancy.channel замість work_profile.city
- vacancy/services/observers/refind_observer.py — vacancy.channel замість work_profile.city
- vacancy/tasks/resend.py — vacancy.channel замість work_profile.city
- vacancy/admin.py — умовне присвоєння channel
- telegram/static/css/styles.css — +city-selector, +city-current стилі

**Як активувати мультимісто для Employer:**
1. Django Admin → Users → знайти Employer
2. Work profile → ✅ Multi-city enabled
3. Allowed cities → обрати додаткові міста
4. Зберегти

**Пріоритети (оновлені 29.03.2026):**
1. ЛК Worker — доработка: блокировка UI, запрос телефона після підтвердження вакансії
2. Ротація вакансій (Celery task кожні 5 хв)
3. Monobank оплата — UI в ЛК
4. Продовження на завтра — розсилка, очікування, перестворення

### Сессия 28.03.2026 (ночь) — Кольорові кнопки + баг-фікси + локалізація

**Виконано:**

1. **pyTelegramBotAPI оновлено 4.27 → 4.32** — підтримка нового параметра `style` для `InlineKeyboardButton`

2. **Кольорові inline-кнопки** — `style='danger'` (червоний) додано до 3 кнопок в `service/telegram_markup_factory.py`:
   - «Я ГОТОВИЙ ПРАЦЮВАТИ» (`channel_vacancy_reply_markup`)
   - «НАДІСЛАТИ ВІДГУК» (`group_url_feedback_reply_markup`)
   - «НАДІСЛАТИ ВІДГУК» (`group_webapp_feedback_reply_markup`)
   - Telegram Bot API підтримує: `danger` (червоний), `success` (зелений), `primary` (синій)

3. **Локалізація тексту вакансії** — розкоментовані переклади в `locale/uk/LC_MESSAGES/django.po`:
   - `from` → `з`, `to` → `до` (Час роботи: з 07:00 до 07:45)
   - `Vacancy is close` → `Вакансію закрито`

4. **Виправлено `vacancy_stop_search`** — view падав з `AttributeError: 'NoneType' object has no attribute 'user_links'`:
   - Причина: викликався `VacancyIsFullObserver` напряму, який перевіряв `vacancy.group.user_links` (group=None для деяких вакансій)
   - Рішення: замінено на прямий виклик — знаходить `ChannelMessage`, оновлює текст на «Вакансію закрито» через `TelegramStrategyFactory`, встановлює `status=STATUS_CLOSED`
   - Додано імпорт `STATUS_CLOSED` в `vacancy/views.py`

5. **Права бота в групах** — 2 групи мали статус `member` замість `administrator`:
   - `Группа Вашей вакансии 2` (-1002831363986) — бот призначений адміном
   - `Группа Вашей вакансии 3` (-1002590038330) — бот призначений адміном
   - Помилка `not enough rights to manage chat invite link` усунена

6. **Захист від подвійного створення вакансії:**
   - Серверний: перед `vacancy_form.save()` перевірка на існуючу pending-вакансію з тими ж address/date/start_time → redirect замість створення дубля
   - Фронтенд: JS `button.disabled=true` + текст «Зачекайте...» після натискання submit

**Оновлені файли:**
- service/telegram_markup_factory.py — style='danger' для 3 кнопок
- vacancy/views.py — виправлено vacancy_stop_search, додано STATUS_CLOSED імпорт, захист від дублів
- vacancy/templates/vacancy/vacancy_form.html — JS захист від подвійного submit
- locale/uk/LC_MESSAGES/django.po — розкоментовані from/to/Vacancy is close
- requirements (pyTelegramBotAPI 4.32.0)

### Сессия 28.03.2026 (ніч, частина 2) — Мультимісто для Employer

**Реалізовано повну підтримку розміщення вакансій в різних містах:**

1. **Модель** — `UserWorkProfile` розширено:
   - `multi_city_enabled` (BooleanField) — прапорець активації мультимісто
   - `allowed_cities` (M2M → City) — дозволені міста для розміщення вакансій
   - Міграція: work/migrations/0005_add_multi_city_fields.py

2. **Адмін-панель** — `UserWorkProfileInline` в UserAdmin:
   - Додано поля `multi_city_enabled` та `allowed_cities` (filter_horizontal)
   - Адміністратор вмикає функцію та обирає міста для конкретного Employer

3. **Форма створення вакансії** — `VacancyForm`:
   - Додано поле `city` (ModelChoiceField)
   - При мультимісті: `<select>` зі списком дозволених міст (allowed_cities + основне місто)
   - Без мультимісто: HiddenInput з містом із профілю
   - `save()` використовує обране місто для визначення каналу: `Channel.objects.get(city=selected_city)`
   - Конструктор приймає `work_profile` kwarg

4. **Шаблон форми** — `vacancy_form.html`:
   - Вгорі під заголовком: поточне місто (текст) або випадаючий список міст

5. **Дашборд Employer** — `employer_dashboard.html` + `index.py`:
   - Кнопка «Мої міста» при мультимісті → окрема сторінка зі списком міст
   - При одному місті → пряме посилання на канал

6. **Сторінка «Мої міста»** — нова:
   - View: `employer_cities` в work/views/employer.py
   - Шаблон: work/templates/work/employer_cities.html
   - URL: /work/employer/cities/ (work:employer_cities)
   - Список міст з посиланнями на канали, основне місто позначено "(основне)"

7. **Картки вакансій** — `vacancy_my_list.html`:
   - Кожна картка підписана: місто + адреса (channel.city · address)

8. **Модерація** — `admin_moderate_vacancy`:
   - Форма отримує `work_profile` власника вакансії (не адміністратора)
   - GET: `initial['city']` = vacancy.channel.city_id → правильне місто в формі
   - POST: `vacancy.channel` оновлюється з обраного міста

9. **Критичний фікс — публікація в правильний канал**:
   - `approved_channel_observer.py` — замінено `Channel.objects.filter(city=vacancy.owner.work_profile.city)` → `vacancy.channel`
   - `refind_observer.py` — аналогічно
   - `vacancy/tasks/resend.py` (ротація) — аналогічно
   - `vacancy/admin.py` (Django Admin save_model) — `Channel.objects.get(city=work_profile.city)` → використовує існуючий `vacancy.channel` якщо він вже встановлений

**Нові файли:**
- work/migrations/0005_add_multi_city_fields.py
- work/templates/work/employer_cities.html

**Оновлені файли:**
- work/models.py — +multi_city_enabled, +allowed_cities
- user/admin.py — UserWorkProfileInline +multi_city_enabled, +allowed_cities, +filter_horizontal
- vacancy/forms.py — +city field, +City import, +work_profile kwarg, save() uses selected city
- vacancy/views.py — vacancy_create передає work_profile в VacancyForm
- vacancy/templates/vacancy/vacancy_form.html — city selector вгорі
- vacancy/templates/vacancy/vacancy_my_list.html — місто в картках
- work/views/index.py — city_channels контекст для мультимісто
- work/views/employer.py — +employer_cities view
- work/views/admin_panel.py — work_profile owner для модерації, city в initial, channel update
- work/templates/work/employer_dashboard.html — мультимісто кнопка
- work/urls.py — +employer/cities/
- vacancy/services/observers/approved_channel_observer.py — vacancy.channel замість work_profile.city
- vacancy/services/observers/refind_observer.py — vacancy.channel замість work_profile.city
- vacancy/tasks/resend.py — vacancy.channel замість work_profile.city
- vacancy/admin.py — умовне присвоєння channel
- telegram/static/css/styles.css — +city-selector, +city-current стилі

**Як активувати мультимісто для Employer:**
1. Django Admin → Users → знайти Employer
2. Work profile → ✅ Multi-city enabled
3. Allowed cities → обрати додаткові міста
4. Зберегти

**Пріоритети (оновлені 29.03.2026):**
1. ЛК Worker — доработка: блокировка UI, запрос телефона після підтвердження вакансії
2. Ротація вакансій (Celery task кожні 5 хв)
3. Monobank оплата — UI в ЛК
4. Продовження на завтра — розсилка, очікування, перестворення

### Сессия 29.03.2026 (вечір) — Система відгуків і рейтингу

**Виконано:**

1. **UserFeedback модель оновлена** — нові поля:
   - `rating` (CharField): `like` / `dislike` / `none`
   - `is_auto` (BooleanField, default=False) — автоматично створені системою
   - Міграція: `user/migrations/0016_userfeedback_is_auto_userfeedback_rating_and_more.py`

2. **AutoRatingObserver** (`vacancy/services/observers/auto_rating.py`) — автоматичні відгуки (is_auto=True):
   - Worker: `+like` при успішному завершенні вакансії (AFTER_START_CALL_SUCCESS)
   - Worker: `+dislike` за провал переклички
   - Employer: `+like` за оплату, `+dislike` за відміну/неоплату

3. **vacancy_feedback.html** — перероблена форма відгуку:
   - Вибір рейтингу: лайк 👍 / дизлайк 👎 / без оцінки (radio-кнопки)
   - Текстове поле (необов'язкове)

4. **vacancy_user_list.html** — список учасників з модальним вікном:
   - Список карток: ім'я → клік → модальне вікно
   - Модальне: «Залишити відгук», «Подивитись відгуки», «Подивитися контакти»
   - Контакти залежать від ролі:
     - `employer` → href на `vacancy:members` (сторінка з телефонами)
     - `worker` → fetch POST на `vacancy:send_contact` → бот надсилає телефон замовника

5. **vacancy_user_reviews.html** — рейтинг і відгуки користувача:
   - Ім'я, лайки 👍 / дизлайки 👎, список текстових відгуків з датою

6. **vacancy_send_contact view** — новий endpoint:
   - POST, тільки для worker
   - Надсилає: `Контактний телефон замовника за вакансією {address}: {phone}`
   - Телефон: `vacancy.contact_phone` або `vacancy.owner.phone_number`
   - Повертає `JsonResponse({'ok': True})` або `{'ok': False, 'error': '...'}`

7. **ЛК Worker і Employer** — «Мій рейтинг / Мої відгуки»:
   - % лайків, прогрес-бар, список відгуків з адресою вакансії (з `extra.vacancy_id`)

8. **Перейменування:**
   - «Поточні заявки» → «Поточні вакансії» (employer_dashboard.html, vacancy_my_list.html, employer_faq.html)
   - Кнопка в групі «Відгуки/Контакти» → «Надіслати відгук» (telegram_markup_factory.py)

9. **UserFeedbackAdmin** — новий клас в `user/admin.py`:
   - `list_display`: id, user, owner, rating, is_auto, short_text, created_at
   - `list_editable = ('rating',)` — редагування рейтингу прямо зі списку
   - `readonly_fields`: owner, user, is_auto, extra, created_at

10. **Фікс UserBlockInline** — додано `fk_name = 'user'` (усуває конфлікт FK при двох FK на User в UserBlock)

**Нові файли:**
- `user/migrations/0016_userfeedback_is_auto_userfeedback_rating_and_more.py`
- `vacancy/services/observers/auto_rating.py`
- `vacancy/templates/vacancy/vacancy_user_list.html`
- `vacancy/templates/vacancy/vacancy_user_reviews.html`

**Оновлені файли:**
- `user/models.py` — +rating, +is_auto в UserFeedback
- `user/admin.py` — +UserFeedbackAdmin, +fk_name='user' в UserBlockInline
- `vacancy/views.py` — +vacancy_send_contact, vacancy_user_list з user_role/contact_phone в контексті
- `vacancy/urls.py` — +`<pk>/send-contact/` (name='send_contact')
- `vacancy/forms.py` — VacancyUserFeedbackForm оновлена (rating + text)
- `vacancy/templates/vacancy/vacancy_feedback.html` — лайк/дизлайк UI
- `work/templates/work/worker_reviews.html` — рейтинг-бар
- `work/templates/work/employer_reviews.html` — рейтинг-бар
- `vacancy/services/observers/subscriber_setup.py` — підписка AutoRatingObserver
- `work/templates/work/employer_dashboard.html` — Поточні вакансії
- `vacancy/templates/vacancy/vacancy_my_list.html` — Поточні вакансії
- `work/templates/work/employer_faq.html` — Поточні вакансії
- `service/telegram_markup_factory.py` — кнопка «Надіслати відгук»

**Пріоритети (оновлені 29.03.2026, вечір):**
1. ЛК Worker — блокировка UI при блокуванні
2. Ротація вакансій (Celery task кожні 5 хв)
3. Monobank оплата — UI в ЛК

### Сессия 30.03.2026 — ЖЦВ: повна реалізація жизненного цикла вакансии

**Реалізовано:**

1. **Нові статуси вакансії:**
   - `STATUS_SEARCH_STOPPED` — пошук зупинено заказчиком
   - `STATUS_AWAITING_PAYMENT` — очікує оплати (після завершення вакансії)

2. **Нові поля Vacancy:**
   - `closed_at` — час закриття вакансії
   - `search_stopped_at` — час зупинки пошуку
   - `first_rollcall_passed` — перша перекличка пройдена (bool)
   - `second_rollcall_passed` — друга перекличка пройдена (bool)

3. **Керування вакансією (vacancy_detail):** — єдина сторінка з кнопками що перемикаються:
   - ЗУПИНИТИ ПОШУК / ПОНОВИТИ ПОШУК (залежно від статусу)
   - ПЕРЕКЛИЧКА ПОЧАТОК / ПЕРЕКЛИЧКА КІНЕЦЬ (залежно від first_rollcall_passed)

4. **ЗАКРИТИ ВАКАНСІЮ** — 3-годинний таймер (`close_lifecycle_timer_task`):
   - Після спрацювання → обнуление групи (status=available), видалення учасників
   - Відправка повідомлень всім учасникам про закриття

5. **Підтвердження рабочого (worker_join_confirm):**
   - 5 хв таймер після вступу в групу
   - Нагадування Employer якщо не підтверджено
   - Запит телефону у Worker при підтвердженні вакансії
   - Celery task: `worker_join_confirm_check_task`

6. **Автозупинка пошуку** — при початку робочого часу (start_call) пошук зупиняється автоматично

7. **Переклички заказчика:**
   - Нагадування кожні 5 хв × 6 разів
   - Ескалація адміністратору після 6 спроб без відповіді

8. **Оплата (Monobank UI):**
   - `vacancy_payment` view → `create_invoice()` → редирект на Monobank
   - Webhook → `process_webhook()` → `is_paid=True` → розблокування Employer

9. **Продовження на завтра:**
   - Опитування заказчика після завершення вакансії
   - Форма з датою=завтра (дублює поточну вакансію)
   - Модерація нової вакансії
   - Опитування рабочих — бажають продовжити?
   - Порівняння кількості підтверджених рабочих

10. **call_formatter.py** — централізовані тексти всіх сповіщень ЖЦВ на українській мові

**Celery tasks (vacancy/tasks/):**
- `close_lifecycle_timer_task` — закриття вакансії через 3 год
- `worker_join_confirm_check_task` — підтвердження рабочого (5 хв)
- `renewal_offer_task` — пропозиція продовження заказчику
- `renewal_worker_check_task` — опитування рабочих про продовження

**Коміт:** e6a8c06

## Django Admin — реорганизация (31.03.2026)

### Секции админки (в порядке отображения)
1. **КОРИСТУВАЧІ** (app: user) — Користувачі, Відгуки користувачів
2. **ВАКАНСІЇ ТА РОБОТА** (app: vacancy) — Вакансії, Учасники вакансій, Переклички
3. **МІСТА ТА КАНАЛИ** (app: city) — Міста, Канали
4. **ТЕЛЕГРАМ ГРУПИ** (app: telegram) — Групи вакансій, Учасники груп, Повідомлення в групах, Повідомлення в каналах
5. **ОПЛАТА** (app: payment) — Платежі Monobank
6. **ДОКУМЕНТИ** (app: work) — Тексти угод

### Что сделано
- Удалены из админки: стандартные Django auth Groups, simplejwt Blacklisted/Outstanding tokens (через `user/admin_site.py` → `unregister()` в `UserConfig.ready()`)
- Все verbose_name моделей переведены на украинский
- Порядок секций кастомизирован через monkey-patch `AdminSite.get_app_list` в `user/admin_site.py`
- Заголовки: site_header="Robochi Bot", site_title="Robochi Admin", index_title="Панель керування"

### Ключевые файлы
- `user/admin_site.py` — unregister ненужных моделей + порядок секций + заголовки
- `user/apps.py` → `ready()` импортирует `user.admin_site`
- `vacancy/admin.py` — VacancyAdmin с 14 actions, StatusDefaultFilter, auto-assign group/channel
- `user/admin.py` — UserAdmin с 4 инлайнами, 5 фильтрами, auto-sync is_staff↔ADMINISTRATOR role
- `payment/admin.py` — MonobankPaymentAdmin
- `telegram/admin.py` — GroupAdmin с actions (kick, invite link, delete messages, permissions)
- `telegram/admin_actions.py` — переиспользуемые admin actions для групп/каналов

### API app (не удалён)
Приложение `api/` (DRF + simplejwt + corsheaders + drf_spectacular) оставлено в проекте — используется `MonobankWebhookView` (`api/views/payment.py`) для приёма webhook Monobank. Остальные endpoints (auth, user, vacancy) не используются фронтом (WebApp работает через Django views).

## Безопасность (настроено 06.04.2026)

**Серверная безопасность:**
- **UFW firewall**: включен, открыты только 22/tcp, 80/tcp, 443/tcp
- **Redis**: пароль установлен (hex, без спецсимволов), Celery broker использует `redis://:PASSWORD@localhost:6379/0`
- **`.env` права**: `chmod 600` — читаем только владельцем (webuser)
- **Nginx**: `server_tokens off` (версия скрыта), `client_max_body_size 2m`
- **Бэкап БД**: cron ежедневно в 03:00, хранение 14 дней, `/home/webuser/backups/`

**Django security:**
- **Django admin URL**: `/taya-panel/` (не стандартный `/admin/`)
- **API schema/docs**: закрыты `IsAdminUser` — 403 для неавторизованных
- **Неавторизованные пользователи**: корневой URL `/` → redirect на `https://robochi.work`
- **auth_date expiry**: 7200 секунд (2 часа) вместо 86400 (24 часа)
- **Session hardening** (production.py): `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `CSRF_COOKIE_HTTPONLY`, `SESSION_COOKIE_AGE=86400`
- **SameSite=None**: оставлено — необходимо для Telegram WebApp iframe

**Nginx security headers:**
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Content-Security-Policy`: self + telegram.org + monobank.ua
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `X-Robots-Tag: noindex, nofollow`

**Nginx rate limiting:**
- `/telegram/webhook-*`: 30r/s burst=50
- `/telegram/authenticate-web-app/`: 5r/s burst=10

**Тесты безопасности:** `tests/test_security.py` — 12 тестов (admin URL, API schema, unauth redirect, auth_date expiry, Redis password, session settings)

**Регресійні тести:** `tests/test_bugfix_channel_in_groups.py` — 2 тести (09.04.2026): `auto_approve` та `handle_user_status_change` не створюють Group для каналів (chat.type="channel")

## Скрытие кнопок vacancy_detail + удаление сообщений модерации (09.04.2026)

- **vacancy_detail:** кнопки действий скрыты для pending и closed статусов. Шаблон: `{% if not is_pending and not is_closed_lifecycle %}`. Переменные из view: `is_pending`, `is_closed_lifecycle`.
- **VacancyCreatedAdminObserver:** отправляет сообщения каждому админу поштучно, сохраняет `vacancy.extra['admin_moderation_messages'] = {str(admin_chat_id): msg_id}`.
- **Удаление при approve/delete:** `admin_moderate_vacancy` и `admin_delete_vacancy` (work/views/admin_panel.py) итерируют `admin_moderation_messages`, удаляют сообщения через `bot.delete_message()`, затем очищают ключ из `extra`.
- **Регресійні тести:** `tests/test_vacancy_detail_buttons.py` — 8 тестів (09.04.2026)

### Обновления 09-10.04.2026
- Карточки пользователей в ЛК Администратора: uniform width (width:100%, box-sizing)
- Админ получил доступ к ЛК заказчика: vacancy:my_list?for_user=X, vacancy:detail для staff
- Все vacancy action views разрешены для is_staff (owner check обходится)
- Убран блок-статус из vacancy_my_list при admin view
- Валидация формы вакансии: сообщение о start_time переведено на укр
- После модерации redirect на vacancy:my_list?for_user= вместо admin_vacancy_card
- Регрессионные тесты: tests/test_admin_panel.py
