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

## На горизонте (приоритеты)
1. AgreementText для employer/worker в admin
2. ЛК администратора — наполнить функционалом
3. ЛК Employer — Фаза 2: управление заявками из ЛК (зупинити/закрити, повторний пошук, учасники групи, оплата monobank)
4. ЛК Worker — доработка: блокировка UI при блокировке, запрос телефона после подтверждения вакансії
5. Ротация вакансий
6. Monobank інтеграція

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
