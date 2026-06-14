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

### 05.06.2026 (3) — Фикс дубля рассылки «Через 2 години» после continue_search

**Баг:** после нажатия «Продовжити пошук» (быстрая докомплектация) рабочим повторно приходило сообщение «Через 2 години початок роботи».

**Причина:**
- `continue_search` сдвигал `start_time` вперёд (если время начала уже прошло) и стирал ВСЕ записи `VacancyUserCall` для вакансии, включая `BEFORE_START`.
- Следующий тик `before_start_call_task` (Celery): новый `start_time` снова попадал в окно «2 часа до начала», `check_before_start` не находил записей `BEFORE_START` → отправлял рассылку повторно.

**Фикс — два слоя защиты в `vacancy.extra`:**
1. `original_start_datetime` (ISO-строка) — якорь, выставляется при создании цикла, не меняется `continue_search`. Используется в `get_before_start_vacancies` (фильтр окна) и `check_before_start` (вычисление `two_hours_before`).
2. `pre_call_done` (bool) — флаг, выставляется в `check_before_start` после хотя бы одной успешной отправки. Фильтр и observer оба ранний-`return` при `True`.

**Хелпер `vacancy/services/call.py::reset_before_start_cycle(vacancy)`** — сбрасывает оба ключа и перезаписывает `original_start_datetime` на текущий `start_time`. Вызывается при старте НОВОГО цикла поиска:
- `vacancy_create` (vacancy/forms.py) — изначально
- `vacancy_resume_search` (vacancy/views.py) — после ЗУПИНИТИ/ПОНОВИТИ через модерацию, заказчик мог изменить время
- `admin_moderate_vacancy` (work/views/admin_panel.py) — админ мог изменить время

**`continue_search` (vacancy/views.py) хелпер НЕ вызывает** — это тот же цикл (просто докомплектация), флаги остаются неизменными.

**Сводная таблица:**

| Точка входа | Что меняется | `pre_call_done` |
|---|---|---|
| Створити вакансію | Всё | сбрасывается |
| Поновити пошук (с модерацией) | Время, дата, кол-во, оплата | сбрасывается → новая рассылка |
| Продовжити на завтра (renewal) | Время, дата=завтра, оплата | сбрасывается |
| Модерация админом | Любое | сбрасывается |
| **Продовжити пошук** (continue_search) | Только сдвиг `start_time` если просрочено | **остаётся** → без повторной рассылки |

**Изменённые файлы:**
- `vacancy/services/call.py` — добавлен хелпер `reset_before_start_cycle`
- `vacancy/forms.py` — вызов хелпера после создания
- `vacancy/views.py` — вызов хелпера в `vacancy_resume_search`
- `work/views/admin_panel.py` — вызов хелпера в `admin_moderate_vacancy`
- `vacancy/tasks/call.py` — `get_before_start_vacancies` учитывает оба слоя
- `vacancy/services/observers/call_observer.py` — `check_before_start` учитывает оба слоя + ставит флаг

**Тесты:** `tests/test_session_20260605_before_start_no_repeat.py` — 7 тестов, все зелёные:
- filter skip при `pre_call_done=True`
- filter использует якорь `original_start_datetime`, а не live `start_time`
- continue_search не трогает оба ключа
- end-to-end: notice → continue_search → filter возвращает пусто
- check_before_start ставит `pre_call_done` после рассылки
- check_before_start ранний-return при `pre_call_done=True`
- `reset_before_start_cycle` сбрасывает флаг и обновляет якорь

Соседние 18 тестов (continue_search_time, members_rollcall, auto_approve_regression) тоже зелёные — регрессий нет.

### 05.06.2026 — Фикс повторного кика на перекличке + race condition в публикации канала

**Баг-фикс 1: повторный кик после разблокировки**
- Сценарий: рабочий проигнорировал BEFORE_START перекличку (за 2ч до начала), кикнут + создан `UserBlock(ROLLCALL_REJECT)`. Админ снял блок в админ-панели, рабочий заново нажал «Я ГОТОВИЙ ПРАЦЮВАТИ» — система мгновенно кикала его повторно.
- Причина: в БД оставалась запись `VacancyUserCall(BEFORE_START, status=SENT)` со старым `created_at`. `check_before_5_start` видел её, `elapsed >> 300s` → кик.
- Фикс: `vacancy/services/observers/call_observer.py::check_before_5_start`:
  - Пропуск если `member.updated_at > user_answer.created_at` (рабочий зашёл уже после переклички)
  - Пропуск если статус уже `CONFIRM` или `REJECT`
  - При кике записываем `call.status = REJECT` (финализация)

**Баг-фикс 2: дубль публикации вакансии в канале**
- Сценарий: рабочий выходит из группы ровно когда `resend_vacancies_to_channel_task` подходит на тике с `last_msg age >= 300s` → оба пути (`VacancySlotFreedObserver` + Celery rotation) читают список `ChannelMessage` одновременно, удаляют по своей копии, публикуют каждый свой пост → в канале два одинаковых сообщения.
- Фикс: добавлен короткий мьютекс через Django cache `vacancy_publish_lock:{id}` (TTL 15с), общий между `vacancy/tasks/resend.py::resend_vacancy_to_channel` и `vacancy/services/observers/member_observer.py::VacancySlotFreedObserver`. Кто первым взял замок — публикует, второй пишет лог-пропуск и выходит.

**Тесты:** `tests/test_session_20260605_rollcall_rejoin.py` (5 тестов, все зелёные):
- skip при rejoin (updated_at > call.created_at)
- skip при REJECT/CONFIRM
- финализация в REJECT при кике
- rotation skip при удержанном lock
- rotation публикует при свободном lock + освобождает lock

**Связанная правка теста:** `vacancy_feedback.html` и `vacancy_user_reviews.html` исключены из `test_no_emoji_in_template` (теперь содержат функциональные кнопки 👍/👎 из фичи рейтинга от 04.06).

Коммиты: `8a52261` (rollcall), `e2b2681` (channel race), `520c487` (no-emoji test).

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
- Кікнутого рабочого розблокування автоматичне (kick_user робить unban в finally). Рабочий може повторно подати заявку через канал міста. (vacancy_reinvite_worker видалено 18.05.2026)
- Страница «Додавання/Видалення працівників. Відгуки/Контакти» (бывшая «Група з працівниками»)

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

## Contact Phone System (Apr 24+29 sessions — DONE)

**Two phones per user:**
- `User.phone_number` — registration phone (from Telegram contact), permanent, never shared
- `User.contact_phone` — contact phone for work interactions, persistent, updated on each change

**Per-vacancy snapshot:**
- `VacancyContactPhone(vacancy, user, phone)` — copy of contact phone at time of vacancy participation
- Created when: employer saves vacancy form; worker confirms phone in bot
- Cascade-deleted with vacancy (ЖЦВ cleanup)

**Employer flow:**
- `User.contact_phone` auto-fills vacancy form field "Телефон для зв'язку"
- On save/edit: writes to `VacancyContactPhone` + updates `User.contact_phone`
- `Vacancy.contact_phone` still written for backward compat

**Worker flow:**
- After "Підтвердити" join: bot shows saved `User.contact_phone` with buttons "Підтвердити" / "Змінити"
- "Підтвердити" → saves to `VacancyContactPhone`, sends group invite
- "Змінити" → asks for new number → saves to `VacancyContactPhone` + `User.contact_phone`
- First time (no contact_phone) → asks to enter number

**Key files:**
- `user/models.py` — `User.contact_phone` field
- `vacancy/models.py` — `VacancyContactPhone` model
- `telegram/handlers/callback/phone_confirm.py` — Підтвердити/Змінити buttons handler
- `telegram/handlers/messages/worker_phone.py` — text input handler, saves to both models
- `telegram/handlers/callback/call.py` — WORKER_JOIN_CONFIRM: shows phone or asks for input
- `vacancy/forms.py` — employer phone save to both models
- `vacancy/views.py` — pre-fill from `User.contact_phone`, edit save to both models

**All fallbacks to `owner.phone_number` removed.** Registration phone never shared.



## «Я ГОТОВИЙ ПРАЦЮВАТИ» — рефакторинг (Apr 29, 2026)

### Новый флоу (worker)
1. Рабочий нажимает «Я ГОТОВИЙ ПРАЦЮВАТИ» в канале → deep link в бот → /start
2. `commands.py:_process_apply_payload()` — создаёт `VacancyUser(MEMBER)` + `VacancyUserCall(WORKER_JOIN_CONFIRM, SENT)` → отправляет confirm-сообщение с кнопками Підтвердити/Відміна. Рабочий **НЕ в группе** на этом этапе.
3. Підтвердити → `call.py` → проверяет `VacancyContactPhone`: если телефон есть → сразу invite в группу; если нет → запрос телефона
4. Ввод телефона → `worker_phone.py` → сохраняет в `VacancyContactPhone` (не `User.phone_number`) → `send_worker_group_invite()` → invite в группу
5. Уже в этой вакансии (confirmed) → сообщение «Перейдіть у Власний кабінет» + кнопка
6. Employer нажимает → сообщение «Перейдіть у Власний кабінет» (не worker flow)
7. Таймаут 5 мин без підтвердження → `VacancyUser → LEFT` (без кика из группы, рабочий не был в группе)

### Изменённые файлы
- `telegram/handlers/callback/apply_vacancy.py` — `_encode_start_payload()`, проверка already_in_vacancy, убран fallback `_send_invite` для рабочего
- `telegram/handlers/messages/commands.py` — `_process_apply_payload()`, `_send_cabinet_message()`, employer-check
- `telegram/handlers/callback/call.py` — CONFIRM: проверка VacancyContactPhone → invite или запрос телефона; REJECT: VacancyUser→LEFT без кика
- `telegram/handlers/messages/worker_phone.py` — сохранение в VacancyContactPhone + `send_worker_group_invite()` + контакт замовника
- `vacancy/services/worker_invite.py` (новый) — `send_worker_group_invite(user, vacancy)`
- `telegram/handlers/member/user/group.py` — удалён join-confirm блок (перенесён в commands.py)
- `vacancy/tasks/call.py` — timeout: VacancyUser→LEFT + уведомление (без GroupService.kick_user)

### Хранение телефонов
- `User.phone_number` — телефон при регистрации (только для авторизации)
- `VacancyContactPhone(vacancy, user, phone)` — телефон для конкретной вакансии (рабочий и заказчик)
- `Vacancy.contact_phone` — телефон заказчика из формы вакансии

### Тесты
- `tests/test_apply_flow.py` — 6 тестов: create VacancyUser+call, employer→cabinet, already_confirmed→cabinet, group_full, phone→VacancyContactPhone, timeout→LEFT
## На горизонте (приоритеты)
1. AgreementText для employer/worker в admin
2. ЛК администратора — наполнить функционалом
3. ЛК Employer — Фаза 2: управление заявками из ЛК — **DONE** (ЖЦВ)
4. ЛК Worker — доработка: блокировка UI при блокировке
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

2. **Фільтр admin_vacancy_card** — додано status__in=[STATUS_PENDING, STATUS_APPROVED, STATUS_APPROVED]:
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
   - Кнопка в групі «Відгуки/Контакти» (прямий WebApp через vacancy_feedback_redirect). (18.05.2026: було «Надіслати відгук», перейменовано та переписано на WebApp)

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
- `service/telegram_markup_factory.py` — кнопка «Відгуки/Контакти» (WebApp, перейменована і переписана 18.05.2026)

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

### Сессія 14.04.2026 — Тексти блокування, перекличка, права заказчика, WebApp

**Виконано:**

1. **Тексти блокування** (`telegram/handlers/messages/commands.py`, `work/views/admin_panel.py`, `vacancy/services/call_formatter.py`):
   - Постійна: "Вас заблоковано у сервісі robochi.work !\nДля розблокування зверніться до Адміністратора- @robochi_work_admin"
   - Тимчасова: "Увага! Вас обмежено у користуванні сервісом robochi.work !\nДля розблокування зверніться до Адміністратора- @robochi_work_admin"
   - `days_text` і `block =` прибрані як unused (ruff F841)

2. **Дубль сповіщення при схваленні вакансії** — метод `_add_employer_to_group` видалено з `approved_group_observer.py`; текст повідомлення 2 оновлено; `employer_invite_msg_id` більше не встановлюється

3. **Перекличка «Кінець роботи»** — `get_final_call_vacancies(before_end=60)` ловить вакансії за 1 годину до `end_time`; `final_call_check_task` використовує нову функцію

4. **Перекличка «Початок роботи»** — `_MAX_REMINDERS = 12` (було 6) → 60 хвилин очікування замість 30

5. **Кнопка переклички в ЛК** — після 1-ї переклички одразу показується кнопка 2-ї; заголовки "Початок роботи" / "Кінець роботи"; посилання "Повернутися до першої переклички"

6. **Права замовника в групі** — `can_restrict_members=False` в `set_default_owner_permissions()`; видалення робітників тільки через ЛК (сторінка members)

7. **Single-instance guard для WebApp** — `lifecycle.js` v6: BroadcastChannel закриває попереднє вікно; reload з retry (500ms/1000ms/1500ms); поріг freeze 3000ms

8. **Fallback у check.html** — при порожньому `initData` інформативне повідомлення з кнопкою "Перейти до бота"

9. **Favicon** — `favicon.ico`, `favicon-32x32.png`, `apple-touch-icon.png` у `telegram/static/`; підключено в `templates/base.html`

10. **Форма створення вакансії** — `start_time` і `end_time` прибрані з initial шаблону; час завжди перераховується від поточного моменту (now+1h rounded to 15min)

11. **Навігація адміна після модерації** — редирект після approve → `admin_dashboard`; кнопки «Назад» в `admin_vacancy_card.html` і `vacancy_my_list.html` → `admin_dashboard`

### Сессія 15.04.2026 — FAQ система (FaqItem) + переименування

**Виконано:**

1. **Модель FaqItem** (`work/models.py`) — динамічні FAQ-записи з адмінки:
   - Поля: `role` (employer/worker), `question`, `answer`, `image` (ImageField, upload_to="faq/"), `video_url` (URLField), `order`, `is_active`, timestamps
   - Property `video_embed_url` — автоконвертація YouTube URL у embed формат
   - Meta: ordering=["role", "order"], verbose_name="FAQ запис"
   - Міграція: work/migrations/0007_faqitem.py

2. **FaqItemAdmin** (`work/admin.py`):
   - list_display: role, question_short, order, is_active, has_image, has_video, updated_at
   - list_filter: role, is_active
   - list_editable: order, is_active
   - Кастомні display-методи: question_short, has_image (boolean), has_video (boolean)

3. **MEDIA налаштування**:
   - `MEDIA_URL = "/media/"`, `MEDIA_ROOT = BASE_DIR / "media"` додано в `config/django/base.py`
   - Директорія `media/faq/` створена
   - Nginx вже обслуговує `/media/` → `/home/webuser/robochi_bot/media/`

4. **Views оновлені** — `employer_faq` та `worker_faq`:
   - Імпорт FaqItem, фільтрація по role та is_active
   - Передача `faq_items` у контекст шаблону

5. **Шаблони переписані** — `employer_faq.html`, `worker_faq.html`:
   - Динамічний контент з БД замість hardcoded
   - `<details>` accordion з опціональним зображенням та відео
   - Fullscreen overlay для зображень (клік → розгортання)
   - YouTube iframe embed для відео
   - Empty state: «Інформація поки що не додана.»

6. **Перейменування** — «Що робити якщо?» → «Як це працює?»:
   - employer_dashboard.html — кнопка
   - worker_dashboard.html — кнопка
   - employer_faq.html — заголовок сторінки
   - worker_faq.html — заголовок сторінки

7. **Початкові дані** — 11 FAQ записів створено (5 employer + 6 worker)

8. **Регресійні тести** — `tests/test_session_20260415_faq.py` — 17 тестів:
   - TestFaqModel (5): import, role choices, video_embed_url property, ordering
   - TestFaqTemplates (6): exist, dynamic items, media support
   - TestDashboardRename (2): employer/worker dashboards renamed
   - TestFaqViews (2): views pass faq_items
   - TestFaqAdmin (1): admin registration
   - TestMediaSettings (2): config + directory

**Нові файли:**
- work/migrations/0007_faqitem.py
- tests/test_session_20260415_faq.py

**Оновлені файли:**
- work/models.py — +FaqItem
- work/admin.py — +FaqItemAdmin
- work/views/employer.py — employer_faq з FaqItem
- work/views/worker.py — worker_faq з FaqItem
- work/templates/work/employer_faq.html — динамічний шаблон
- work/templates/work/worker_faq.html — динамічний шаблон
- work/templates/work/employer_dashboard.html — «Як це працює?»
- work/templates/work/worker_dashboard.html — «Як це працює?»
- config/django/base.py — +MEDIA_URL, +MEDIA_ROOT
- CLAUDE.md — +FAQ System секція

### Сессия 16.04.2026 — bugfix admin filter "Заблоковані" + Invariants registry

**Fix:**
- work/views/admin_panel.py:78 — фильтр "Заблоковані" изменён с is_active=False на blocks__is_active=True (distinct)
- Причина (см. INV-009): только PERMANENT блокировки ставят User.is_active=False; TEMPORARY оставляют is_active=True
- Verification: recrutcorpltd (temporary rollcall_reject) теперь корректно возвращается в поиске

**Doc changes:**
- PROJECT_RULES.md — добавлена секция "Invariants" (INV-001..INV-009)
- CLAUDE.md — добавлен блок "Before doing anything" с порядком загрузки контекста

**Investigated (требует отдельной сессии):**
- Employer @recrutcorpltd попал в чужую vacancy 38 через "Я ГОТОВИЙ ПРАЦЮВАТИ"
- Диагноз: invite_link группы без creates_join_request=True → handler chat_join_request не сработал → сработал chat_member_handler (INV-007 — без проверки роли)
- План на след. сессию: согласно INV-005, добавить проверку в check_system.py; дублировать проверку role в chat_member_handler как fallback

---

**Сесія 18-19.04.2026 — Фільтри кнопки «Я ГОТОВИЙ ПРАЦЮВАТИ», повідомлення заказчику, Celery-таск запрошення в групу**

### Callback-архітектура кнопки «Я ГОТОВИЙ ПРАЦЮВАТИ»

Кнопка в каналі міста = `callback_data=f"apply:{vacancy.id}"`. При натисканні бот прогоняє 12 перевірок в `telegram/handlers/callback/apply_vacancy.py`:

1. Admin → deep link в бот (без перевірок)
2. Постійна блокировка → popup
3. Тимчасова блокировка → popup
4. `is_active=False` → popup
5. Не зареєстрований → popup з `@riznorobochi_ua_bot` + `@robochi_work_admin`
6. Вакансія не знайдена → popup
7. Owner вакансії → deep link в бот (`answer_callback_query(url=deep_link)`)
8. Чужий employer → popup «Ви не можете приєднатися до чужої вакансії.»
9. Вже в іншій вакансії → popup
10. Група заповнена → popup
11. Стать не вказана → popup
12. Стать не відповідає → popup «Ця вакансія призначена для іншої статі.»

Пройшов перевірки (worker) → deep link в бот → `process_start_payload` (type="apply") → silent return (повідомлення не надсилається, Celery-таск handles it).

INV-005 FIX блок в `chat_member_handler` залишено як safety net.
Admin bypass в `chat_member_handler` — не створює VacancyUser, тег «Адміністратор».

### Повідомлення заказчику

**2.1. Після створення вакансії (на модерацію):**
- Текст: «Ваша вакансія для пошуку працівників відправлена на модерацію...»
- Кнопка: «Як це працює?» → WebApp URL `/work/employer/faq/`
- `msg_id` зберігається в `vacancy.extra["created_msg_id"]`
- Файл: `vacancy/services/observers/created_user_observer.py`

**2.2. Після approve модерації:** Залишено як є + `msg_id` зберігається в `vacancy.extra["approved_msg_id"]`
- Файл: `vacancy/services/observers/approved_user_observer.py`

**2.3. Запрошення в групу (Celery-таск):**
- Файл: `vacancy/tasks/employer_group_invite.py`
- Зареєстровано в `vacancy/tasks/__init__.py`
- Через 5 сек після approve → повідомлення «Перейдіть у групу Вашої вакансії...» + кнопка
- Повтор кожну 1 хвилину, макс 10 разів
- Перевірка: якщо owner вже в групі (VacancyUser зі статусом OWNER/MEMBER) → зупинка
- Після 10 спроб без входу:
  1. Видалити всі сервісні повідомлення вакансії
  2. Надіслати попередження в групу
  3. Закрити вакансію через `vacancy_publisher.notify(VACANCY_CLOSE)`
  4. Заблокувати заказчика (BlockReason.EMPLOYER_NO_GROUP)
  5. Надіслати повідомлення про блокування

**Новий BlockReason:** `EMPLOYER_NO_GROUP = "employer_no_group"` + метод `BlockService.auto_block_employer_no_group()`
- Міграція: `user/0017`

### Видалення сервісних повідомлень при закритті вакансії

`VacancyDeleteEmployerInviteObserver` розширено — тепер видаляє: `employer_invite_msg_id`, `created_msg_id`, `approved_msg_id`, `apply_invite_msg_ids` (для всіх рабочих).
Спрацьовує при будь-якому `VACANCY_CLOSE` (через 3 години, вручну, через неприхід заказчика).

### Deep link автоперехід в бот

`telegram/handlers/messages/commands.py`: додано `encode_start_param()`, обробка `type="apply"` в `process_start_payload` — silent return без повідомлення.
`telegram/handlers/callback/apply_vacancy.py`: owner та worker після перевірок → `answer_callback_query(url=deep_link)` → автоматичне відкриття бота.

### Ключові файли змінені

- `service/telegram_markup_factory.py` — callback_data замість url
- `telegram/handlers/callback/apply_vacancy.py` — 12 перевірок + deep link
- `telegram/handlers/member/user/group.py` — INV-005 FIX блок (safety net) + admin bypass
- `vacancy/tasks/employer_group_invite.py` — Celery-таск з повторами
- `vacancy/tasks/__init__.py` — реєстрація таска
- `vacancy/services/observers/created_user_observer.py` — збереження msg_id + кнопка FAQ
- `vacancy/services/observers/approved_user_observer.py` — збереження msg_id + запуск таска
- `vacancy/services/observers/vacancy_close.py` — розширене видалення повідомлень
- `vacancy/services/call_formatter.py` — новий текст повідомлення 2.1
- `telegram/handlers/messages/commands.py` — encode_start_param + обробка type="apply"
- `user/choices.py` — BlockReason.EMPLOYER_NO_GROUP
- `user/services.py` — auto_block_employer_no_group()

## Session 10.06.2026 — Stage 6.B (continue offer + scenario В block)

### Changes

**1. Duplicate vacancy publication fix (вынесено отдельно ранее)**
- `vacancy/views.py::vacancy_create` и `vacancy_resume_search`: добавлен per-user cache lock (`vacancy_create_lock:{uid}`, TTL 10s) до обработки формы.
- DB-дедуп расширен: `status__in=[STATUS_PENDING, STATUS_APPROVED]`, фильтр по `(owner, date, start_time)` без адреса.
- НЕТ `created_at__gte` фильтра (модель `Vacancy` не имеет такого поля).

**2. Stage 6.B — search_more button**
- Шаблон `vacancy_members.html`: динамическая submit-кнопка «Підтвердити + шукати ще» (id=`btn-confirm-and-search`) появляется через inline JS когда есть снятые чекбоксы И `can_search=True`. Условие отображения GET-ссылки расширено с `scenario == "B"` до `scenario in "BC"`.
- `vacancy/views.py::vacancy_check_call`: ветка `request.POST.get("search_more") == "1"` и `len(selected_users) >= 1` запускает `start_continue_search(vacancy)` напрямую через сервис.

**3. Stage 6.B — DM-offer заказчику**
- Новый сервис `vacancy/services/continue_offer.py`:
  - `send_continue_offer_dm(vacancy)` — DM с двумя inline-кнопками («Шукати ще» / «Залишити як є»), сохраняет `extra["continue_offer_msg_id"]`, планирует `delete_continue_offer_task` с countdown=`(shift_start+1ч)-now`.
  - `start_continue_search(vacancy)` — reusable core, дублирует логику `_continue_search_after_first_rollcall` без request (для использования из view и callback).
  - `is_within_continue_deadline(vacancy)` — проверка `now < shift_start + 1ч`.
  - `delete_continue_offer_msg(vacancy)` — идемпотентное удаление DM + снятие флага.
- DM отправляется только если: `search_more != "1"` AND `1 <= selected_users < people_count` AND `now < shift_start + 1ч`.

**4. Stage 6.B — Scenario В block message**
- `vacancy/views.py`: в ветке `elif all_unchecked` для `CallType.START` после кика и блокировки заказчика отправляется DM по паттерну 2-й переклички:
  > «Ви заблоковані! Пройдіть першу перекличку повторно або зв'яжіться з Адміністратором для розблокування.»
  - Кнопка «До переклички» (web_app на `/vacancy/<pk>?focus=rollcall`)
  - Кнопка «Зв'язатися з адміністратором» (`https://t.me/robochi_work_admin`)
- `message_id` сохраняется в `extra["first_call_block_msg_id"]`.

**5. Stage 6.B — Callback handlers**
- `telegram/handlers/callback/continue_offer.py`:
  - `handle_continue_offer_search` (data `{"t":"co_search","v":<id>}`): проверяет дедлайн через `is_within_continue_deadline`, при истечении показывает alert «Вже пізно» и удаляет DM. Иначе удаляет DM + вызывает `start_continue_search`.
  - `handle_continue_offer_ignore` (data `{"t":"co_ignore","v":<id>}`): просто удаляет DM.
- Регистрация в `telegram/handlers/callback/__init__.py` (импорт перед `work_role`).

**6. Stage 6.B — Celery cleanup task**
- `vacancy/tasks/call.py::delete_continue_offer_task(vacancy_id)`: вызывает `delete_continue_offer_msg`. Планируется при отправке DM с countdown=`shift_start+1ч - now`, чтобы заказчик не мог нажать «Шукати ще» после дедлайна.

### Key learnings & patterns

- Telegram **callback_data** должен быть JSON, паттерн `'"t": "<type>"' in c.data` для роутинга через `bot.callback_query_handler(func=...)`. Иначе нужно регистрировать каждый handler в `callback/__init__.py`.
- **«Шукати ще»** в карточке вакансии (`vacancy_detail.html`) уже отображается счётчиком «Триває добір — залишилось X хв» когда `extra["continue_after_first_rollcall"]=True`. Это работает автоматически из любой точки запуска (форма, DM-кнопка).
- При extract'е логики из view-функции в reusable-сервис: убрать `request`, использовать timezone+now() напрямую. View оставляет за собой только `redirect(...)`.
- **Идемпотентность DM**: всегда сохранять `message_id` в `extra`, удаление через try/except (Telegram кидает ошибку если сообщение уже удалено).
- **`scenario`** в `vacancy_check_call`: `"A"`=0 работников, `"B"`=<people_count, `"C"`=>=people_count. Кнопка «Продовжити пошук» теперь показывается в B И C (раньше только B).

### Regression tests
- `tests/test_session_20260609_vacancy_create_dedup.py` — двойной POST + ORM-дедуп
- `tests/test_session_20260610_continue_offer.py` — DM-offer, идемпотентность delete, дедлайн, start_continue_search


## Session 2026-04-30

### Worker «Моя робота» page
- New view `worker_my_work` in `work/views/worker.py` + template `work/templates/work/worker_my_work.html`
- URL: `/work/my-work/` (name: `work:worker_my_work`)
- Shows vacancy detail + buttons: Група моєї роботи, Залишити відгук
- Employer contact phone shown only when <= 2h before start_time
- Vacancy shown ONLY when worker is in Telegram group (UserInGroup check)
- Worker dashboard button leads to this page instead of direct group link
- Renamed: Мої вакансії -> Загальна стрічка вакансій

### Phone flow fixes
- Змінити in phone_confirm: deletes old VacancyContactPhone before accepting new number
- worker_phone handler: iterates CONFIRM calls by created_at DESC, picks vacancy without saved CP
- Employer contact phone removed from bot messages, shown only in worker LK

### before_start_call fix
- Skips workers who joined < 2h before start (start_aware - join_confirm.created_at < 7200)
- Uses .value for enum comparisons in ORM filters
- VacancyUserCall.update_or_create: call_type moved to lookup key

### Group join and limits
- VACANCY_NEW_MEMBER notify added in group.py -> triggers VacancyIsFullObserver
- people_count check removed from apply_vacancy and commands (controlled by channel button)
- Group full check uses UserInGroup count instead of VacancyUser
- Invite message deleted from bot on group join and kick

### Timeout and rejection flow
- confirm message_id saved in vacancy.extra for deletion on 5min timeout
- Cabinet link message sent after timeout and rejection
- VacancyContactPhone cleaned up on rejection and timeout for fresh re-apply

## Session 2026-05-04 — Group reset + invite links + worker tag

### Group selection ordering fix (group_selection_nulls_first)
- `GroupService.get_available_group()` теперь сортирует `F("last_used_at").asc(nulls_first=True)`
- До фикса: PostgreSQL ставил `NULL` в конец → новые неиспользованные группы простаивали
- После фикса: группы с `last_used_at=NULL` (никогда не использованные) выбираются первыми

### Полное обнуление группы (`GroupService.reset_group`)
Метод вызывается из `VacancyKickGroupUsersObserver` при VACANCY_CLOSE. Шаги:
1. Запоминает `last_msg_id` ИЗ ЗАКРЕПА **до** unpin (важный порядок)
2. Также проверяет max ID из `GroupMessage` DB
3. Fallback: если ID неизвестен — диапазон 500
4. `unpin_all_chat_messages` — снимает закреп
5. **Удаляет сообщения по одному** (`delete_message`, не `delete_messages`) — пакет падает на сервисных сообщениях
6. Получает админов через `bot.get_chat_administrators` (не из UserInGroup — те могут отсутствовать)
7. **Демоутит** админов через `promote_chat_member` со всеми правами False (без demote нельзя кикнуть админа)
8. Кикает админов: ban + unban с `until_date=now+1`
9. Кикает обычных юзеров из `UserInGroup` (workers, employer)
10. Удаляет ВСЕ записи `UserInGroup` для группы
11. `set_default_permissions` — сбрасывает права группы
12. Удаляет записи `GroupMessage` из БД
13. **Warning о неучтённых юзерах**: если `telegram_count > admins+1` — лог warning (зашли мимо bot flow)

**Telegram limitations:**
- Создатель группы (`creator`) кикнуть нельзя — это владелец, ограничение Telegram API
- Бот не может ставить теги через `set_chat_member_tag` — нужны права creator
- Сообщения старше 48ч могут быть неудалимы (Telegram limit для не-bot сообщений)
- `delete_messages` (пакет) падает если в нём есть сервисное сообщение (msg_id=1 — создание группы)

### Тег «Працівник» для рабочих
- При входе рабочего в группу (`handle_user_status_change`, status=MEMBER, не owner) — `set_default_owner_permissions` (все права False) + `set_admin_custom_title("Працівник")`
- `set_chat_member_tag` НЕ работает — требует прав создателя группы
- Заказчик: тег «Роботодавець», админ: тег «Адміністратор», рабочий: тег «Працівник»

### Лишние invite-ссылки бота
- В группах накопились старые ссылки бота (созданные до того как `update_invite_link` стал no-op)
- Решение: владелец вручную **отключил `can_invite_users`** у бота во всех 11 группах через Telegram UI
- При отключении `can_invite_users` Telegram автоматически удаляет ВСЕ ссылки бота
- ВНИМАНИЕ: при отключении `can_invite_users` сбрасывается и `chat.invite_link` (primary link)
- Постоянные ссылки групп пришлось пересоздавать вручную владельцем
- БД (`Group.invite_link`) обновлена на новые ссылки

### Permissions cleanup
- 7 групп имели `can_invite_users=True`, `can_change_info=True`, `can_pin_messages=True`
- Все сброшены в False через `GroupService.set_default_permissions()`

### Подтверждено готовое
- **VacancyContactPhone**: модель, миграция, формы, хэндлеры — всё работает (71 запись в БД)
- **«Я ГОТОВИЙ ПРАЦЮВАТИ» flow**: callback проверки → deep link → `_process_apply_payload` → confirm message → phone → group invite — работает

### Изменённые файлы
- `telegram/service/group.py` — `get_available_group` (nulls_first), `reset_group` (полностью переписан), `set_member_tag` (добавлен но не используется — требует creator)
- `vacancy/services/observers/vacancy_close.py` — `VacancyKickGroupUsersObserver` использует `reset_group`
- `telegram/handlers/member/user/group.py` — добавлен `set_admin_custom_title("Працівник")` для рабочих

## Сессия 5 мая 2026 — фикс блокировок + PENDING_CONFIRM + инфраструктура

Код (4 коммита, все в develop+main):
- dfb2db8 fix(blocking): kick_user синхронизирует UserInGroup+VacancyUser→KICKED; auto_block_* без дубликатов; BlockService.unblock_user_all(user); кнопка «Розблокувати» снимает все блоки; UserBlockInline readonly (max 20); is_blocked проверка в 3 observer-ах
- 4cf912b fix(apply): ранний reject при переполнении (vacancy.members.count >= people_count); фикс flaky тестов (mock message_id); фикс test_dashboard_renamed (dashboard_bottom.html)
- 6631b71 feat(apply): статус PENDING_CONFIRM — юзер при apply становится PENDING_CONFIRM, переходит в MEMBER только после Підтвердити. Решает баг «Через 2 години» (PENDING не попадает в vacancy.members). Удалён мёртвый код joined_less_than_2h в call_observer.py. Проверка переполнения считает MEMBER+PENDING_CONFIRM. Таймаут подтверждения ищет PENDING_CONFIRM→LEFT
- ff9be9a test(apply): регрессионные тесты — PENDING_CONFIRM пропускается в before_start observer; MEMBER получает BEFORE_START call

Инфраструктура:
- .env был утерян, восстановлен из снимка ClaudeCode в /tmp/, исправлены POSTGRESQL_NAME=robochi_db и POSTGRESQL_USER=robochi_user
- Применены 13 миграций к боевой БД (отставали с конца апреля)
- Telegram-токен бота отозван Telegram (утёк в публичный GitHub через Git-историю). Получен новый токен через BotFather, webhook зарегистрирован
- Удалена старая БД robochi и роль coin в Postgres
- Очищены утечки секретов: /tmp/robochi_main/, /root/robochi_bot/, ~/.claude/projects/*.jsonl, /root/.bash_history
- Удалены старые .env-бэкапы (.env.before_fix, .env.before_token_*, .env.local)

Тесты: 214 зелёных

Технический долг (отдельная сессия):
- D: Ротация секретов (DJANGO_SECRET_KEY, POSTGRESQL_PASSWORD, TELEGRAM_WEBHOOK_SECRET, SENTRY_DSN, PROVIDER_TOKEN)
- E: pg_hba.conf trust→md5 (Postgres принимает любой пароль для localhost)
- F: Добавить migrate в деплой-процедуру (миграции отставали 6 недель)
- G: Сайт robochi.work — Internal Server Error при прямом входе

## Session 2026-05-07: User cleanup tasks

### What was done
1. **Task 1 — Unregistered users (7 days):** New Celery task `cleanup_unregistered_users_task` runs nightly at 03:30. Deletes users who pressed /start but never completed registration (no WorkProfile or is_completed=False) after 7 days. Full cascade delete.

2. **Task 2 — Unregistered user clicks vacancy:** Already implemented in `apply_vacancy.py` step 5 — shows "register first" message.

3. **Task 3 — Inactive workers (180 days):** Modified `cleanup_inactive_users_task` to fully delete (not deactivate) workers with no VacancyUser activity for 180 days. Falls back to date_joined if no activity.

4. **Task 4 — Deleted Telegram accounts:** Modified same task to fully delete users whose Telegram account no longer exists. Detection via `bot.get_chat()` — error or first_name="Deleted Account" means deleted. Rate limited at 50ms per check.

5. **Task 5 — Inactive employers (180 days):** Added employer check to same task. Uses Vacancy.date (not created_at) to determine last activity. Converts date to timezone-aware datetime for comparison.

### Files changed
- `user/tasks.py` — rewritten: two tasks, three helper functions
- `config/settings/celery.py` — added `cleanup_unregistered_users` schedule entry
- `work/management/commands/check_system.py` — added to REQUIRED_BEAT_TASKS
- `tests/test_user_cleanup.py` — 11 regression tests

### Schedule
- 03:00 — `cleanup_inactive_users` (tasks 3, 4, 5)
- 03:30 — `cleanup_unregistered_users` (task 1)

### Key decisions
- All cleanup = full `user.delete()` (cascade), not `is_active=False`
- Staff/superuser users are never deleted
- Employer activity measured by Vacancy.date, worker by VacancyUser.created_at
- Telegram deleted account check: 50ms delay between API calls (~20 req/sec)

## Сессия 07.05.2026

### Починено:
1. **REDIS_PASSWORD** — был утерян при пересоздании .env (ротация секретов). Celery не мог ставить задачи в очередь (`apply_async` падал с "invalid username-password pair"). Добавлен обратно.
2. **Сообщение заказчику после модерации** (ссылка на группу через `send_employer_group_invite_task`) — не работало из-за Redis.
3. **Закреп в группе вакансии** (`VacancyApprovedGroupObserver`) — работает, `sent_in_group=True`.
4. **Роли в группе вакансии** — title не ставился потому что `promote_chat_member` со всеми правами False не делает реального promote. Исправлено:
   - Рабочий: `can_manage_chat=True` (минимум для title) → title «Працівник»
   - Заказчик: `can_manage_chat=True` + `can_restrict_members=True` → title «Роботодавець»
   - Выбран **Вариант Б**: кик рабочего через бота/ЛК (не через Telegram UI, т.к. оба — админы)
   - **Вариант А** (без promote рабочего, кик через TG UI) — запасной
5. **before_start_call кикал рабочего** — перекличка "за 2 часа" отправлялась рабочим которые зашли менее 2ч до начала. Фикс: `check_before_start` в `call_observer.py` проверяет `join_confirm.created_at >= two_hours_before`.
6. **Массовые блокировки** — у тестового рабочего 201 запись `rollcall_reject`. Очищено вручную.

### Файлы изменены:
- `telegram/handlers/member/user/group.py` — логика ролей: owner→Роботодавець, staff→admin, else→Працівник
- `telegram/service/group.py` — два метода: `set_default_owner_permissions` (can_restrict+can_manage_chat) и `set_default_worker_permissions` (can_manage_chat only)
- `vacancy/services/observers/call_observer.py` — skip before_start для рабочих зашедших после 2h-before mark
- `tests/test_session_20260430.py` — обновлены тесты before_start (2 теста: recent joiner skipped, early joiner gets call)

### Коммиты:
- `fix: role assignment for worker/employer in vacancy group`
- `fix: separate permissions for employer and worker in vacancy group`
- `fix: skip 2h rollcall for workers who joined after the 2h-before mark`
- `test: update before_start tests for skip-recent-joiner logic`

## Обязательные переменные .env (чеклист)

При любых правках .env — сверить что ВСЕ ключи на месте:

- DJANGO_SECRET_KEY
- DJANGO_SETTINGS_MODULE
- BASE_URL (2 записи)
- HOST (2 записи)
- ADMIN_TELEGRAM_IDS
- TELEGRAM_BOT_TOKEN
- TELEGRAM_WEBHOOK_SECRET
- POSTGRESQL_HOST
- POSTGRESQL_PORT
- POSTGRESQL_NAME
- POSTGRESQL_USER
- POSTGRESQL_PASSWORD
- REDIS_PASSWORD
- PROVIDER_TOKEN
- SENTRY_DSN

## Стабильная конфигурация (не ломать)

### Роли в группе вакансии (Вариант Б)
- Рабочий: promote can_manage_chat=True → title «Працівник» (set_default_worker_permissions)
- Заказчик: promote can_manage_chat=True + can_restrict_members=True → title «Роботодавець» (set_default_owner_permissions)
- Кик рабочего: ТОЛЬКО через бота/ЛК (оба юзера — админы, Telegram не даёт админу кикнуть админа)
- Вариант А (без promote рабочего, кик через TG UI) — запасной
- **Member tags (Bot API 9.4+):** `telegram/service/group.py` — `set_member_tag()` at line ~219 using `bot.set_chat_member_tag()`. Called from `telegram/handlers/member/user/group.py` on join/status-change. Requires `can_manage_tags=True` — must be granted manually in group admin settings.

### Перекличка before_start
- check_before_start() пропускает рабочих с join_confirm после (start_time - 2h)
- check_before_20_start() кикает + блокирует через 20 мин без ответа

### Invite links
- Бот НИКОГДА не создаёт invite-ссылки
- can_invite_users=False во всех группах
- Ссылки только через Django admin

### Деплой
- set -a; source .env; set +a
- python3 manage.py collectstatic --clear --noinput && sudo systemctl restart gunicorn.service
- Celery: sudo systemctl restart celery-worker.service celery-beat.service
- Celery ОБЯЗАТЕЛЬНО перезапускать при изменениях в tasks/ и observers/

### Тесты
- DJANGO_SETTINGS_MODULE=config.django.test (SQLite)
- pytest tests/ -x --timeout=60
- Все тесты должны проходить перед push

### Session 2026-05-07 (update 2): check_telegram_deleted improvements

- Fixed: empty first_name was not caught as deleted account (user 7373456897 case)
- Fixed: cleanup_inactive_users_task now checks ALL users (including is_active=False), not just active
- Removed send_chat_action from check_telegram_deleted to reduce API calls (1 call per user instead of 2)
- Detection logic: get_chat → empty/missing first_name OR name contains 'deleted' OR API error = deleted
- 15 regression tests in test_user_cleanup.py (was 11, added 4 for check_telegram_deleted)

### Session 2026-05-09: Rollcall overhaul + continue search

**Переклички заказчика — полная переработка:**

1. **Тексты и кнопки** — все сообщения и кнопки перекличек на украинском. Новый формат: «Початок роботи за вакансією- / Адреса: ... / Проведіть перекличку — натисніть кнопку нижче.»

2. **3 сценария первой переклички (pre_call):**
   - Сценарий А (0 рабочих): «Продовжити пошук» + «Закрити вакансію»
   - Сценарий Б (рабочие есть, мало): чекбоксы + «Підтвердити явку» + «Продовжити пошук»
   - Сценарий В (достаточно): обычная перекличка с чекбоксами
   - Логика в `vacancy_pre_call_check()` в views.py

3. **«Продовжити пошук» = быстрое возобновление без модерации:**
   - Новый view `vacancy_continue_search` (URL: `/<pk>/continue-search/`)
   - Автоматически сдвигает start_time на текущее+1ч (rounded to 15min)
   - Обеспечивает минимум 3ч рабочего времени (end_time сдвигается если нужно)
   - Перепубликует вакансию в канале с кнопкой
   - Группа остаётся та же, рабочие на месте
   - 4 кнопки ведут к одному действию: «Продовжити пошук» (pre_call), «Поновити пошук» (vacancy_detail), кнопки в боте

4. **Автоподтверждение при игнорировании (12 напоминаний = 60мин):**
   - 0 рабочих → автозакрытие вакансии
   - Есть рабочие → автоподтверждение всех + сообщение заказчику
   - Код в `_escalate_rollcall()` в tasks/call.py

5. **Сообщения в бот заказчику:** при прохождении переклички, автоподтверждении, закрытии

6. **Сообщения админу:** блок данных пользователя (ID, Ім'я, Username, Телефон) в _escalate_rollcall

7. **Уведомление при добавлении нового рабочего:** в `VacancyIsFullObserver` (member_observer.py) — если first_rollcall_passed, шлёт заказчику «Новий працівник доданий»

8. **Блокировка создания вакансии** во время непройденной переклички (has_pending_rollcall в index.py → disabled кнопка в employer_dashboard)

**Баг-фиксы:**

9. **Ночные смены:** `_get_end_aware()` / `_get_start_aware()` в tasks/call.py — если end_time < start_time, +1 день. Заменены все datetime.combine в tasks/call.py

10. **Валидация времени при resume:** `VacancyForm.resume_mode` пропускает проверку «не раніше ніж через 1 годину»

11. **before_start_call для подтверждённых:** пропускает рабочих с CallType.START + CONFIRM (call_observer.py)

12. **Channel handler ghost records:** `channel.py` фильтровал `["channel", "supergroup"]` → группы вакансий создавали записи в Channel. Исправлено: только `["channel"]`

13. **Авто-обновление страниц:** JSON endpoint `/vacancy/<pk>/members-json/` + JS polling 15с на pre_call, call, vacancy_detail

**Файлы изменены:** vacancy/views.py, vacancy/tasks/call.py, vacancy/forms.py, vacancy/urls.py, vacancy/services/call_formatter.py, vacancy/services/call_markup.py, vacancy/services/observers/call_observer.py, vacancy/services/observers/member_observer.py, vacancy/services/observers/approved_user_observer.py, telegram/handlers/member/bot/channel.py, work/views/index.py, work/templates/work/employer_dashboard.html, vacancy/templates/vacancy/pre_call.html, vacancy/templates/vacancy/call.html, vacancy/templates/vacancy/vacancy_detail.html

**Тесты:** tests/test_rollcall_session_20260509.py — 9 тестов (overnight shift, 3 scenarios, continue search, skip before_start, block creation, resume mode)

### Session 2026-05-12: Second rollcall rework + admin notifications + form fixes

**Задача 1 — 2-я перекличка (кінець роботи) переработана:**

1. **Снятие галочек — новая логика:**
   - Любое снятие чекбоксов (все или часть) → заказчик НЕ кикается из группы
   - Заказчик блокируется временно (BlockReason.EMPLOYER_ROLLCALL_FAIL)
   - Сообщение в бот: «Друга перекличка не пройдена— Вас заблоковано!»
   - second_rollcall_passed НЕ ставится в True — напоминания продолжают приходить
   - Рабочие с снятыми галочками — блокируются как раньше (EMPLOYER_UNCHECK)

2. **Повторное прохождение:**
   - Заказчик заходит на страницу 2-й переклички → видит ВСЕХ тех же рабочих с галочками
   - При подтверждении (хоть один отмечен) → блокировка снимается, second_rollcall_passed=True, переход к оплате
   - Админ может пройти перекличку вместо заказчика через is_staff проверку

3. **Чекбоксы по умолчанию:**
   - При первом заходе на любую перекличку (1-ю и 2-ю) все чекбоксы отмечены
   - При повторном заходе на 2-ю перекличку — тоже все отмечены (свежий старт)

4. **Новые сущности:**
   - BlockReason.EMPLOYER_ROLLCALL_FAIL в user/choices.py
   - BlockService.auto_block_employer_rollcall_fail() / unblock_employer_rollcall_fail() в user/services.py
   - Миграция user/0019_add_employer_rollcall_fail_reason.py

5. **Код:** vacancy/views.py (vacancy_check_call — is_repeat_after_start детекция, блокировка/разблокировка)

**Задача 2 — Ночные смены в форме вакансии:**

6. **Labels date_choice:** для ночных смен (end_time < start_time) показывает «Сьогодні (ніч DD→DD.MM)» / «Завтра (ніч DD→DD.MM)»
7. **Утренняя проверка:** если до 12:00 и ночная смена — автосмена на «Завтра» (текущая ночь прошла)
8. **JS обновление:** при смене start_time/end_time labels обновляются в реальном времени
9. **Код:** vacancy/forms.py (__init__), vacancy/templates/vacancy/vacancy_form.html (JS)

**Задача 4 — Блок данных заказчика в сообщениях админу:**

10. **Новые методы форматирования:**
    - admin_start_call_fail_detailed() — 1-я перекличка с данными заказчика (ID, Ім'я, Username, Телефон)
    - admin_after_start_call_fail_detailed() — 2-я перекличка с данными заказчика
    - admin_call_fail() — обновлён, добавлен блок данных заказчика
11. **Кнопка для админа:** get_admin_check_rollcall_markup(vacancy, call_type) — WebApp кнопка «Перевірити перекличку»
12. **Обновлены observers:** VacancyStartCallFailObserver и VacancyAfterStartCallFailObserver используют новые методы + parse_mode="HTML" + кнопка
13. **all_unchecked блок:** в vacancy_check_call для обоих типов переклички — HTML формат + данные заказчика

**Задача 5 — Обновление страниц в реальном времени:**

14. **Убраны дубли скриптов:** polling JS был вставлен дважды на pre_call.html и call.html — оставлен один
15. **call.html:** добавлено обновление чекбоксов — при появлении нового рабочего страница перезагружается

**Задача 6 — Кнопка переклички после continue_search:**

16. **rollcall_time_reached:** теперь проверяет vacancy.extra['sent_start_call'] — если перекличка уже отправлена, кнопка активна независимо от текущего start_time

**Тесты:** tests/test_second_rollcall.py — 6 тестов (all confirmed, partial uncheck blocks, all unchecked no kick, repeat unblocks, default checkboxes, repeat checkboxes)

### Telegram Bot API 9.4-10.0 features (May 2026 session)

1. **Button styles applied:** Added `style="constructive"` to the phone sharing button ("Надіслати номер телефону") in `telegram/handlers/messages/commands.py` line ~74, and to the "Перейти" cabinet button in the same file line ~261. The `channel_vacancy_reply_markup` in `service/telegram_markup_factory.py` already had `style="danger"`, and `group_url_feedback_reply_markup` / `group_webapp_feedback_reply_markup` already had `style="primary"`.

2. **Member tags implemented:** Added `GroupService.set_member_tag()` calls in `telegram/handlers/member/user/group.py` at all 4 entry points — auto_approve (employer → "Роботодавець"), handle_user_status_change (admin → "Адміністратор", employer → "Роботодавець", worker → "Працівник"). The method `set_member_tag` was already defined in `telegram/service/group.py` (line ~219) using `bot.set_chat_member_tag()` but was never called. Bot requires `can_manage_tags=True` permission in each group — must be set manually in group admin settings.

3. **Home screen shortcut:** Already available via Telegram's native 3-dot menu in the bot chat. No custom button needed in the WebApp. BotFather Main Mini App is already configured.

4. **pyTelegramBotAPI version:** 4.32.0 — supports Bot API 9.4+ features including `style` on buttons, `setChatMemberTag`, `can_manage_tags` in `promoteChatMember`, `can_edit_tag` in `ChatPermissions`.

### Bot API 9.4-10.0 integration (May 18, 2026 session)

- `style="constructive"` added to phone button and cabinet "Перейти" button in `commands.py`
- `GroupService.set_member_tag()` calls added in `telegram/handlers/member/user/group.py` at all 4 entry points (auto_approve employer, handle_user_status_change admin/employer/worker). Method existed in `GroupService` but was never called.
- Bot requires `can_manage_tags=True` in each vacancy group (manual setting via group admin panel)
- Home screen shortcut: works natively via Telegram 3-dot menu, no custom WebApp button needed
- pyTelegramBotAPI 4.32.0 confirmed compatible with Bot API 9.4-10.0 (style, setChatMemberTag, can_manage_tags, can_edit_tag)
- 8 regression tests in `tests/test_session_20260518.py`

## Сессия 18.05.2026 — Об'єднання «Відгуки» + «Додавання/Видалення працівників» в одну функцію «Відгуки/Контакти»

### Що зроблено:
1. Кнопка в карточці вакансії ЛК заказчика перейменована: «Додавання/Видалення працівників» → «Додавання/Видалення працівників. Відгуки/Контакти».
2. Сторінка vacancy_members перероблена: телефон з VacancyContactPhone.phone (не user.phone_number); картка owner виключена для non-staff; додана кнопка «Відгуки» в кожну картку → модалка з «Залишити відгук» / «Подивитися відгуки»; гілка «Повернути до групи» прибрана повністю.
3. Кнопка в закріпі групи вакансії перейменована з «Надіслати відгук» на «Відгуки/Контакти», тепер відкривається ПРЯМО як WebApp (без deep-link через бота).
4. Новий view vacancy_feedback_redirect (URL feedback-entry) розводить роутинг за роллю: worker → work:worker_my_work; employer або admin → vacancy:members.
5. Видалено мертвий код: vacancy_reinvite_worker view + URL, обробник type=feedback у process_start_payload, тест test_reinvite_worker_unblocks_and_sends_message.

### Файли змінені:
- `vacancy/templates/vacancy/vacancy_detail.html` — перейменування кнопки
- `vacancy/templates/vacancy/vacancy_members.html` — телефон з VacancyContactPhone, модалка «Відгуки», прибрана кнопка reinvite
- `vacancy/views.py` — vacancy_members виключає owner для non-staff; додано vacancy_feedback_redirect; видалено vacancy_reinvite_worker
- `vacancy/urls.py` — додано feedback-entry; видалено reinvite_worker
- `service/telegram_markup_factory.py` — group_url_feedback_reply_markup переписана на WebApp button + новий URL; перейменована
- `telegram/handlers/messages/commands.py` — видалено type=feedback з process_start_payload
- `tests/test_blocking_regression.py` — видалено test_reinvite_worker_unblocks_and_sends_message
- `tests/test_session_20260518.py` — оновлено test_group_url_feedback_markup_uses_primary_style під WebApp
- `tests/test_feedback_contacts_merge.py` — новий регресійний тест

### Архітектурні рішення:
- Кнопка в закріпі групи тепер прямий WebApp (style=primary) на новий entry-point view, який сам редиректить за роллю. Це дозволило прибрати проміжне повідомлення від бота з кнопкою 'Open' і прибрати deep-link обробник.
- Картка заказчика на vacancy_members показується тільки адміну. Для самого заказчика — список тільки рабочих.
- «Повернути до групи» прибрана повністю. Кікнутий рабочий автоматично розблоковується (kick_user робить unban в finally блоці) і може повторно натиснути «Я готовий працювати» з каналу міста.

## Сесія 19.05.2026 — Унікальний порядок відображення міст (City.order unique)

### Що зроблено:
- `City.order` (`PositiveIntegerField`) отримав `unique=True` та `verbose_name=_("Порядок")` (раніше — звичайний рядковий рядок без перекладу і без унікальності).
- Міграція `city/migrations/0006_alter_city_order.py` застосована.

### Поточний стан моделі:
```python
order = models.PositiveIntegerField(default=0, verbose_name=_("Порядок"), unique=True)

class Meta:
    ordering = ["order", "pk"]
```

### Патерн:
- Повторює підхід `FaqItem.order` (також `unique=True`, `list_editable` в адміні).
- `CityAdmin` використовує `list_editable = ["order"]` для inline-редагування порядку безпосередньо зі списку.

## Сесія 19.05.2026 — Session fix + Lifecycle v7

### Проблема 1: Розлогінювання адмінки
- **Причина:** production.py мав SameSite="None" (браузери видаляють як трекінгове) і SESSION_COOKIE_AGE=86400 (24г замість 2 тижнів)
- **Виправлено:** SameSite="Lax", AGE=1209600 (2 тижні), SESSION_SAVE_EVERY_REQUEST=True, CSRF_COOKIE_HTTPONLY=False
- **Файл:** config/django/production.py

### Проблема 2: Зависання міні-застосунку після згортання
- **Причина:** lifecycle.js v6 робив reload() одразу — мережа ще не прокинулась → ERR_CONNECTION_ABORTED
- **Виправлено:** lifecycle.js v7 — спочатку ping (fetch HEAD), потім reload. Overlay "Завантаження..." замість напівпрозорості. 6 спроб. Додані focus/pageshow події
- **Файл:** telegram/static/js/lifecycle.js

### Видалений мертвий код
- telegram.js: блок alpine:init + getCookie (Alpine.js не підключена, getCookie не визначена)

### Тести
- tests/test_session_20260519_lifecycle.py — 11 тестів

## Удаление иконок из мини-приложения (19.05.2026)

Из 15 HTML-шаблонов мини-приложения (WebApp) удалены все декоративные emoji-иконки.
Иконки в сообщениях бота, админ-панели Django и системных отчётах НЕ затронуты.

Затронутые файлы:
- work/templates/work/: worker_dashboard.html, employer_dashboard.html, admin_dashboard.html, employer_cities.html, admin_search_results.html, employer_reviews.html, worker_my_work.html
- vacancy/templates/vacancy/: vacancy_detail.html, vacancy_my_list.html, vacancy_payment.html, vacancy_members.html, vacancy_feedback.html, vacancy_user_reviews.html, pre_call.html, vacancy_form.html

Символ ✕ (кнопка закрытия модалок) оставлен — это функциональный элемент, не декоративная иконка.

## Удаление іконок з міні-додатку (19.05.2026)

З 16 HTML-шаблонів міні-додатку (WebApp) видалено всі декоративні emoji-іконки.
Іконки в повідомленнях бота, адмін-панелі Django та системних звітах НЕ змінювались.
Символ ✕ (кнопка закриття модалок) залишено.
Регресійний тест: tests/test_session_20260519_no_emojis.py (16 файлів).

## Сесія 19.05.2026 — Модерація вакансій з ЛК Адміністратора

### Проблема:
Фільтр «На модерації» в ЛК Адміністратора (вкладка Вакансії) показував список заказчиків з вакансіями на модерації, але натиснувши на вакансію зі статусом "pending" — відкривалась сторінка деталей (vacancy_detail), де всі кнопки управління були заховані для pending-статусу. Модерація з ЛК була неможлива — лише через повідомлення бота в Телеграмі.

### Рішення:
В шаблоні `vacancy/templates/vacancy/vacancy_my_list.html` (рядок 50) — для адмін-перегляду (`is_admin_view`) вакансії зі статусом `pending` картка тепер веде на форму модерації (`work:admin_moderate_vacancy`), а не на сторінку деталей. Для інших статусів та для самого заказчика — все працює як раніше.

### Повний шлях модерації з ЛК:
Фільтр «На модерації» → ПОШУК → картка заказчика → «Карта вакансій» → натиснути вакансію «Очікує модерації» → **форма модерації** (редагування + підтвердження).

### Файли змінені:
- `vacancy/templates/vacancy/vacancy_my_list.html` — умовна ссилка: pending + is_admin_view → admin_moderate_vacancy; інакше → vacancy:detail
- `tests/test_session_20260519_moderation.py` — 3 регресійні тести (admin бачить ссилку на модерацію для pending; admin бачить detail для approved; employer завжди бачить detail)

## Сесія 26.05.2026 — Критичні баги ЖЦВ + закріп у групі

### 3 критичні баги ЖЦВ виправлено:

1. **Рабочий блокувався після підтвердження переклички «за 2 години».**
   Причина: `callback/call.py` рядок 193 — `update_or_create` шукав запис тільки по `vacancy_user` (без `call_type`). Якщо у рабочого 2 записи (WORKER_JOIN_CONFIRM + BEFORE_START), Django кидав `MultipleObjectsReturned`, підтвердження не зберігалось, `check_before_20_start` бачив статус SENT → кік + блок.
   Виправлення: додано `call_type=data["call_type"]` в lookup `update_or_create`.

2. **Вакансія закривалась через ~3 години після початку роботи.**
   Причина: `close_lifecycle_timer_task` (Case b) закривав будь-яку вакансію в статусі SEARCH_STOPPED через 3 години після `search_stopped_at`, не перевіряючи чи є рабочі і чи йде ЖЦВ.
   Виправлення: додана перевірка `vacancy.members.exists()` + `payment_checked` — вакансії з рабочими і незавершеним ЖЦВ пропускаються.

3. **Ланцюжок обробників ламався при помилці одного.**
   Причина: `BasePublisher.notify()` не мав `try/except` — якщо observer кидав виняток, наступні не виконувались (наприклад, помилка каналу → закріп у групі не відправлявся).
   Виправлення: кожен `observer.update()` обгорнутий в `try/except` з `logging.warning`.

### Закріплене повідомлення в групі виправлено:

4. **Прапорець `sent_in_group` ставився навіть при невдалій відправці.**
   Причина: `approved_group_observer.py` — `vacancy.extra["sent_in_group"] = True` був за межами `try` блоку.
   Виправлення: переміщено всередину `try`, після успішного `pin_chat_message`.

5. **Кнопка `web_app=WebAppInfo()` не працює в групах — обмеження Telegram Bot API.**
   Документація: «Available only in private chats between a user and the bot.»
   Рішення: кнопка замінена на `url="https://t.me/riznorobochi_ua_bot?startapp=fb_{vacancy.pk}"`.
   Telegram відкриває Main App (check-web-app/) з параметром `start_param`.

6. **Роутинг через `check.html` для кнопки з групи.**
   `check.html` тепер читає `Telegram.WebApp.initDataUnsafe.start_param` (або GET `tgWebAppStartParam`).
   Якщо `start_param` починається з `fb_` → `next=/vacancy/ID/feedback-entry/` → view визначає роль → worker → "Моя робота", employer/admin → "Учасники".
   Кнопка "ПОЧАТИ" (Menu Button) працює як раніше — без start_param → redirect на `/`.

7. **Кнопка «Повернутися в групу» додана на сторінку vacancy_members** для заказчика/адміна.
   У рабочого кнопка «Група моєї роботи» вже була на сторінці worker_my_work.

### Важливе архітектурне рішення:
- **`web_app=WebAppInfo()` на InlineKeyboardButton НЕ працює в групах** (Telegram API обмеження, станом на Bot API 10.0).
- Альтернатива: `url="https://t.me/BOT?startapp=PARAM"` — відкриває Main Mini App з параметром, повна авторизація через initData.
- Це стосується ВСІХ кнопок в групових повідомленнях — завжди використовувати `url=` з startapp, НЕ `web_app=`.

### Файли змінені:
- `telegram/handlers/callback/call.py` — call_type в update_or_create
- `vacancy/tasks/call.py` — skip close для вакансій з рабочими
- `vacancy/services/observers/publisher.py` — try/except в notify
- `vacancy/services/observers/approved_group_observer.py` — sent_in_group всередині try
- `service/telegram_markup_factory.py` — кнопка url= startapp замість web_app=
- `telegram/templates/telegram/check.html` — обробка start_param
- `vacancy/templates/vacancy/vacancy_members.html` — кнопка «Повернутися в групу»
- `tests/test_session_20260526.py` — 12 регресійних тестів
- `tests/test_feedback_contacts_merge.py` — оновлені тести кнопки

## Сесія 27.05.2026

### Виконані задачі (8 пунктів):

1. **Обнулення груп** — `reset_group` доповнено кроком 10: повторна перевірка та кік адмінів що залишились після основного скидання. `until_date` збільшено з +1с до +35с для надійного кіку. Вручну почищена група -1002882819252.

2. **Перекличка робочих за 2 год** — таймаут змінено з 20 хв на 5 хв з нагадуваннями кожну хвилину (аналогічно `worker_join_confirm_check_task`). Метод перейменовано `check_before_20_start` → `check_before_5_start`.

3. **Сторінка Учасники (vacancy_members.html)** — кнопка «Повернутися в групу» переміщена вище в стилі `btn-secondary`. Прибрано слово «Участник». Кнопка «Відгуки» → «Рейтинг/Відгуки» в стилі `btn-secondary btn-block`. Карточка: кнопка зверху, дані посередині, «Видалити з групи» знизу.

4. **Закриття вакансії з оплатою (close_lifecycle)** — якщо після 1-ї переклички є робочі в групі, при натисканні «Закрити вакансію» виставляється рахунок (статус `AWAITING_PAYMENT`), замовник блокується до оплати. Без робочих — закривається як раніше.

5. **Кнопка оплати в блокуванні** — додано кнопку «Сплатити рахунок» під текстом блокування на employer_dashboard, веде на «Поточні вакансії». Текст: «Сплатіть рахунок».

6. **Підрахунок вакансій** — кнопка «Поточні вакансії» тепер рахує всі статуси (pending, approved, active, stopped, awaiting, paid, closed за 3г) замість тільки active/approved.

7. **Автоперехід після переклички** — `call_confirm.html` автоматично перенаправляє на сторінку вакансії через 2 секунди. Додано `vacancy` в контекст view.

8. **Редизайн 2-ї переклички** — `call.html` повністю переписано в стилі `pre_call.html`. Прибрано посилання «Повернутися до першої переклички» та старі кнопки «Меню».

### Додатково:
- **Перейменування**: «Оплатити рахунок» → «Сплатити рахунок» всюди (vacancy_detail.html, vacancy_payment.html)
- **Кнопка «Подивитися контакти»** прибрана з модалки vacancy_user_list.html
- **CSS статуси** в vacancy_my_list.html: додані стилі для stopped, awaiting (червоний #dc3545), closed, paid
- **Фікс тестів**: test_retry_reload_in_lifecycle (MAX_RETRIES→pingAndReload), test_group_url_feedback_markup (style→url startapp)

### Файли змінені:
- `vacancy/views.py` — close_lifecycle з оплатою, vacancy в call_confirm контексті
- `vacancy/services/observers/call_observer.py` — check_before_5_start з нагадуваннями
- `telegram/service/group.py` — reset_group крок 10, until_date +35с
- `work/views/index.py` — active_vacancies_count всі статуси
- `vacancy/templates/vacancy/call.html` — повний редизайн
- `vacancy/templates/vacancy/call_confirm.html` — автоперехід
- `vacancy/templates/vacancy/vacancy_members.html` — новий layout
- `vacancy/templates/vacancy/vacancy_detail.html` — Сплатити рахунок
- `vacancy/templates/vacancy/vacancy_payment.html` — Сплатити рахунок
- `vacancy/templates/vacancy/vacancy_my_list.html` — CSS статуси
- `vacancy/templates/vacancy/vacancy_user_list.html` — прибрано контакти
- `work/templates/work/employer_dashboard.html` — кнопка оплати в блокуванні
- `tests/test_session_20260527.py` — 16 тестів (10 функціональних + 6 регресійних)

## Сесія 27.05.2026 (частина 2) — Фікс рахунку + засчитування оплати адміном

### Баг: «0 працівників» у рахунку після автопідтвердження переклички

**Проблема:** Коли замовник ігнорує 2-гу перекличку і система автоматично підтверджує (`_escalate_rollcall`), список робочих НЕ записувався в `vacancy.extra["calls"]["after_start"]`. Рахунок формується з цих даних (`invoice.py` рядок 25), тому показував 0 працівників і 0 грн.

**Причина:** `_escalate_rollcall` у `vacancy/tasks/call.py` створювала `VacancyUserCall` записи і ставила прапорці `first/second_rollcall_passed`, але пропускала запис у `extra["calls"]`. Ручна перекличка через форму (`views.py` рядок 179) цей запис робила.

**Виправлення:** Додано запис `extra["calls"][ct] = list(members.values_list("user_id", flat=True))` в обидві гілки (1-а і 2-а перекличка) функції `_escalate_rollcall`.

### Засчитування оплати адміністратором

**Проблема:** Адмін міг розблокувати замовника в ЛК, але вакансія залишалась у статусі «Очікує оплати», `is_paid=False`, група не звільнялась. Єдиний шлях — Django shell.

**Рішення:** Створено спільну функцію `admin_mark_vacancies_paid(user, admin_user)` в `user/services.py`, яку використовують обидва шляхи:

1. **ЛК Адміністратора** — при натисканні «Розблокувати» на замовнику з блокуванням за неоплату система автоматично викликає `admin_mark_vacancies_paid`
2. **Django-адмінка** — нове дію «Зарахувати оплату (адмін)» у списку вакансій

**Функція `admin_mark_vacancies_paid` виконує:**
- Знаходить всі вакансії зі статусом `AWAITING_PAYMENT`
- Ставить `is_paid=True`, `admin_marked_paid=True`, статус `PAID`
- Знімає блокування за неоплату (`reason=unpaid`)
- Видаляє повідомлення з рахунком у боті
- Надсилає замовнику «Оплату зараховано адміністратором»
- Логує дію з `admin_id` та `vacancy_id`

### Файли змінені:
- `vacancy/tasks/call.py` — `_escalate_rollcall` записує `extra["calls"]`
- `user/services.py` — нова функція `admin_mark_vacancies_paid`
- `work/views/admin_panel.py` — розблокування з засчитуванням оплати
- `vacancy/admin.py` — дію «Зарахувати оплату (адмін)»
- `tests/test_session_20260527_invoice_fix.py` — 4 тести

## Сесія 29.05.2026 — Завислі вакансії + фікс CI

### Два баги завислих вакансій:

**Баг 1: Після автопідтвердження 2-ї переклички (ігнор замовника) не виставлявся рахунок.**
Вакансія залишалась в `stopped` назавжди. `close_lifecycle_timer_task` бачив робочих і `payment_checked=False` → пропускав.
**Фікс:** `_escalate_rollcall` після автопідтвердження 2-ї переклички тепер автоматично переводить вакансію в `awaiting_payment` і викликає `send_vacancy_invoice`.

**Баг 2: Вакансії оплачені адміном не звільняли групу.**
`close_lifecycle_timer_task` шукав тільки `MonobankPayment` записи. Якщо оплата зарахована адміном — запису немає → група висить назавжди.
**Фікс:** Case c тепер перевіряє `admin_marked_paid` і звільняє групу через 3г після `search_stopped_at`.

**Баг 3: Кнопка «Сплатити рахунок» показувалась для оплачених вакансій.**
`show_payment` перевіряв тільки `extra["is_paid"]`, не статус. Якщо `is_paid=None` але статус `paid` — кнопка залишалась.
**Фікс:** додано `vacancy.status != STATUS_PAID` в умову `show_payment`.

### Фікс CI тесту:
`test_phone_button_has_constructive_style` — `KeyboardButton(style=)` не підтримується старішою версією pyTelegramBotAPI в CI. Замінено на `try/except` з `pytest.skip`.

### Статуси вакансій (довідка):
- `pending` — Очікує модерації
- `approved` — Активна (пошук)
- `stopped` — Пошук зупинено (група привʼязана, переклички йдуть)
- `closed` — Закрита (через 3г група звільняється)
- `awaiting` — Очікує оплати (замовник заблокований)
- `paid` — Сплачено (через 3г група звільняється)
- `rejected` — Скасована модератором
- `active` — ВИДАЛЕНО 29.05.2026 (був мертвий код, ніколи не ставився)
- `created` — тільки для імені події `VACANCY_CREATED`, не статус БД

### На горизонті (додано):
- ✅ ВИКОНАНО 29.05.2026: `STATUS_ACTIVE` повністю видалено з 16 файлів (~48 правок). Всі фільтри `status__in=[APPROVED, ACTIVE]` замінено на `status=APPROVED`. В admin_panel.py фільтр «до сплати» — `ACTIVE` замінено на `AWAITING_PAYMENT`. Константа видалена з choices.py. Тест: test_session_20260529_status_active.py (7 тестів).

### Файли змінені:
- `vacancy/tasks/call.py` — `_escalate_rollcall` виставляє рахунок + `close_lifecycle_timer_task` Case c для admin-paid
- `vacancy/views.py` — `show_payment` перевіряє `STATUS_PAID`
- `tests/test_session_20260518.py` — фікс CI тесту style param

## История изменений

### 2026-05-30 — Apply button (Я ГОТОВИЙ ПРАЦЮВАТИ) message routing fix

Проблема: после нажатия «Я ГОТОВИЙ ПРАЦЮВАТИ» в канале заказчик/админ
попадали в бота, но получали стандартное приветствие "Вітаємо у нашому
сервісі!" вместо нужного сообщения.

Корневая причина: в `_send_cabinet_message` и `_send_employer_cabinet_message`
у `InlineKeyboardButton` был параметр `style="constructive"` — Telegram Bot API
такого параметра не поддерживает и возвращает 400 Bad Request:
"can't parse inline keyboard button: invalid button style specified".
Исключение проглатывалось в `process_start_payload`
(`except Exception: return False`), поэтому payload терялся и шёл
`default_start`.

Исправлено в `telegram/handlers/messages/commands.py`:
1. Убран невалидный `style="constructive"` из InlineKeyboardButton (2 места).
2. Добавлена функция `_send_admin_invite_message(message, vacancy_id)` —
   шлёт админу ссылку на группу вакансии с текстом
   «Перейдіть у групу даної вакансії за посиланням нижче:» и кнопкой
   «Перейти в групу вакансії».
3. Обработчик `type=admin_apply` теперь вызывает `_send_admin_invite_message`
   вместо `_send_cabinet_message`.

Поведение трёх сценариев нажатия «Я ГОТОВИЙ ПРАЦЮВАТИ»:
- Рабочий (уже в этой вакансии) → текст «...тут ви зможете обрати роботу...»
  + кнопка «Перейти» (WebApp/ЛК)
- Заказчик (свою вакансию) → текст «...тут ви зможете керувати вакансією...»
  + кнопка «Перейти» (WebApp/ЛК)
- Админ → текст «Перейдіть у групу даної вакансії за посиланням нижче:»
  + кнопка «Перейти в групу вакансії» (invite_link)

Регрессионный тест: `tests/test_session_20260530_apply_button_messages.py`
(4 теста). Ключевой защитный тест —
`test_no_invalid_button_style_in_inline_buttons` — проверяет что
`style="constructive"` отсутствует в исходниках трёх функций.

Важное правило на будущее: `InlineKeyboardButton` в pyTelegramBotAPI НЕ
поддерживает `style="..."`. Этот параметр существует только в
`ReplyKeyboardMarkup`. При добавлении кнопок всегда проверять через
минимальный smoke-тест.

## Сесія 31.05.2026 — Session fix + Lifecycle v8

### Проблема 1: Розлогінювання адмінки
- Причина: production.py мав SameSite="None" + SESSION_COOKIE_AGE=86400
- Виправлено: SameSite="Lax", AGE=1209600, SESSION_SAVE_EVERY_REQUEST=True, CSRF_COOKIE_HTTPONLY=False
- Файл: config/django/production.py

### Проблема 2: Зависання міні-додатку після згортання
- Причина: Android WebView заморожує JS при згортанні, events (visibilitychange, focus) можуть не спрацювати
- lifecycle.js v8: touchstart detection (capture:true) — найнадійніший сигнал, спрацьовує ЗАВЖДИ коли користувач торкається екрану. Ping (fetch HEAD) перед reload. Overlay "Завантаження...". Не залежить від Telegram SDK
- Файл: telegram/static/js/lifecycle.js

### Видалено мертвий код
- telegram.js: блок alpine:init + getCookie (Alpine.js не підключена, getCookie не визначена)

### Тести
- tests/test_session_20260519_lifecycle.py — 13 тестів

## Сессия 31.05.2026: Объединение страницы Учасники + Перекличка

### Что сделано
- **Объединение страниц**: Страница «Учасники» (`vacancy_members.html`) теперь совмещает управление участниками и переклички. Отдельная кнопка «Перекличка» убрана из карточки вакансии (`vacancy_detail.html`).
- **Три режима страницы Учасники**:
  1. До начала работы — карточки рабочих + кнопка «Видалити з групи»
  2. 1-я перекличка (Початок роботи) — чекбоксы + «Підтвердити» (фиксирована внизу) + сценарії А/Б/В
  3. 2-я перекличка (Кінець роботи) — чекбоксы + «Підтвердити»
- **Кнопка «Повернутися в групу»** перенесена выше заголовка «Учасники»
- **URL бота**: `call_markup.py` теперь отправляет ссылку на `vacancy:members` вместо `vacancy:pre_call`
- **Редирект**: `vacancy_pre_call_check` редиректит на `vacancy:members`
- **Проверка owner убрана** из `vacancy_members` (как в оригинальных pre_call/call)
- **`is_end_rollcall`** проверяет `sent_final_call` — 2-я перекличка показывается только после уведомления Celery
- **`vacancy_continue_search`**: сбрасывает все флаги переклички (`first/second_rollcall_passed`, extra-ключи) + удаляет старые `VacancyUserCall` записи для чистого нового цикла
- **Удаление auto-confirm блока**: при «Продовжити пошук» первая перекличка НЕ автоподтверждается, вместо этого весь цикл запускается заново
- **Удаление сообщений переклички при закрытии**: `start_call_msg_id` и `final_call_msg_id` добавлены в `VacancyDeleteEmployerInviteObserver`
- **Модерация**: `admin_moderate_vacancy` использует `resume_mode=True` чтобы не требовать сдвиг времени

### Ключевые файлы
- `vacancy/views.py` — `vacancy_members` (основной view), `vacancy_continue_search` (сброс флагов), `vacancy_pre_call_check` (редирект)
- `vacancy/templates/vacancy/vacancy_members.html` — объединённый шаблон
- `vacancy/templates/vacancy/vacancy_detail.html` — убраны кнопки переклички
- `vacancy/services/call_markup.py` — URL бота → members
- `vacancy/services/observers/vacancy_close.py` — удаление сообщений переклички
- `work/views/admin_panel.py` — resume_mode для модерации
- `tests/test_session_20260531_members_rollcall.py` — 10 тестов

### Баги найдены и исправлены
- `search_active=False` при `status=approved` — observer не включал поиск после модерации (данные, не код)
- Статус `awaiting_payment` → правильное значение в БД `awaiting` (max_length=10)
- `STATUS_ACTIVE` уже полностью удалён (сессия 29.05)

## Сессия 01-02.06.2026: Унификация сервисных сообщений администратору

### Что сделано
- **`admin_format.py`** — новый файл `vacancy/services/admin_format.py` с функциями `format_user_block(user)`, `format_user_block_with_contact(user, vacancy)`, `format_group_link(vacancy)`. Все сервисные сообщения админу используют эти функции.
- **Единый блок данных заказчика**: ID + Ім'я + Username + Телефон + Контактний (если отличается от регистрационного). Добавлен ко всем вакансийным сообщениям.
- **Ссылка на группу** добавлена ко всем вакансийным сообщениям через `format_group_link()`.
- **Відгук** — показывает обоих участников (Автор + Працівник).
- **`ADMIN_TELEGRAM_IDS`** полностью удалён из `config/django/base.py` и `.env`. Все уведомления через `admin_broadcast()` (запрос `is_staff=True`).
- **chr() кодирование** убрано из `_escalate_rollcall()` и `admin_start_call_fail_detailed()`.
- **Инлайн-форматирование** в `views.py` заменено на вызовы методов форматтера: `admin_all_unchecked()`, `admin_employer_closed_invoice()`, `admin_employer_closed_no_workers()`.
- **Сценарій Б** (`admin_scenario_b()`) — сообщение «Початок роботи — недостатньо робітників!» с количеством (Потрібно/Підтверджено) + блок заказчика + группа. Вызывается в 2 местах views.py.
- **`parse_mode="HTML"`** добавлен в 4 наблюдателя (vacancy_close ×2, feedback, refind).

### Ключевые файлы
- `vacancy/services/admin_format.py` — единые функции форматирования
- `vacancy/services/call_formatter.py` — все admin-методы переписаны
- `vacancy/services/vacancy_formatter.py` — `for_admin_chat`, `for_admin_refind`, `for_admin_new_feedback`
- `vacancy/tasks/call.py` — `_escalate_rollcall()` переписан
- `vacancy/views.py` — инлайн-сообщения заменены + сценарій Б
- `telegram/utils.py` — `notify_admins_new_user()` → `admin_broadcast()`
- `tests/test_session_20260601_admin_notifications.py` — 17 тестов

## Сессия 02.06.2026: Встраивание участников в карточку вакансии + баг-фиксы

### Что сделано
- **Страница «Учасники» встроена в карточку вакансии** — вся логика перекличек, чекбоксы, список работников, кнопки «Підтвердити» и «Продовжити пошук» теперь отображаются прямо на карточке вакансии. Кнопка «Додавання/Видалення працівників» удалена.
- **vacancy_members** — старый view полностью удалён, URL `/members/` редиректит на `/detail/` (обратная совместимость со старыми ссылками из бота).
- **Вспомогательная функция `_build_members_context()`** — выделена для повторного использования; формирует данные участников, перекличек, чекбоксов.
- **call_markup.py** — ссылки из бота ведут на `/detail/` вместо `/members/`.

### Косметические правки ЛК заказчика
- «Закрити вакансію» — перенесена выше над информационной карточкой; скрывается во время перекличек и после выставления счёта.
- «Учасники» → «Робітники» повсюду.
- «Група в Telegram» → «Група з робітниками» / «Перейти для спілкування».
- «Підтвердити» → «Підтвердити. Робітників достатньо.»
- «Продовжити пошук» → «Підтвердити наявних + шукати ще» — закреплена внизу рядом с кнопкой подтверждения.
- Подсказка переклички — красный текст «Увага!», без фоновой карточки.
- Карточки рабочих — кнопка «Дивитися/Залишити відгук» сверху над именем; счётчик отзывов убран; «Видалити з групи» скрывается после начала рабочего времени.
- Объединённые карточки переклички — полная карточка рабочего (отзыв, имя, телефон) + чекбокс справа.

### Баг-фиксы
- **Статус MEMBER до входа в группу**: убрано преждевременное присвоение MEMBER в `call.py` при нажатии «Підтвердити» в боте. Теперь MEMBER ставится только при реальном входе в группу (`group.py chat_member handler`).
- **Дубль VacancyUser**: исправлен `update_or_create` в `group.py` — использовался `status` как фильтр поиска вместо `defaults`, создавая дубли.
- **Сдвиг времени при «Поновити пошук»**: `vacancy_continue_search` сдвигал время всегда. Теперь — только если рабочее время уже прошло; до начала работы время остаётся оригинальным.
- **Кик недавнего участника**: `before_start` проверял `join_confirm` запись для определения «недавно вошедших», но эта запись удалялась при «Поновити пошук». Заменено на проверку `VacancyUser.updated_at`.

### Тесты
- `tests/test_session_20260602_members_embed.py` — 7 тестов: встроенные участники, редирект /members/, статус PENDING_CONFIRM, сдвиг времени, before_start для новых/старых участников.
- `tests/test_session_20260602_continue_search_time.py` — 2 теста: сдвиг времени до/после начала работы.
- Обновлены тесты: `test_feedback_contacts_merge.py`, `test_session_20260512.py`, `test_session_20260531_members_rollcall.py`, `test_vacancy_detail_buttons.py`, `test_apply_flow.py`, `test_session_20260430.py`, `test_rollcall_session_20260509.py`.
- Итого: 399 тестов, все проходят.

### Ключевые файлы
- `vacancy/views.py` — `_build_members_context()`, обновлённый `vacancy_detail`, `vacancy_continue_search` с условным сдвигом времени
- `vacancy/templates/vacancy/vacancy_detail.html` — полная перезапись с встроенными участниками
- `vacancy/services/observers/call_observer.py` — `check_before_start` использует `updated_at`
- `vacancy/services/call_markup.py` — ссылки на `/detail/`
- `telegram/handlers/callback/call.py` — убрана преждевременная смена на MEMBER
- `telegram/handlers/member/user/group.py` — исправлен `update_or_create`

## Автоподтверждение вакансий (02.06.2026)

- Поле `UserWorkProfile.auto_approve_vacancy` (BooleanField, default=False) — включатель на конкретного Заказчика
- Логика в `vacancy/services/auto_approve.py` → `try_auto_approve(vacancy)`:
  - Проверяет `work_profile.auto_approve_vacancy`
  - Привязывает канал (если нет) и группу (если есть свободная)
  - Ставит `status=approved`, `search_active=True`, `extra["auto_approved"]=True`
  - Отправляет Админам «✅ Автоматично підтверджено» + текст вакансии
  - Если нет свободных групп: уведомляет Админов «⚠️ Немає вільних груп!», вакансия уходит на обычную модерацию
- Работает в двух местах:
  1. `vacancy_create` — создание новой вакансии
  2. `vacancy_resume_search` — продление на завтра (из бота)
- НЕ затрагивает:
  - `vacancy_continue_search` (Поновити пошук / Продовжити пошук) — уже работал без модерации
  - Кнопки сценариев А/Б при перекличке
- Включение: Панель управления → карточка пользователя → Work profile → «Auto-approve vacancies»

## Сессия 03.06.2026 — Повторное нажатие «Я ГОТОВИЙ ПРАЦЮВАТИ»

**Проблема:** При повторном нажатии кнопки в канале города заказчик и рабочий получали одинаковое сообщение «Перейдіть у Власний кабінет» без привязки к конкретной вакансии. При двойном нажатии рабочим пока висит «Підтвердити/Відмовитись» — спам дубликатов.

**Решения (файл telegram/handlers/messages/commands.py):**

1. **Заказчик-владелец** нажал свою вакансию → `_send_owner_action_message`:
   - Если `vacancy.extra["employer_invite_msg_id"]` есть (инвайт уже отправлялся) → 1 кнопка «Керування вакансією» (WebApp на `/vacancy/<id>/detail/`).
   - Если ключа нет → 2 кнопки: «Перейти в групу вакансії» (invite_link) + «Керування вакансією». Сохраняет `employer_invite_msg_id`.

2. **Рабочий уже в этой вакансии** (`type=already_in_vacancy`) → `_send_worker_my_work_message`: кнопка WebApp на `/work/my-work/` (страница «Моя робота»).

3. **Антиспам «Підтвердити/Відмовитись»**: при повторном нажатии удаляет старое сообщение (через `vacancy.extra["confirm_msg_ids"]`) перед отправкой нового. Перезаписывает `message_id`.

4. Получение `vacancy` перенесено ВЫШЕ проверки роли employer в `_process_apply_payload`, чтобы vacancy была доступна для `_send_owner_action_message`.

**Тесты:** `tests/test_session_20260530_apply_button_messages.py` — 6 тестов (переписаны + добавлены). 421 тест всего, все проходят.

## Сессия 03.06.2026 (часть 2) — get_chat_member + кнопка одобрения

**Баги из боевой проверки:**
1. Заказчик уже в группе, но после «Поновити пошук» получал 2 кнопки (инвайт + карточка) — флаг `employer_invite_msg_id` ненадёжен.
2. Рабочий подтвердил участие, но не зашёл в группу — получал «Моя робота» вместо инвайта.

**Решение:** `_send_owner_action_message` и `_send_worker_my_work_message` теперь проверяют реальное членство через `bot.get_chat_member()`:
- В группе → заказчик: «Керування вакансією» (карточка); рабочий: «Моя робота».
- Не в группе → обоим: кнопка «Перейти в групу вакансії» (invite_link).

**Кнопка одобрения:** В `approved_user_observer.py` заменена `get_vacancy_my_list_markup()` («До поточних заявок») на `_get_detail_markup(vacancy)` («Керування вакансією» с прямой ссылкой на карточку) для всех случаев одобрения.

**Тесты:** 7 тестов в `test_session_20260530_apply_button_messages.py` (полностью переписаны под get_chat_member). 422 теста всего.

## Сессия 03.06.2026 (часть 3) — 4 этапа рабочего + троттлинг

**Рабочий — 4 этапа при повторном нажатии «Я ГОТОВИЙ ПРАЦЮВАТИ»:**
`_send_worker_my_work_message` теперь определяет этап по VacancyUserCall + VacancyContactPhone + get_chat_member:
1. VacancyUserCall(SENT) → повторно «Підтвердити/Відмовитись» (с антиспамом — удаление старого)
2. VacancyUserCall(CONFIRM) + нет VacancyContactPhone → повторно запрос телефона (Підтвердити/Змінити или «Напишіть номер»)
3. VacancyUserCall(CONFIRM) + есть VacancyContactPhone + не в группе → `send_worker_group_invite()`
4. В группе → «Моя робота» (WebApp)

**Троттлинг 300 сек** в `apply_vacancy.py`:
- Шаг 7 (owner нажал свою вакансию) и шаг 9b (рабочий уже в этой вакансии)
- `django.core.cache` с ключом `apply_throttle:{user_id}:{vacancy_id}`, TTL=300
- При повторе раньше 300 сек → тост «Зачекайте трохи» без последствий

**Тесты:** 422 теста, все зелёные.

## Session 03.06.2026 (доповнення) — cleanup window 7d -> 1d

- `UNREGISTERED_DAYS` в `user/tasks.py` змінено з 7 на 1.
- Тепер `cleanup_unregistered_users_task` (Celery beat, 03:30 щодня) видаляє за 24 години:
  - юзерів-«обрубків», які дали не-+380 номер і отримали відмову (work_profile=None);
  - юзерів, які натиснули /start, але не закінчили реєстрацію.
- Підкручений тест `test_keeps_user_without_profile_before_7_days`: days=3 -> hours=1.
- Новий тест `tests/test_session_20260603_cleanup_1day.py` фіксує нове вікно (3 кейси).
- Деплой: рестарт `celery-worker.service` + `celery-beat.service`. Gunicorn не чіпали.


## Сесія 04.06.2026 — Байесовський рейтинг, захист відгуків, кікнуті робітники

### Зміни

1. Байесовський рейтинг замість простого відсотка
   - Новий файл user/rating.py — функція bayesian_rating(likes, dislikes)
   - Формула: (C * m + likes) / (C + total) * 100, де C = поріг з БД, m = середній рейтинг по платформі
   - Поріг керується з адмін-панелі: модель RatingConfig в work/models.py (розділ Work, Налаштування рейтингу). Метод RatingConfig.get_threshold()
   - Байесовський рейтинг застосовано у всіх місцях відображення

2. Форма відгуку — оцінка обовязкова
   - VacancyUserFeedbackForm: rating (лайк/дизлайк) обовязковий, text необовязковий

3. Захист від дублікатів ручних відгуків
   - vacancy_user_feedback view: 1 ручний відгук від 1 користувача іншому за 1 вакансію

4. Виправлені шаблони
   - employer_reviews.html, vacancy_user_reviews.html — додані значки лайк/дизлайк (були порожні)
   - vacancy_feedback.html — додані значки на кнопках Лайк/Дизлайк
   - Позитивних перейменовано на Рейтинг N відсотків на всіх сторінках
   - vacancy_user_list.html — прибрані зайві теги else/endif (TemplateSyntaxError)

5. Кнопка в ЛК (обидва дашборди)
   - Замість reviews_count тепер: rating_percent (Байес) + text_reviews_count (тільки з текстом)
   - Відображення: Рейтинг N відсотків та N відгуків

6. Рейтинг в карточці робітника (vacancy_detail)
   - _build_members_context рахує rating_percent для кожного робітника
   - На кнопці: Дивитися/Залишити відгук та Рейтинг N відсотків

7. Навігація Назад за роллю
   - vacancy_feedback.html, vacancy_user_reviews.html, vacancy_user_list.html — worker йде на Моя робота, employer/admin на карточку вакансії
   - vacancy_user_feedback і vacancy_user_reviews views — додано user_role в контекст

8. Кікнуті/вийшовші робітники бачать вакансію 1 годину
   - worker_my_work view: шукає VacancyUser зі статусом kicked/left та updated_at за останню годину
   - worker_dashboard (index.py): та сама логіка для кнопки Моя робота
   - Ссилка на групу прихована при is_kicked=True
   - vacancy_kick_member view: оновлює VacancyUser.status=KICKED + updated_at
   - GroupService.kick_user: додано updated_at при оновленні VacancyUser
   - handle_user_status_change webhook: додано updated_at при Status.LEFT

### Файли змінені
- user/rating.py — НОВИЙ, bayesian_rating()
- work/models.py — RatingConfig модель
- work/admin.py — RatingConfigAdmin
- vacancy/forms.py — валідація rating обовязковий
- vacancy/views.py — захист дублікатів, user_role, kick_member оновлює VacancyUser
- work/views/index.py — Байес рейтинг + kicked/left пошук
- work/views/worker.py — Байес рейтинг + kicked/left пошук
- work/views/employer.py — Байес рейтинг
- work/templates/work/ — оновлені дашборди і сторінки відгуків
- vacancy/templates/vacancy/ — оновлені шаблони відгуків і навігація
- telegram/service/group.py — updated_at при kick
- telegram/handlers/member/user/group.py — updated_at при left


## Сесія 05.06.2026 — Кік з старої групи при вході в нову

### Зміни

1. При вході робітника в нову групу вакансії — автоматичний кік з груп старих вакансій
   - Тільки якщо стара вакансія в статусі closed/awaiting/paid
   - Якщо стара вакансія approved/stopped — робітника не пускає в нову (існуюча логіка)
   - Реалізовано в handle_user_status_change (telegram/handlers/member/user/group.py)
   - Після успішного входу (status=MEMBER) шукає всі UserInGroup крім поточної групи
   - Для кожної перевіряє статус вакансії, кікає через GroupService.kick_user

### Файли змінені
- telegram/handlers/member/user/group.py — кік з старих груп після входу в нову



## Сесія 06-07.06.2026 — Етапи 1-5: snapshot, UI, спір-перекличка, авто-підтвердження, боржники

Велика сесія в 5 етапів, що вирішила:
- Баг 500 у 2-й перекличці без галочок
- Відсутність даних на стор. «Моя робота» під час робочого дня
- Сценарії А/Б/В для 2-ї переклички (спір, бан, авто-підтвердження)
- Ручне підтвердження оплати адміністратором
- Постійний бан за неоплату

### Етап 1 — Snapshot 1-ї переклички (merged в develop)
- Новий сервіс `vacancy/services/rollcall_snapshot.py`:
  - `save_first_rollcall_snapshot(vacancy, user_ids)` — зберігає в `vacancy.extra["rollcall_snapshot"]`
  - `get_snapshot_user_ids(vacancy)` — повертає список user_id
  - `get_snapshot_vacancy_users(vacancy)` — QuerySet VacancyUser
  - `is_user_in_snapshot(vacancy, user_id)`
  - Константа `SNAPSHOT_KEY = "rollcall_snapshot"`
- `vacancy/views.py` lines 181-187: збереження snapshot після успішної 1-ї переклички
- `vacancy/views.py` lines 317-318 (`vacancy_call`): для AFTER_START використовуємо snapshot замість members
- `vacancy/views.py` lines 580-583 (`_build_members_context`): rollcall_qs з snapshot для 2-ї переклички
- `work/views/worker.py` lines 80-130: розширений фільтр для «Моя робота» — `STATUS_APPROVED, STATUS_SEARCH_STOPPED` + snapshot fallback для кікнутих/тих, що пішли
- Тести: `tests/test_session_20260606_rollcall_snapshot.py` (5 тестів)

### Етап 2 — UI карткі вакансії
- `vacancy/views.py`: `owner_in_group` обчислюється через `UserInGroup.objects.filter(user=vacancy.owner, group=vacancy.group, status=MEMBER)`
- `vacancy/templates/vacancy/vacancy_detail.html`:
  - Кнопка групи прихована якщо `not owner_in_group`
  - Телефон у картці учасника видно тільки `if is_member`
  - Кнопка «Видалити з групи» — тільки до `first_rollcall_passed`
  - Якорь `id="rollcall-block"` + JS-скрол при `?focus=rollcall`
- `vacancy/services/call_markup.py`: 3 бот-кнопки переклички тепер додають `?focus=rollcall` до URL
- Тести: `tests/test_session_20260606_card_ui.py` (7 тестів)

### Етап 3 — Спірна перекличка (Сценарії Б+В, баг 500, повторний submit)
**Гілка `feature/disputed-rollcall`, 5 коммітів (3.A-3.E)**

#### 3.A — сервіс `vacancy/services/disputed_rollcall.py`
- `mark_disputed(vacancy, first_count, selected_user_ids, rejected_user_ids, is_full_uncheck)` — створює стан спору в `vacancy.extra["disputed_rollcall"]`
- `is_disputed(vacancy)`, `get_disputed(vacancy)`, `clear_disputed(vacancy)`
- `disable_admin_buttons(vacancy)` — захист від гонки
- `increment_reminders(vacancy)` — інкремент лічильника + timestamp
- `finalize_rollcall(vacancy, final_selected_user_ids, finalized_by)`:
  - Оновлює `VacancyUserCall` статуси (CONFIRM/REJECT)
  - Банить REJECT робітників через `BlockService.auto_block_rollcall_reject`
  - `second_rollcall_passed = True`, `status = STATUS_AWAITING_PAYMENT`
  - Викликає `send_vacancy_invoice` (lazy import)
  - Розблоковує замовника (`unblock_employer_rollcall_fail`)
  - Очищає disputed стан
- Константа `DISPUTED_KEY = "disputed_rollcall"`
- Структура стану: `{first_count, second_count, selected_ids, rejected_ids, is_full_uncheck, reminders_count, last_reminder_at, admin_buttons_disabled}`

#### 3.B — обробник `vacancy_check_call` для 2-ї переклички
- **Виправлено баг 500**: всі 4 виклики `TelegramBroadcastService()` в `vacancy/views.py` тепер передають `notifier=TelegramNotifier(_bot)` (рядки 211, 232, 272, 894)
- Єдина гілка `elif call_type == CallType.AFTER_START and (all_unchecked or rejected_users > 0)`:
  - Викликає `mark_disputed(...)`
  - **Сценарій В** (всі зняті): кік замовника з групи (`GroupService.kick_user`), `BlockService.auto_block_employer_rollcall_fail`, видалення старого `final_call_msg_id`, нове повідомлення «Ви заблоковані!» з 2 кнопками (WebApp на `?focus=rollcall` + URL на `t.me/robochi_work_admin`)
  - **Обидва сценарії**: уведомлення адмінам через `get_admin_disputed_rollcall_markup`
- Робітники **НЕ банять одразу** — бан відкладений до `finalize_rollcall`

#### 3.C — Celery-таска `disputed_rollcall_reminders_task`
- Запускається кожні 30 сек (`config/settings/celery.py`)
- Тільки для Сценарію Б (`is_full_uncheck=False`)
- Інтервал 5 хв, макс 12 нагадувань
- Шле «Підтвердіть наявність робочих у другій перекличці» з `get_rollcall_reminder_markup`
- Тести: `tests/test_session_20260606_3c_reminders.py` (6 тестів)

#### 3.D — callback-обробники адміна
- Новий `CallbackData`: `disputed_action = CallbackData("action", "vacancy_id", prefix="disputed")` в `telegram/handlers/common.py`
- Дії: `confirm`, `edit`, `unblock_yes`, `unblock_no`
- Файл: `telegram/handlers/callback/disputed_rollcall.py`
- Markups в `vacancy/services/call_markup.py`:
  - `get_admin_disputed_rollcall_markup(vacancy)` — 2 кнопки (Підтвердити кількість / Редагувати кількість)
  - `get_admin_unblock_employer_modal_markup(vacancy)` — Так/Ні модалка
- Захист від гонки через `admin_buttons_disabled` flag
- Зареєстровано в `telegram/handlers/callback/__init__.py`
- Тести: `tests/test_session_20260606_3d_admin_callbacks.py` (6 тестів)

#### 3.E — повторний submit замовника після спору
- Нова гілка в `vacancy_check_call` ПЕРЕД обробкою спору: перевіряє чи `vacancy.extra["disputed_rollcall"]` вже існує
- Сценарій В повторний з 0 чекбоксів → `form.add_error` + re-render `vacancy/call_confirm.html`
- 1+ чекбокс → `disable_admin_buttons` + `finalize_rollcall` + broadcast адмінам «Замовник X сам пройшов...»
- Тести: `tests/test_session_20260606_3e_repeat_submit.py` (4 тести)

#### 3.* — оновлено старі тести
- `tests/test_second_rollcall.py`: 2 тести переписані під нову поведінку (часткове зняття НЕ блокує замовника)

### Етап 4 — Адмін-модерація переклички (merged)
**Гілка `feature/admin-moderate-rollcall`**

- `work/views/admin_panel.py` line ~504: `admin_moderate_rollcall(request, vacancy_id, call_type)`:
  - Декоратор `@staff_required` (404 для не-staff)
  - Pre-fill формою з останнім вибором замовника
  - Валідація: адмін може ЛИШЕ ДОДАВАТИ чекбокси (не знімати), окрім Сценарія В де можна вибрати будь-яку кількість
  - Submit → `disable_admin_buttons` + `finalize_rollcall`
- `work/templates/work/admin_moderate_rollcall.html` (новий)
- `work/urls.py`: `admin_moderate_rollcall` path `admin-panel/vacancy/<int:vacancy_id>/moderate-rollcall/<str:call_type>/`
- `telegram/handlers/callback/disputed_rollcall.py`: `_handle_edit` шле посилання на цей view
- Тести: `tests/test_session_20260606_4_admin_moderate_rollcall.py` (5 тестів)

### Етап 5 — Ігнор переклички + боржники + перм-бан (merged)
**Гілка `feature/rollcall-ignore-and-debtors`, 2 комміти (5.A, 5.C-F)**

#### 5.A — розділ «Боржники» + ручне підтвердження оплати
- `work/views/admin_panel.py`:
  - `admin_debtors_list(request)` — список вакансій в `STATUS_AWAITING_PAYMENT` з полями: замовник, сума, дата рахунку, днів просрочки, нагадування, активний блок
  - `admin_mark_paid(request, vacancy_id)` — POST-only, ставить `is_paid=True`, `status=STATUS_PAID`, знімає UNPAID-блок, шле бот-повідомлення
  - **Важливо**: фільтр `is_paid` в Python (не `.exclude(extra__is_paid=True)`) — SQLite JSONField має ненадійну поведінку з відсутніми ключами
- `work/templates/work/admin_debtors.html` (новий)
- `work/templates/work/admin_dashboard.html`: кнопка «Боржники» в `admin-top-bar`
- `work/urls.py`: `admin_debtors` path `admin-panel/debtors/`, `admin_mark_paid` path `admin-panel/debtors/<int:vacancy_id>/mark-paid/`
- Management command `python manage.py mark_vacancy_paid <id> [--keep-block]`:
  - Файл `vacancy/management/commands/mark_vacancy_paid.py`
  - Створено `vacancy/management/__init__.py` та `vacancy/management/commands/__init__.py`
  - Вимагає `set -a && source .env && set +a` перед запуском
- Тести: `tests/test_session_20260606_5a_debtors.py` (6 тестів)

#### 5.C — авто-підтвердження через 3 години ігнору
- Нова таска `auto_confirm_ignored_rollcall_task` в `vacancy/tasks/call.py`:
  - Запуск кожні 60 сек
  - Умови: `status=STATUS_SEARCH_STOPPED`, `second_rollcall_passed=False`, є `rollcall_snapshot`, немає `disputed_rollcall`, `end_time + 3h < now`, не `auto_confirmed_at_ignore`
  - Поведінка: Сценарій А — викликає `finalize_rollcall` зі всім snapshot
- Зареєстровано в beat: `config/settings/celery.py`
- Тести: `tests/test_session_20260606_5c_auto_confirm.py` (5 тестів)

#### 5.D — нагадування про оплату 24× за годину
- Нова таска `send_unpaid_reminders_task`:
  - Запуск кожні 60 сек
  - Умови: `status=STATUS_AWAITING_PAYMENT`, `is_paid=False`, `unpaid_reminders < 24`, минув час від `unpaid_last_reminder_at`
  - Інтервал 1 година, макс 24 нагадування
  - Лічильник в `vacancy.extra["unpaid_reminders"]`, timestamp `unpaid_last_reminder_at`
- Тести: `tests/test_session_20260606_5d_unpaid_reminders.py` (5 тестів)

#### 5.E — постійний бан після 24 нагадувань
- Розширення `send_unpaid_reminders_task`:
  - Коли `unpaid_reminders >= 24` і не `permanent_ban_done`:
    - `BlockService.block_user(user=owner, block_type=BlockType.PERMANENT, reason=BlockReason.UNPAID)`
    - Фінальне повідомлення замовнику з сумою
    - Broadcast адмінам
  - `BlockType.PERMANENT` автоматично деактивує `user.is_active`
- Flag `vacancy.extra["permanent_ban_done"]` — ідемпотентність
- Тести: `tests/test_session_20260606_5e_permanent_ban.py` (3 тести)

#### 5.F — видалено legacy 2nd-rollcall auto-confirm з `_escalate_rollcall`
- В `_escalate_rollcall` (vacancy/tasks/call.py) гілка `elif not vacancy.second_rollcall_passed` тепер тільки логує — 3-годинне вікно ігнору тепер обробляється виключно через `auto_confirm_ignored_rollcall_task`
- Auto-confirm 1-ї переклички в тій же функції — НЕ змінено
- Оновлено 3 старих тести під нову поведінку:
  - `tests/test_regression_invoice_autopay.py::test_invoice_workers_count_after_auto_confirm`
  - `tests/test_regression_lifecycle_stuck.py::test_auto_confirm_2nd_rollcall_changes_status_to_awaiting`
  - `tests/test_session_20260527_invoice_fix.py::test_escalate_second_rollcall_writes_after_start_calls`
- Нові тести: `tests/test_session_20260606_5f_legacy_auto_confirm_removed.py` (2 тести)

### Celery beat schedule — додано 3 нові задачі
- `disputed_rollcall_reminders_task` — кожні 30 сек
- `auto_confirm_ignored_rollcall_task` — кожні 60 сек
- `send_unpaid_reminders_task` — кожні 60 сек

### Ключові уроки сесії
- **Pre-commit hook patterns**: ruff може форматувати імпорти/строки — патчити треба під реальний формат файлу через `cat -A`
- **SQLite JSONField обмеження**: `.exclude(extra__is_paid=True)` НЕ працює надійно — використовувати фільтр в Python
- **Timezone в тестах з `_get_end_aware`**: треба `(now - delta).astimezone(tz)` перед `.time()` — інакше naive time інтерпретується як локальний Київ
- **`finalize_rollcall` повинен виконувати lazy import `send_vacancy_invoice`**: тести моніторять через `monkeypatch.setattr("vacancy.services.invoice.send_vacancy_invoice", ...)`
- **`VacancyCallForm.users` приймає `VacancyUser.pk`**, не `user.id` (немає to_field_name)
- **Stage 5.A SQLite quirk**: `admin_debtors_list` фільтрує в Python через `[v for v in vacancies if not v.extra.get("is_paid")]`

## Тех. борг та flaky-тести — для майбутніх сесій
- **Flaky-тести**, що падають тільки після 23:00 Київ (start_time переходить на наступний день а date залишається сьогодні):
  - `tests/test_session_20260430.py::TestBeforeStartCall::test_before_start_created_for_early_joiner`
  - `tests/test_session_20260602_members_embed.py::TestBeforeStartRecentJoiner::test_early_joiner_gets_call`
  - Проблема: `start_time_local = (now + 1h).astimezone(tz).time()` втрачає дату, тоді `vacancy.date=date.today() + time` дає вчорашній час замість завтрашнього
  - Фікс: правильно обчислювати vacancy.date коли (now+1h) переходить через північ
- **Баг continue_search після 1-ї переклички** (визначено 07.06.2026):
  - Кнопка «Підтвердити наявних + шукати ще» в `vacancy_detail.html:269` веде на `vacancy:continue_search?confirm_rollcall=1`
  - Але обробник `?confirm_rollcall=1` живе в `vacancy_resume_search`, не в `vacancy_continue_search`
  - В результаті `vacancy_continue_search` ігнорує параметр, скидає `first_rollcall_passed=False`, видаляє всі VacancyUserCall, snapshot НЕ зберігається
  - Кнопка фактично працює як «Просто шукати ще», без підтвердження 1-ї переклички
- **План Етапу 6 (continue_search після 1-ї переклички, не виконано):**
  - Сценарії підтверджені користувачем:
    1. За ≤1ч набралось `people_count` → стоп refind, snapshot готовий
    2. За 1ч ніхто новий не зайшов → таймер експ., snapshot = ті хто був
    3. За 1ч зайшли частково → таймер експ., snapshot = (initial + ті хто встигли) [варіант b]
    4. Замовник «Зупинити пошук» → snapshot = поточні, якщо 0 → закрити вакансію
  - При `members.count() == people_count` → негайно зупиняти refind (зайвих відрізати)
  - Snapshot динамічний — кожне додавання/видалення робітника в 1ч оновлює snapshot
  - Підетапи:
    - 6.A: новий view `vacancy_confirm_and_continue_search(pk)` + переключити шаблонну кнопку
    - 6.B: Celery-таска «refind 1h timer» + логіка 4 сценаріїв
    - 6.C: модифікація `vacancy_stop_search` — якщо після start_time і `first_rollcall_passed=False` → авто-підтвердити з фактичними
    - 6.D: тести на всі 4 сценарії + регрес
  - Відкрите питання: 1 година відраховується від моменту натискання чи від start_time? (наступне уточнення з користувачем)


## Сесія 07.06.2026 (вечір) — Етап 6.A + фікс flaky-тестів

### Етап 6.A: continue_search після 1-ї переклички — РЕАЛІЗОВАНО

**Контекст:** до цього кнопка «Підтвердити наявних + шукати ще» в шаблоні переклички вела на `vacancy:continue_search?confirm_rollcall=1`, але обробник `?confirm_rollcall=1` жив у `vacancy_resume_search`. У результаті `continue_search` ігнорував параметр, скидав `first_rollcall_passed=False` і знищував усі `VacancyUserCall` — кнопка фактично ламала 1-у перекличку.

#### Узгоджені бізнес-правила (Q1–Q5)
- **Таймер 1 година** замість 2-х (правка ТЗ).
- Таймер відраховується **від моменту натискання кнопки**.
- Snapshot 1-ї переклички зберігається **на момент фінализації**, не натискання — щоб робітники, які зайшли за цей 1 год, теж потрапили в snapshot.
- При досягненні `people_count` всередині вікна — НЕ фіналізуємо одразу, чекаємо таймер (на випадок виходу).
- `Зупинити пошук` під час вікна:
  - ≥1 робітник → негайна фіналізація (snapshot = поточний склад).
  - 0 робітників → автозакриття як «Закрити вакансію» (CLOSED + таймер 3 год очищення групи).

#### Що зроблено

**Новий хелпер** `vacancy/services/continue_after_rollcall.py`:
- `is_in_continue_mode(vacancy)` — перевірка прапора в `extra`.
- `clear_continue_flags(vacancy)` — видалення прапорів (без save).
- `finalize_continue_after_first_rollcall(vacancy)` — ідемпотентна фіналізація:
  - 0 робітників → `STATUS_CLOSED`, `closed_at=now`, очищення прапорів, повідомлення адміну `admin_employer_closed_no_workers`.
  - ≥1 робітник → snapshot через `save_first_rollcall_snapshot`, `extra["calls"][START]`, `VacancyUserCall(START)→CONFIRM`, статус `SEARCH_STOPPED`, `search_active=False`. Якщо `count<plan` — `scenario_b` повідомлення адміну.

**Нова ветка в `vacancy_continue_search`** (vacancy/views.py):
- При `?confirm_rollcall=1 + first_rollcall_passed=False` викликається `_continue_search_after_first_rollcall(request, vacancy)`.
- Зсуває `start_time` на `now+1h` (округлення до 15 хв), `end_time` тільки якщо зсув робить зміну < 3 год.
- Встановлює `first_rollcall_passed=True` одразу (зупиняє нагадувачі переклички).
- Записує в `extra`: `continue_after_first_rollcall=True`, `continue_started_at`, `continue_deadline`.
- Перепубліковує вакансію в канал.
- Планує `finalize_continue_after_rollcall_task.apply_async(countdown=3600)`.
- Шле повідомлення замовнику в бот: «Триває добір… Завершиться о HH:MM».

**Новий Celery-таск** `vacancy/tasks/call.py::finalize_continue_after_rollcall_task(vacancy_id)`:
- Не в beat schedule — викликається через `apply_async(countdown=3600)`.
- Викликає `finalize_continue_after_first_rollcall`, який ідемпотентний.

**Правка `vacancy_stop_search`** (vacancy/views.py):
- На вході перевіряє `is_in_continue_mode(vacancy)` — якщо так, викликає `finalize_continue_after_first_rollcall` і повертається. Решта старої логіки без змін.

**UI-баннер** в `vacancy/templates/vacancy/vacancy_detail.html`:
- Виводиться між заголовком і кнопкою «Закрити», коли `continue_mode=True`.
- Текст «Триває добір працівників. Завершиться о HH:MM».
- JS-лічильник тікає кожну секунду: «(залишилось 47 хв 12 с)».
- Коли таймер дійшов до 0 — текст «(завершується…)», авто-перезавантаження сторінки через 5 сек.

**Контекст view `vacancy_detail`** доповнено полями `continue_mode` і `continue_ends_at` (парсимо `extra["continue_deadline"]` у `datetime`).

**Правка `search_deadline`** — `2h → 1h` (правка ТЗ).

**Регресійні тести** (`tests/test_continue_search_bug_07062026.py`, 7 тестів):
1. GET `?confirm_rollcall=1` встановлює прапори і відкладає snapshot.
2. Сценарій 1: ліміт досягнуто → snapshot містить ВСІХ поточних.
3. Сценарій 2: ніхто не зайшов → snapshot = початкові.
4. Сценарій 3: дозайшли частково → snapshot оновлений.
5. Сценарій 4: `stop_search` з ≥1 робітником → негайна фіналізація + ідемпотентність повторної.
6. Edge case: `stop_search` з 0 робітниками → авто-закриття як CLOSED.
7. Перевірка `VacancyUserCall.START.CONFIRM` після фіналізації.

### Фікс 2 flaky-тестів після 23:00 Київ

**Тести:**
- `tests/test_session_20260430.py::test_before_start_created_for_early_joiner`
- `tests/test_session_20260602_members_embed.py::test_early_joiner_gets_call`

**Діагноз:** `now = timezone.now()`, потім `start_time_local = (now+1h).astimezone(tz).time()` — час, але дата втрачена. `vacancy_factory(date=date.today(), start_time=start_time_local)`. Якщо `now+1h` після 23:00 Києва переходить через північ — `date.today()` залишає вчорашню дату Києва, а `start_time` вже відноситься до завтра → вакансія створюється «23 години тому» → 2-годинне вікно «до початку» давно прошло → нагадування не створюється → assert падає.

**Фікс:** взяти дату з того ж зсунутого datetime:
```python
target_local = (now + timedelta(hours=1)).astimezone(timezone.get_current_timezone())
vacancy_factory(date=target_local.date(), start_time=target_local.time())
```

### Ключові уроки сесії

- **Memory edit limit 500 chars** — при оновленні запис у пам'ять Claude інколи треба робити декілька проб щоб вкластися.
- **Ідемпотентні фіналізатори** — `finalize_continue_after_first_rollcall` повертає `{"action": "noop"|"finalized"|"auto_closed"}`, що дозволяє безпечно викликати з двох тригерів (Celery + view).
- **`save_first_rollcall_snapshot` сам викликає `vacancy.save()`** — порядок викликів важливий, щоб `update_fields` не затирав snapshot.
- **Telegram payment timer pattern**: `apply_async(countdown=3600)` краще за beat-schedule для одноразових таймерів.
- **Date-boundary в тестах**: завжди отримувати `date` і `time` з ОДНОГО datetime, не комбінувати `date.today()` із зсунутим часом.

### Дата та автор
Сесія 07.06.2026 завершена о 2026-06-07 17:17 EEST. Гілка `feature/continue-after-first-rollcall` смержена в `develop` (commit 36d043a + merge 8131a78); `fix/flaky-date-boundary` смержена в `develop`. Деплой: `collectstatic` + рестарт `gunicorn.service` + `celery-worker.service`. Підтверджено: таска `finalize_continue_after_rollcall_task` зареєстрована.

## 09.06.2026 — Critical cleanup fail-open + owner_in_group fix

### Bug 1: cleanup_inactive_users_task удалял живых пользователей
- `user/tasks.py::check_telegram_deleted` возвращал True на ЛЮБОЕ исключение `bot.get_chat()` (rate limit, timeout, network error)
- Каскад: User.delete() → Vacancy.owner CASCADE → Vacancy удалена → VacancyUser удалены каскадно
- Реально удалённые жертвы из логов journalctl:
  * 31.05.2026 03:00:11 — @Nephrite_u (worker, пересоздался через 14ч)
  * 08.06.2026 03:00:11 — @ParaibaUA (employer, vacancy id=126 утрачена навсегда)
- Симптом 08.06: бот при /start снова спрашивает телефон + WEBAPP попытка зайти на /vacancy/126/detail/ → 404
- Fix: на исключение return False (fail-open) + warning лог

### Bug 2: кнопка «Группа» пропала из карточки вакансии заказчика
- `vacancy/views.py:820` фильтровал UserInGroup по `Status.MEMBER`
- Но в `telegram/handlers/member/user/group.py:308` для владельца ставится `Status.OWNER`
- Условие никогда не выполнялось → owner_in_group=False → кнопка скрыта (Stage 2 регрессия 06.06)
- Fix: фильтр по `Status.OWNER`

### Tests
- `tests/test_session_20260609_cleanup_failopen.py` — 5 тестов
- `tests/test_session_20260609_owner_in_group.py` — статическая проверка кода
- Обновлены 2 старых теста, закреплявших баговое поведение:
  * `test_user_cleanup.py::test_api_error_treated_as_deleted` → `test_api_error_does_not_treat_as_deleted`
  * `test_session_20260606_card_ui.py::test_owner_in_group_true_when_owner_is_member` → split на 2 теста (OWNER=True, MEMBER=False)

### Что НЕ требует фикса
- «Нет переклички за 2ч + пустая Моя робота» — прямое следствие Bug 1 (вакансия удалена → before_start_call не находит, snapshot пуст). После Патча А не повторится.

### Известная вторая мина (tech debt)
- `cleanup_unregistered_users_task` тоже удаляет users (через 1 день при `is_completed=False`).
- Сейчас в БД у всех 8 юзеров is_completed=True — пока безопасно.
- Риск: если где-то `UserWorkProfile.objects.get_or_create(...)` создаёт профиль без последующего is_completed=True → жертва через сутки.
- Action item на следующую сессию: пройтись по всем местам get_or_create профиля.

### 09.06.2026 (продолжение) — cleanup hardening + Telegram status check

#### cleanup_unregistered_users_task — anomaly detector
- Срок 1 день оставлен (это by design — чистка мусорных /start без регистрации).
- Добавлен охранник: если у кандидата на удаление есть Vacancy.owner или VacancyUser.user — это аномалия (такое невозможно у незарегистрированного по дизайну). Skip + alert админам, deletion отменяется.
- Подробное логирование каждого решения cleanup.
- Tests: tests/test_session_20260609_cleanup_unregistered_anomaly.py (7 кейсов).

#### check_telegram_status — комбинированная проверка статуса Telegram-аккаунта
- 4 статуса: ALIVE / DELETED / BOT_BLOCKED / UNKNOWN.
- Шаг 1: bot.get_chat_member(city_channel, user.id) — точно когда юзер в канале, работает даже если бот заблокирован в приватном чате.
- Шаг 2 (fallback): bot.get_chat(user.id) для не-подписчиков канала.
- Ошибки «blocked by user» / «chat not found» / «forbidden» → BOT_BLOCKED (не deleted).
- Прочие ошибки API → UNKNOWN (fail-open).
- Старая check_telegram_deleted оставлена как legacy shim для обратной совместимости тестов.

#### cleanup_inactive_users_task — две фазы
- Pass 0: пересмотр существующих BOT_BLOCKED записей. ALIVE → BlockService.unblock_user (авто-снятие, когда юзер разблокировал бота). DELETED → удалить юзера. Иначе — оставить блок.
- Pass 1: все юзеры. DELETED → delete. BOT_BLOCKED → бессрочный TEMPORARY-блок (blocked_until=None). UNKNOWN → skip. ALIVE → проверка 180 дней.
- Добавлен BlockReason.BOT_BLOCKED + миграция user.0021.

#### Архитектурный нюанс
- Telegram Bot API **не присылает** chat_member события для подписчиков каналов (только для групп/супергрупп). Event-driven детектор Deleted Account невозможен. Опрос get_chat_member раз в сутки — единственный путь.

#### Tests
- tests/test_session_20260609_telegram_status_combined.py — 17 тестов (4 + 5 + 4 + 4 для unit-функций и обоих pass-ов).
- tests/test_user_cleanup.py — обновлены 6 декораторов @patch с check_telegram_deleted на check_telegram_status.

#### Принцип, на который опираемся
Все деструктивные операции теперь fail-open: при любой неопределённости задача НЕ удаляет/НЕ блокирует. Лучше пропустить итерацию и попробовать завтра, чем стереть живого юзера каскадом.

## 14.06.2026 — Admin Help button + persistent reply keyboard

**Що зроблено:**
- Reply-клавіатура: 3 кнопки на етапі реєстрації (контакт + договір + допомога), 2 постійні після (`is_persistent=True`). Кнопка «Договір оферти» — WebApp на публічну сторінку `/work/legal/offer/` напряму, бо initData у reply WebApp передається лише через sendData, не URL hash.
- Модель `AdminHelpRequest` (`user/models.py`, db_table `user_admin_help_request`, міграція user.0022) — pending/open/closed/timeout, FK на User, JSONField media_message_ids.
- Сервіс `user/services/admin_help.py`: `start_request` / `submit_request` / `cancel_request` / `close_request` / `_build_card`. COOLDOWN_KEY 5 хв, CACHE_KEY 10 хв, admin_help_pending_msg:{uid}.
- Картка адміну: TG ID, role, місто, тел, рейтинг Bayesian, активні блокування, активні вакансії (address замість city — у Vacancy немає FK на City). Кнопки: 🔗 Адмінка / 💬 Написати юзеру / ✅ Закрити звернення.
- Глобальний хендлер `telegram/handlers/messages/global_buttons.py` ловить кліки кнопок у всіх станах. Матчер у всіх локалях через `override(lang_code)`. Зареєстрований у `telegram/handlers/messages/__init__.py` ПЕРЕД `worker_phone` (інакше worker_phone з'їсть текст). Файл `__init__.py` помічено `# ruff: noqa: I001,F401,F811`.
- Реплай-хендлер `admin_reply.py`: реплай адміна у групі `ADMIN_HELP_CHAT_ID=-1003987159270` → бот пересилає юзеру з префіксом `↪️ <Імя> (адміністратор):` + реакція ✅.
- Уніфікація `/help`: у групах вакансій бот видаляє команду й запускає флоу у особистих (через `start_request`), fallback — deep-link з payload `{"type": "help"}`.
- Stub `telegram/_translation_stubs.py` для makemessages (тексти кнопок через змінні + multi-line склеєні рядки не підхоплюються без літерала).
- Celery таски: `cleanup_stale_admin_help` (countdown=600, переводить pending→timeout та видаляє «Опишіть проблему»). `auto_close_admin_help` (beat-schedule 1 година, OPEN > 24h → CLOSED). Обидві у `user/tasks.py`, розклад у `config/settings/celery.py`.
- **Django CACHES → Redis** (`django_redis.cache.RedisCache`, DB 1). Раніше Django використовував LocMemCache — окремий на кожен gunicorn worker, тому cache-флаги між викликами губилися. Тепер спільний Redis. Залежність: `django-redis>=5.4.0`.
- Reorg `user/services`: був файл `user/services.py` → пакет з `core.py` (старе ядро) + `admin_help.py`. `__init__.py` реекспортує BlockService, get_or_create_user_from_telegram, find_user_by_phone, admin_mark_vacancies_paid.
- Lazy-migration: при `default_start` старі юзери одноразово отримують клавіатуру разом з вітанням (не «·» окремим повідомленням).
- Кнопка «Назад» на `legal_offer.html` тепер закриває WebApp через `Telegram.WebApp.close()` (фолбек `history.back()`).
- Локалізація uk/ru через `polib`: 26+1 ключів. Запис у БД `Group(-1003987159270)` помічено status=deactivated щоб не потрапляла в integrity-check `_check_groups`.
- Регресійні тести `tests/test_session_20260611_admin_help.py` (11 тестів) — усі зелені.

**Ключеві learnings:**
- Django default cache = LocMemCache, НЕ розшарюється між gunicorn workers. Будь-який `cache.set` у webhook-handler може потім не знайтися. Якщо потрібен спільний стейт — обов'язково Redis.
- `makemessages` НЕ підхоплює `_(VAR)` де VAR — змінна. Потрібен stub-файл з явними літералами.
- pyTelegramBotAPI використовує порядок реєстрації хендлерів. Якщо `__init__.py` пакета `messages` імпортує `worker_phone` ДО нашого `global_buttons` — текст кнопок з'їдається.
- Ruff агресивно reformatує/схлопує блоки → assert-anchors часто не знаходяться після `ruff format`. Кращий підхід — або робити патчі ДО format, або polib для .po.
- WebApp у reply-кнопці отримує initData лише через `Telegram.WebApp.sendData()`, у URL hash його немає. Тому `check-web-app` обгортка не працює — публічну сторінку відкриваємо напряму.
- `Vacancy` НЕ має FK на `City` — лише `address: CharField`. У картці виводимо address.

**Бэклог:**
- Privacy mode off + ІІ-аналіз чатів — у бэклог.
- Кнопки у групах вакансій — не лізли.
