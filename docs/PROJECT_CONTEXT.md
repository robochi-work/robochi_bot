
# ПОЛНЫЙ КОНТЕКСТ ПРОЕКТА robochi_bot

> Этот документ собран **только из переданных отчётов**.
>
> Важно: это **не гарантированно точный снимок текущего репозитория**, а **сводка последнего известного состояния** по веткам и обсуждениям.
>
> Если в отчётах по одному и тому же файлу были разные версии, ниже взята:
> 1. более поздняя по дате ветка;
> 2. внутри одной ветки — более поздний явно обозначенный вариант;
> 3. если последняя ветка содержала только **патч/кусок изменения**, а не полный файл, это отмечено отдельно как **реконструированная последняя известная версия**.

---

## 1. Итоговое описание проекта

`robochi_bot` — это Django-проект с Telegram-ботом и Telegram Mini App / WebApp для сервиса поиска подработки и работников.

### 1.1. Бизнес-идея проекта
Проект предназначен для двух ролей:
- **Рабочий / Worker** — ищет подработку;
- **Заказчик / Employer** — создаёт заявки и ищет работников.

### 1.2. Ключевая продуктовая логика
По итогам согласования нового ТЗ зафиксирована такая логика:

- основной пользовательский вход идёт через **Telegram**;
- **бот** отправляет сервисные текстовые сообщения;
- **WebApp / Mini App** используется для:
  - личных кабинетов;
  - форм;
  - табличных интерфейсов;
  - перекличек;
  - управления заявками;
- сайт `robochi.work` **не участвует** в системной логике mini app, кроме перехода пользователя в бот / mini app;
- большие анкеты Рабочего и Заказчика в старом виде решено убрать;
- хранить нужно **минимальный набор данных**:
  - Telegram ID,
  - имя (full_name из first_name + last_name Telegram),
  - username,
  - телефон,
  - роль,
  - город / города,
  - пол для Рабочего;
- один Telegram ID = одна роль;
- смена роли — только через админку;
- Рабочий выбирает один город / один канал;
- тестовую оплату Telegram решено убрать;
- как целевую оплату зафиксировали **monobank**, но реализация ещё не сделана.

### 1.3. Зафиксированный пользовательский сценарий входа
Последняя согласованная и **работающая** цель UX (подтверждено тестами 10.03.2026):

1. `/start` в боте;
2. при необходимости — запрос телефона через `request_contact`;
3. сообщение "Ласкаво просимо! Натисніть кнопку щоб відкрити кабінет:" с кнопкой WebApp;
4. переход в WebApp (с промежуточным окном Telegram о переходе в мини-приложение);
5. шаги wizard:
   - `role` (выбор Роботодавець / Працівник)
   - `city` (выбор города)
   - `agreement` (страница правил / договора);
6. после нажатия "Продовжити" на agreement — **прямой переход в личный кабинет** (index `/`), без промежуточных сообщений в бот.

### 1.4. Архитектурная идея проекта

- **Django** — backend, auth, templates, admin;
- **Telegram Bot API / pyTelegramBotAPI (TeleBot)** — бот и webhook;
- **Telegram WebApp JS API** — вход в mini app;
- **PostgreSQL** — БД;
- **Celery** + **Redis** (брокер, `redis://localhost:6379/0`) — фоновые задачи, ротация и служебная логика;
- **Gunicorn + Nginx + systemd** — production;
- **WhiteNoise** — раздача статики;
- **django-formtools** — wizard;
- **django-parler** — мультиязычность;
- **Sentry** — мониторинг ошибок;
- **monobank** — как будущая интеграция оплаты.

### 1.5. Что важно понимать про текущее состояние
Проект находится **между проектированием и стабилизацией**:

- часть архитектуры уже зафиксирована в новом ТЗ;
- часть кода уже существует и работает;
- основной flow (start → phone → wizard → dashboard) **работает** (подтверждено 10.03.2026);
- при этом ряд устаревших страниц и форм остаются в коде и требуют удаления;
- в нескольких местах есть противоречие между:
  - тем, как проект **должен** работать по новому ТЗ;
  - тем, как он **реально** устроен сейчас в коде.

---

## 2. Финальная структура файлов

```text
/home/webuser/robochi_bot/
├── deploy.sh
├── .gitignore
├── .env
├── .env.example
├── .env.local
├── manage.py
├── docs/
│   └── PROJECT_CONTEXT.md
├── config/
│   ├── __init__.py
│   ├── wsgi.py
│   ├── urls.py
│   ├── django/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── production.py
│   └── settings/
│       ├── __init__.py
│       ├── celery.py
│       ├── sentry.py
│       └── telegram_bot.py
├── telegram/
│   ├── urls.py
│   ├── views.py
│   ├── utils.py
│   ├── models.py
│   ├── admin.py
│   ├── admin_actions.py
│   ├── choices.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── bot_instance.py
│   │   ├── common.py
│   │   ├── utils.py
│   │   ├── messages/
│   │   │   └── commands.py
│   │   └── contact/
│   │       └── user_phone_number.py
│   ├── service/
│   │   ├── common.py
│   │   └── ...
│   ├── media/
│   │   ├── Договір оферти.docx
│   │   └── Політика конфіденційності.docx
│   └── templates/
│       └── telegram/
│           └── check.html
├── work/
│   ├── urls.py
│   ├── forms.py
│   ├── models.py
│   ├── choices.py
│   ├── views/
│   │   ├── __init__.py
│   │   ├── index.py
│   │   └── work_profile.py
│   ├── blocks/
│   │   ├── base.py
│   │   ├── registry.py
│   │   └── implementations/
│   │       ├── active_vacancies_preview.py
│   │       ├── channel_preview.py
│   │       └── vacancy_create_form.py
│   ├── service/
│   │   ├── events.py
│   │   ├── publisher.py
│   │   ├── subscriber_setup.py
│   │   ├── complete_user_work_profile_observer.py
│   │   └── work_profile.py
│   └── templates/
│       └── work/
│           ├── index.html
│           ├── includes/
│           │   ├── header.html
│           │   └── channel_preview.html
│           ├── blocks/
│           │   ├── active_vacancies_preview.html
│           │   ├── channel_preview.html
│           │   └── vacancy_create_form.html
│           └── work_profile/
│               ├── role.html
│               ├── step_city.html
│               ├── step_agreement.html
│               ├── steps.html
│               └── work_profile.html  # УСТАРЕВШИЙ — подлежит удалению
├── user/
│   ├── models.py
│   ├── forms.py
│   ├── views.py
│   ├── middleware.py
│   ├── admin.py
│   └── choices.py
├── city/
│   ├── models.py
│   └── admin.py
├── vacancy/
│   ├── urls.py
│   ├── views.py
│   ├── forms.py
│   ├── models.py
│   ├── choices.py
│   └── services/
│       └── observers/
│           ├── publisher.py
│           └── subscriber_setup.py
├── service/
│   ├── common.py
│   ├── notifications.py
│   ├── notifications_impl.py
│   ├── telegram_markup_factory.py
│   ├── telegram_strategies.py
│   ├── telegram_strategy_factory.py
│   └── broadcast_service.py
├── templates/
│   ├── base.html
│   ├── admin/
│   │   └── login.html
│   └── includes/
│       ├── messages.html
│       └── terms_link.html
├── static/
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── telegram.js
│       └── menu.js
├── staticfiles/
└── gunicorn.sock
```

### 2.1. Важные внешние файлы production
```text
/etc/systemd/system/gunicorn.service
/etc/robochi_bot.env
```

### 2.2. Важные замечания по структуре
1. **Два дерева настроек**: `config/django/*` (base, production, local) и `config/settings/*` (celery, sentry, telegram_bot).
2. **Путь check.html**: `telegram/templates/telegram/check.html`.
3. **JS файлы**: `static/js/telegram.js` и `static/js/menu.js` подключаются в base.html, но из-за `.gitignore` (`*.js`) могли не попадать в git.

---

## 3. Актуальный код ключевых файлов

> Файлы, изменённые в сессии 10.03.2026, помечены **[ОБНОВЛЕНО 10.03.2026]**.
> Файлы без изменений помечены как **[БЕЗ ИЗМЕНЕНИЙ]** — их код см. в репозитории.

### 3.1. `telegram/utils.py` [ОБНОВЛЕНО 10.03.2026]
Добавлена `_build_full_name()`, обновлена `get_or_create_user()` — сохраняет `full_name`, `telegram_id` при создании; обновляет `username`, `full_name` при каждом `/start`.

```python
import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Any
from urllib.parse import parse_qsl
from django.conf import settings
from user.models import User

logger = logging.getLogger(__name__)

def check_webapp_signature(init_data: str) -> tuple[bool, Optional[int]]:
    user_id = None
    try:
        parsed_data = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return False, user_id
    if "hash" not in parsed_data:
        return False, user_id
    hash_ = parsed_data.pop("hash")
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed_data.items())
    )
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=settings.TELEGRAM_BOT_TOKEN.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    calculated_hash = hmac.new(
        key=secret_key.digest(),
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    if calculated_hash != hash_:
        return False, user_id
    auth_date = parsed_data.get("auth_date")
    if not auth_date:
        return False, user_id
    if time.time() - int(auth_date) > 86400:
        logger.warning("WEBAPP AUTH initData expired, auth_date=%s", auth_date)
        return False, user_id
    if "user" in parsed_data:
        user_id = json.loads(parsed_data["user"])["id"]
    return True, user_id

def _build_full_name(first_name: str = '', last_name: str = '') -> str:
    parts = [p for p in (first_name or '', last_name or '') if p.strip()]
    return ' '.join(parts) or None

def get_or_create_user(user_id: int, **kwargs: dict[str, Any]) -> tuple[User, bool]:
    created = False
    full_name = _build_full_name(kwargs.get('first_name', ''), kwargs.get('last_name', ''))
    try:
        logger.debug(f'get user {user_id}')
        user = User.objects.get(id=user_id)
        update_fields = []
        new_username = kwargs.get('username')
        if new_username and user.username != new_username:
            user.username = new_username
            update_fields.append('username')
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            update_fields.append('full_name')
        if not user.telegram_id:
            user.telegram_id = user_id
            update_fields.append('telegram_id')
        if update_fields:
            user.save(update_fields=update_fields)
            logger.info(f'Updated user {user_id} fields: {update_fields}')
    except User.DoesNotExist:
        try:
            logger.debug(f'user {user_id} does not exist')
            user = User(id=user_id, telegram_id=user_id, username=kwargs.get('username'), full_name=full_name)
            user.save()
            created = True
            logger.info(f'Create new user {user}')
        except Exception as ex:
            logger.error(f'failed to create new user {user_id} {ex=}')
            user = User(id=user_id)
            user.save()
    return user, created
```

### 3.2. `telegram/handlers/utils.py` [ОБНОВЛЕНО 10.03.2026]
В декораторе `user_required` теперь передаются `first_name`, `last_name`:
```python
user_kwargs = {
    'first_name': getattr(query.from_user, 'first_name', ''),
    'last_name': getattr(query.from_user, 'last_name', ''),
    'username': query.from_user.username,
}
user, created = get_or_create_user(user_id=query.from_user.id, **user_kwargs)
```
Полный файл см. в репозитории.

### 3.3. `telegram/handlers/messages/commands.py` [ОБНОВЛЕНО 10.03.2026]
Ключевое изменение — `default_start` ведёт на `/` вместо `/work/profile/`:
```python
@user_required
def default_start(message: Message, user: User, **kwargs):
    bot = get_bot()
    try:
        next_path = '/' if user.work_profile.is_completed else '/work/wizard/'
    except Exception:
        next_path = '/wizard/'
    check_url = reverse('telegram:telegram_check_web_app')
    url = settings.BASE_URL.rstrip('/') + check_url + '?' + urlencode({'next': next_path})
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(_('Відкрити кабінет'), web_app=types.WebAppInfo(url=url)))
    bot.send_message(message.chat.id, _('Ласкаво просимо! Натисніть кнопку щоб відкрити кабінет:'), reply_markup=markup)
```
Полный файл см. в репозитории.

### 3.4. `work/views/work_profile.py` [ОБНОВЛЕНО 10.03.2026]
Ключевые изменения:
- `TEMPLATES['role']` → `'work/work_profile/role.html'` (было `step_city.html`)
- `done()` → `redirect('/')` (было `redirect('work:work_profile_detail')`)
- `questionnaire_redirect` → финальный redirect на `/`
- `work_profile_detail` помечен как УСТАРЕВШИЙ

```python
TEMPLATES = {
    'role': 'work/work_profile/role.html',
    'city': 'work/work_profile/step_city.html',
    'agreement': 'work/work_profile/step_agreement.html',
}
```
Полный файл см. в репозитории.

### 3.5. `work/service/complete_user_work_profile_observer.py` [ОБНОВЛЕНО 10.03.2026]
Было: вызывал `default_start(None)` → AttributeError. Стало: no-op logger.
```python
class UserWorkProfileCompleteObserver(Observer):
    def update(self, event: str, data: dict[str, Any]) -> None:
        user = data.get('user')
        if user:
            logger.info(f'Work profile completed for user {user.id}')
```

### 3.6. `work/templates/work/work_profile/step_agreement.html` [ОБНОВЛЕНО 10.03.2026]
Было: невалидный UTF-8, мусор в кнопке. Стало: чистый UTF-8, кнопка `{% trans "Continue" %}`.
Полный файл см. в репозитории.

### 3.7–3.28. Файлы без изменений [БЕЗ ИЗМЕНЕНИЙ]
Все остальные файлы (`config/*`, `telegram/views.py`, `telegram/handlers/bot_instance.py`, `telegram/handlers/contact/user_phone_number.py`, `telegram/admin_actions.py`, `check.html`, `work/urls.py`, `work/forms.py`, `user/models.py`, `templates/base.html`, `static/css/styles.css`, `.env*`, `gunicorn.service`) — без изменений по сравнению с предыдущей версией контекста. Код см. в репозитории или в git history (commit до `5c0ee0e`).

---

## 4. Данные в базе (снимок 10.03.2026)

### 4.1. Города (City)
| id | name |
|----|------|
| 1  | Київ |
| 2  | Одеса |
| 3  | Дніпро |
| 4  | Харків |

### 4.2. Каналы (Channel)
| id | title | city_id | active | admin | invite_link |
|----|-------|---------|--------|-------|-------------|
| -1002673104270 | Робота у Харкові | 4 | True | True | https://t.me/+zg7P6NopMXEyNGRi |
| -1002839707201 | Робота в Одесі | 2 | True | True | https://t.me/+DDcwFRDUvcpmOGVi |
| -1002840488729 | Робота у Дніпрі | 3 | True | True | **None** |

**Проблемы:**
- **Київ (city_id=1)** — канала нет. Нужно создать.
- **Дніпро (city_id=3)** — канал есть, но `invite_link=None`. Нужно добавить.
- `ChannelPreviewBlock` фильтрует по `invite_link__isnull=False` → для этих городов кабинет пустой.

### 4.3. Какие данные сохраняются о пользователе
При `/start` из Telegram:
- `User.id` = Telegram user ID (primary key)
- `User.telegram_id` = Telegram user ID (дублирует id)
- `User.username` = Telegram username (обновляется при каждом /start)
- `User.full_name` = first_name + last_name из Telegram (обновляется при каждом /start)

При отправке контакта:
- `User.phone_number` = номер телефона

Через wizard:
- `UserWorkProfile.role` = employer/worker
- `UserWorkProfile.city` = выбранный город
- `UserWorkProfile.agreement_accepted` = True
- `UserWorkProfile.is_completed` = True

Поля НЕ заполняемые автоматически:
- `User.gender` — NULL
- `User.birth_year` — NULL
- `UserWorkProfile.phone_number` — NULL (дубль User.phone_number, не используется)

### 4.4. Личный кабинет (index `/`)
Блоки через `block_registry`:
- `ChannelPreviewBlock` (order=1) — канал города с кнопкой "Відкрити"
- `VacancyCreateFormBlock` — форма создания вакансии (только Employer)
- `ActiveVacanciesPreviewBlock` — активные вакансии

### 4.5. AgreementText
Тексты не добавлены в admin. Нужна схема с разными соглашениями для employer/worker.
Проблема: `get_context_data` ищет по `profile.role`, но role ещё не в базе на шаге agreement.

---

## 5. Полный технический стек

- **Python 3.11**, **Django**, django-formtools, django-parler, WhiteNoise, python-dotenv
- **pyTelegramBotAPI** / telebot, Telegram WebApp JS API, Webhook
- **PostgreSQL**, **Celery** + **Redis** (`redis://localhost:6379/0`)
- **Gunicorn** (unix socket, 1 worker) + **Nginx** + **systemd**
- **Sentry**, Django logging → journalctl
- **Домен**: robochi.pp.ua, **VPS**: Fornex
- **Платежи**: monobank (не реализовано)

---

## 6. Что реализовано и работает

### 6.1. Работающий flow (подтверждено 10.03.2026)
1. `/start` → запрос телефона → сохранение данных из Telegram
2. Кнопка "Відкрити кабінет" → WebApp → auth → login
3. Wizard: role → city → agreement → redirect `/` (dashboard)
4. Личный кабинет с блоками по ролям

### 6.2. Production
- gunicorn.service стабильно работает
- Webhook обрабатывает update'ы
- Sentry мониторит ошибки

---

## 7. Что не завершено

### 7.1. По продукту
1. Отзывы и рейтинги — отложены.
2. Этапы реализации — не написаны.
3. Схема ротации не собрана.
4. Тексты agreement не добавлены.

### 7.2. По коду
1. **Удалить устаревшее**: `work_profile_detail`, `ContactForm`, `work_profile.html`, URL `/work/profile/`.
2. **Agreement**: брать role из wizard data, а не из базы.
3. **Каналы**: нет канала для Києва, нет invite_link для Дніпро.
4. **monobank** — не реализован.
5. `UserWorkProfile.phone_number` — дубль, не используется.

### 7.3. По infrastructure
1. `deploy.sh` — доработать.
2. `/etc/robochi_bot.env` — доступ только через sudo.
3. `.gitignore` — глобально игнорирует `*.css` и `*.js`.

### 7.4. По качеству
1. Нет тестов.
2. Баг смешивания аккаунтов — не подтверждено исправление.
3. Скомпрометированные токены — нужно перевыпустить.

---

## 8. Известные проблемы

1. **Два дерева настроек** — `config/django/*` и `config/settings/*`.
2. **User.id = telegram_id** — дублирование, но работает.
3. **Устаревший код** — ContactForm, work_profile_detail ещё в проекте.
4. **Смешивание аккаунтов** — `session.flush()` не подтверждено.
5. **Кодировка** — битые символы в admin_actions (`вњ…`, `вљ пёЏ`).
6. **Безопасность** — BOT_TOKEN попадал в логи.

---

## 9. Исправлено

### 9.1. Сессия 09.03.2026 (ChatGPT)
1. Импорты Telegram-части (get_bot, bot, commands).
2. deploy.sh (ветка develop, venv/bin/).
3. TELEGRAM_WEBHOOK_SECRET в /etc/robochi_bot.env.
4. Кодировка check.html.

### 9.2. Сессия 09–10.03.2026 (Claude)
1. Кодировка `step_agreement.html` — UTF-8 (была причина 500).
2. TEMPLATES: role → `role.html` (было `step_city.html`).
3. `__init_.py` → `__init__.py` (опечатка).
4. Observer: убран `default_start(None)` → no-op logger.
5. Redirect после wizard: `/` вместо `/work/profile/`.
6. Сохранение данных Telegram: full_name, telegram_id, обновление username.
7. Кнопка "Відкрити кабінет": `/` вместо `/work/profile/`.
8. Коммит `5c0ee0e` в develop.

---

## 10. Следующие шаги

### Приоритет 1 — Данные в admin
1. Создать канал для Києва.
2. Добавить invite_link для Дніпро.
3. Создать AgreementText для employer и worker.

### Приоритет 2 — Удалить устаревший код
1. `work_profile_detail` view + URL.
2. `ContactForm`, `CitySelectForm`.
3. Шаблон `work_profile.html`.

### Приоритет 3 — Исправить agreement
1. Брать role из `self.get_cleaned_data_for_step('role')`.

### Приоритет 4 — Ротация
### Приоритет 5 — monobank
### Приоритет 6 — Стабилизация (токены, deploy.sh, тесты)

---

## Итог

Проект `robochi_bot` имеет работающую основу: Telegram-бот, WebApp-авторизацию, wizard (role → city → agreement → dashboard) и production на Django. Flow подтверждён тестами 10.03.2026. Ближайшие задачи — данные в admin (каналы, agreement), удаление устаревшего кода, затем ротация и monobank.
