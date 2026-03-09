
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
  - имя,
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
Последняя согласованная цель UX:

1. `/start` в боте;
2. при необходимости — запрос телефона через `request_contact`;
3. переход в WebApp;
4. шаги wizard:
   - `role`
   - `city`
   - `agreement` (страница правил / договора);
5. далее — личный кабинет.

### 1.4. Архитектурная идея проекта
По отчётам проект строится вокруг такой схемы:

- **Django** — backend, auth, templates, admin;
- **Telegram Bot API / pyTelegramBotAPI (TeleBot)** — бот и webhook;
- **Telegram WebApp JS API** — вход в mini app;
- **PostgreSQL** — БД;
- **Celery** + брокер (`Redis` или `RabbitMQ`, точное текущее значение не подтверждено) — фоновые задачи, ротация и служебная логика;
- **Gunicorn + Nginx + systemd** — production;
- **WhiteNoise** — раздача статики;
- **django-formtools** — wizard;
- **django-parler** — мультиязычность;
- **Sentry** — по конфигам присутствует;
- **monobank** — как будущая интеграция оплаты.

### 1.5. Что важно понимать про текущее состояние
Проект находится **между проектированием и стабилизацией**:

- часть архитектуры уже зафиксирована в новом ТЗ;
- часть кода уже существует и работает хотя бы частично;
- при этом прод, env, auth-flow, импортная схема Telegram-части и ряд файлов остаются нестабильными;
- в нескольких местах есть противоречие между:
  - тем, как проект **должен** работать по новому ТЗ;
  - тем, как он **реально** устроен сейчас в коде.

---

## 2. Финальная структура файлов

Ниже — **последняя известная структура по отчётам**, а не полный гарантированный tree всего репозитория.

```text
/home/webuser/robochi_bot/
├── deploy.sh
├── .gitignore
├── .env
├── .env.example
├── .env.local
├── manage.py
├── config/
│   ├── __init__.py
│   ├── wsgi.py
│   ├── urls.py
│   ├── django/
│   │   ├── base.py
│   │   └── production.py
│   └── settings/
│       ├── __init__.py
│       ├── sentry.py
│       └── telegram_bot.py
├── telegram/
│   ├── urls.py
│   ├── views.py
│   ├── utils.py
│   ├── admin_actions.py
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
│   │   └── work_profile.py
│   └── templates/
│       └── work/
│           └── work_profile/
│               ├── step_city.html
│               ├── step_agreement.html
│               ├── steps.html
│               └── work_profile.html
├── user/
│   ├── models.py
│   ├── middleware.py
│   └── choices.py
├── city/
│   └── models.py
├── vacancy/
│   └── services/
├── service/
│   ├── notifications.py
│   └── telegram_strategy_factory.py
├── templates/
│   ├── base.html
│   ├── includes/
│   │   └── messages.html
│   └── work/
│       └── includes/
│           └── header.html
├── static/
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── telegram.js      # в шаблонах подключается, но в git мог отсутствовать
│       └── menu.js          # в шаблонах подключается, но в git мог отсутствовать
├── staticfiles/             # генерируемый collectstatic-артефакт, на сервере чистился
└── gunicorn.sock
```

### 2.1. Важные внешние файлы production
```text
/etc/systemd/system/gunicorn.service
/etc/robochi_bot.env
```

### 2.2. Важные замечания по структуре
1. В проекте фигурируют **два дерева настроек**:
   - `config/django/*`
   - `config/settings/*`

   Это признано источником путаницы.

2. В отчётах встречалась путаница по пути шаблона `check.html`:
   - `telegram/templates/telegram/check.html`
   - `templates/telegram/check.html`

   **Последний известный путь по develop-отчёту:** `telegram/templates/telegram/check.html`.

3. В шаблоне `templates/base.html` подключаются:
   - `static/js/telegram.js`
   - `static/js/menu.js`

   Но из-за `.gitignore` эти исходники могли **не попадать в git**.

---

## 3. Весь актуальный код (последние версии файлов)

> Ниже — **только тот код, который удалось восстановить из отчётов**.
>  
> Это не весь код проекта целиком, а весь **последний известный код по упомянутым файлам**.
>  
> Где последняя ветка содержала только изменение, а не полный файл, это отмечено отдельно.

### 3.1. `deploy.sh`
Последняя известная полная версия — из отчёта по ветке про наведение порядка / develop.

```bash
#!/bin/bash
cd ~/robochi_bot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py compilemessages
systemctl restart gunicorn
systemctl restart celery-worker
systemctl restart celery-beat
```

---

### 3.2. `.gitignore`
Последняя известная полная версия — из develop-отчёта.

```gitignore
# Python/Django
__pycache__/
*.py[cod]
*.egg-info/
*.log
*.sqlite3
.env
.env.*
!.env.example

# Venv
venv/

# Django collectstatic (если используешь)
staticfiles/
# Юзерский медиа-контент (если он генерится пользователями)
media/

# IDE
.vscode/
.idea/
.DS_Store

# Тесты/линтеры
.coverage
coverage.xml
.pytest_cache/
.mypy_cache/

/staticfiles/
/venv/
/__pycache__/
/*.pyc
*.gz
*.css
*.js
gitignore.save
fix-user-models.patch
!static/css/styles.css
```

---

### 3.3. `config/settings/telegram_bot.py`
Последняя известная полная версия — более поздний строгий вариант из ветки восстановления запуска.

```python
import os

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
if ":" not in TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing or invalid (must contain a colon)")

PROVIDER_TOKEN = (os.getenv("PROVIDER_TOKEN") or "").strip()

# Секретный хвост для webhook URL (НЕ из токена)
TELEGRAM_WEBHOOK_SECRET = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
if not TELEGRAM_WEBHOOK_SECRET:
    raise ValueError("TELEGRAM_WEBHOOK_SECRET is not set")
```

---

### 3.4. `config/django/base.py`
Последняя известная полная версия — поздний валидный вариант из ветки восстановления запуска.

```python
import os
from pathlib import Path

from django.urls import reverse_lazy
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = False

ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    'whitenoise.runserver_nostatic',

    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'formtools',
    'parler',
    'user',
    'telegram',
    'vacancy',
    'work',
    'city',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'user.middleware.UserLanguageMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRESQL_NAME'),
        'USER': os.getenv('POSTGRESQL_USER'),
        'PASSWORD': os.getenv('POSTGRESQL_PASSWORD'),
        'HOST': os.getenv('POSTGRESQL_HOST'),
        'PORT': os.getenv('POSTGRESQL_PORT'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

AUTH_USER_MODEL = 'user.User'

# Internationalization
TIME_ZONE = 'Europe/Kiev'
USE_I18N = True
USE_TZ = True
USE_L10N = True
LANGUAGE_CODE = 'uk'
LANGUAGES = [
    ('ru', 'Р СѓСЃСЃРєРёР№'),
    ('uk', 'РЈРєСЂР°С—РЅСЃСЊРєР°'),
]
PARLER_DEFAULT_LANGUAGE_CODE = LANGUAGE_CODE
PARLER_LANGUAGES = {
    None: tuple({'code': l[0]} for l in LANGUAGES),
}
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Static files
STATIC_HOST = os.environ.get('DJANGO_STATIC_HOST', '')
STATIC_URL = STATIC_HOST + '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
    'default': {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}
WHITENOISE_KEEP_ONLY_HASHED_FILES = True

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
    'loggers': {
        'telebot': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        # если хочешь именно твои сообщения:
        'telegram': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

LOGIN_URL = reverse_lazy('telegram:telegram_check_web_app')

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
from config.settings.sentry import *
from config.settings.telegram_bot import *
```

---

### 3.5. `config/django/production.py`
Последняя известная полная версия.

```python
import os
from .base import *


DEBUG = False
HOST = os.getenv('HOST')
ALLOWED_HOSTS = [HOST, f"www.{HOST}"]
CSRF_TRUSTED_ORIGINS = [
    f'https://{HOST}',
    f'https://www.{HOST}',
]

BASE_URL: str = f'https://{HOST}'
if not HOST:
    raise ValueError('Please set the HOST environment variable')

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "None"
```

---

### 3.6. `config/wsgi.py`
Последняя известная полная версия.

```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "config.django.production"),
)

application = get_wsgi_application()
```

---

### 3.7. `manage.py`
Последняя известная полная версия.

```python
import os
import sys


def main():
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        os.getenv("DJANGO_SETTINGS_MODULE", "config.django.production"),
    )

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
```

---

### 3.8. `telegram/urls.py`
Последняя известная полная версия — схема с `TELEGRAM_WEBHOOK_SECRET`.

```python
from django.conf import settings
from django.urls import path
from . import views

app_name = "telegram"

urlpatterns = [
    path(f"webhook-{settings.TELEGRAM_WEBHOOK_SECRET}/", views.telegram_webhook, name="telegram_webhook"),
    path("check-web-app/", views.check, name="telegram_check_web_app"),
    path("authenticate-web-app/", views.authenticate_web_app, name="telegram_authenticate_web_app"),
]
```

---

### 3.9. `telegram/utils.py`
Последняя известная полная версия — из develop-отчёта.

```python
import hashlib
import hmac
import json
import logging
from operator import itemgetter
from typing import Optional, Any
from urllib.parse import parse_qsl
from django.conf import settings

from user.models import User


logger = logging.getLogger(__name__)

def check_webapp_signature(init_data: str) -> tuple[bool, Optional[int]]:
    """
    Check incoming WebApp init data signature
    Source: https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    """
    user_id = None

    try:
        parsed_data = dict(parse_qsl(init_data))
    except ValueError:
        return False, user_id

    if "hash" not in parsed_data:
        return False, user_id

    hash_ = parsed_data.pop('hash')
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed_data.items(), key=itemgetter(0))
    )

    secret_key = hmac.new(
        key=settings.TELEGRAM_BOT_TOKEN.encode("utf-8"),
        msg=b"WebAppData",
        digestmod=hashlib.sha256,
    )
    calculated_hash = hmac.new(
        key=secret_key.digest(),
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


    result = calculated_hash == hash_

    if result:
        user_id = json.loads(parsed_data['user'])['id']

    return result, user_id


def get_or_create_user(user_id: int, **kwargs: dict[str, Any]) -> tuple[User, bool]:
    created = False
    try:
        logger.debug(f'get user {user_id}')
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        try:
            logger.debug(f'user {user_id} does not exist')
            user = User(
                id=user_id,
                **kwargs,
            )
            user.save()
            created = True
            logger.info(f'Create new user {user}')
        except Exception as ex:
            logger.error(f'failed to create new user {user_id} {ex=}')
            user = User(
                id=user_id,
            )
            user.save()

    return user, created
```

---

### 3.10. `telegram/views.py`
Ниже — **реконструированная последняя известная версия**:

- за основу взята последняя полная версия из develop-отчёта;
- поверх неё применено **более позднее изменение** из ветки про смешивание аккаунтов:
  - при конфликте пользователя в сессии предлагается `request.session.flush()` вместо `logout(request)`.

> Важно: эту полную итоговую версию **не удалось подтвердить инструментально** по реальному файлу.  
> Это **лучшее восстановление последнего известного состояния** по отчётам.

```python
import json
import logging
from urllib.parse import unquote

from django.contrib.auth import login
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.handlers.wsgi import WSGIRequest
from django.views.decorators.csrf import csrf_exempt

import telebot

from telegram.handlers.bot_instance import get_bot
from telegram.handlers.bot_instance import bot, load_handlers_once
from .utils import check_webapp_signature, get_or_create_user

logger = logging.getLogger(__name__)


def check(request: WSGIRequest) -> HttpResponse:
    return render(request, "telegram/check.html")


def authenticate_web_app(request: WSGIRequest):
    init_data = request.GET.get("init_data", "")
    next_path = unquote(request.GET.get("next", "/"))

    logger.warning(
        "WEBAPP AUTH HIT path=%s host=%s secure=%s",
        request.path,
        request.get_host(),
        request.is_secure(),
    )
    logger.warning(
        "WEBAPP AUTH query next(raw)=%r next(decoded)=%r init_data_len=%s",
        request.GET.get("next"),
        next_path,
        len(init_data or ""),
    )

    logger.warning("WEBAPP AUTH allowed_hosts=%s", {request.get_host()})

    if not url_has_allowed_host_and_scheme(
        url=next_path,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_path = "/"

    is_valid, user_id = check_webapp_signature(init_data)
    logger.warning("WEBAPP AUTH signature is_valid=%s user_id=%s", is_valid, user_id)

    if is_valid and user_id:
        # user_id = Telegram user id. В нашей системе он хранится в User.telegram_id.
        if request.user.is_authenticated:
            current_tid = getattr(request.user, "telegram_id", None)
            if current_tid and current_tid != user_id:
                request.session.flush()

        user, _ = get_or_create_user(user_id=user_id)

        logger.warning("WEBAPP AUTH logging-in telegram_user_id=%s user_pk=%s", user_id, user.pk)
        login(request, user)
        return redirect(next_path)

    admin_login_url = reverse("admin:login")
    return redirect(f"{admin_login_url}?next={next_path}")


@csrf_exempt
def telegram_webhook(request: WSGIRequest) -> HttpResponse:
    logger.warning(
        "WEBHOOK HIT method=%s path=%s len=%s",
        request.method,
        request.path,
        len(request.body or b""),
    )

    if request.method != "POST":
        return HttpResponse("Only POST allowed", status=405)

    try:
        json_str = request.body.decode("utf-8")
        update = telebot.types.Update.de_json(json_str)

        b = get_bot()
        logger.warning(
            "BOT HANDLERS: message=%s callback=%s",
            len(getattr(b, "message_handlers", []) or []),
            len(getattr(b, "callback_query_handlers", []) or []),
        )

        b.process_new_updates([update])

    except Exception:
        logger.exception("Webhook processing failed. body=%r", (request.body[:200] if request.body else b""))
        # Telegram должен получить 200
        return HttpResponse("ok")

    return HttpResponse("ok")

    return HttpResponse("ok")
```

---

### 3.11. `telegram/handlers/bot_instance.py`
Последняя известная полная версия по develop-отчёту.

```python
import logging
import telebot
from django.conf import settings

logger = logging.getLogger(__name__)

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN, parse_mode="HTML")

_handlers_loaded = False

def load_handlers_once():
    global _handlers_loaded
    if _handlers_loaded:
        return
    _handlers_loaded = True

    # импортируй тут модули с хендлерами ЯВНО, без walk_packages
    # (это убирает непредсказуемые циклы)
    from telegram.handlers.messages import commands  # noqa
    from telegram.handlers.messages import info  # noqa
    # добавь остальные handler-модули аналогично
```

> Важно: по другим отчётам существовал более ранний альтернативный вариант этого файла через `get_bot()` и автозагрузку handlers.  
> Но **более поздний зафиксированный develop-снимок** выше — именно этот, хотя он и конфликтует с другими файлами.

---

### 3.12. `telegram/handlers/messages/commands.py`
Последняя известная полная версия по develop-отчёту.

```python
import base64
import json
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot import types
from urllib.parse import urlencode

from telebot.types import Message, InlineKeyboardMarkup, CallbackQuery, ReplyKeyboardMarkup, InlineKeyboardButton, \
    WebAppInfo

from service.notifications import NotificationMethod
from telegram.handlers.common import CallbackStorage as Storage
from telegram.handlers.bot_instance import get_bot
from telegram.handlers.utils import user_required
from telegram.handlers.common import ButtonStorage, F, CallbackStorage
from vacancy.services.observers.subscriber_setup import telegram_notifier
from work.choices import WorkProfileRole
from user.models import User


@user_required
def choose_role(message: Message, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    markup.add(ButtonStorage.work_role(label=str(WorkProfileRole.WORKER.label), role=WorkProfileRole.WORKER.value))
    markup.add(ButtonStorage.work_role(label=str(WorkProfileRole.EMPLOYER.label), role=WorkProfileRole.EMPLOYER.value))

    get_bot().send_message(
        message.chat.id,
        'Вас вітає сервіс\nrobochi.work\nОбираите\nЯ ЗАМОВНИК\nта знаходьте будь яку кількість\nпрацівників швидко та зручно!\nАбо обираите\nЯ ПРАЦІВНИК\nта знаходьте підробіток\nколи зручно!\n',
        reply_markup=markup,
    )
@user_required
def fill_work_account(message: Message, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    next_path = reverse('work:wizard')
    check_url = reverse('telegram:telegram_check_web_app')
    url = settings.BASE_URL.rstrip('/') + check_url + '?' + urlencode({'next': next_path})
    markup.add(ButtonStorage.web_app(label=_('Fill out the form'), url=url))
    get_bot().send_message(message.chat.id, text=_('You must fill out a work form'), reply_markup=markup)

@user_required
def ask_phone(message: Message, user: User):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton(_('Send phone number'), request_contact=True))

    telegram_notifier.notify(
        recipient=SimpleNamespace(chat_id=message.chat.id, ),
        method=NotificationMethod.TEXT,
        text=_('It is necessary to send your phone number, use the button below'),
        reply_markup=markup,
    )

@user_required
def default_start(message: Message | None, user: User, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    markup.add(ButtonStorage.web_app())
    markup.add(ButtonStorage.menu(menu_name='info', label=_('Info')))

    if user.is_staff:
        markup.add(
            ButtonStorage.web_app(
                label=_('Admin panel'), url=settings.BASE_URL.rstrip('/') + reverse('admin:index')
            )
        )

    text = _('Hello')

    message_common_settings = {
        'chat_id': message.chat.id,
        'reply_markup': markup,
        'parse_mode': 'HTML',
    }

    get_bot().send_message(
        text=text,
        **message_common_settings,
    )

def decode_start_param(encoded: str) -> dict:
    """Декодирование safe Base64 в словарь"""
    padding = "=" * (-len(encoded) % 4)  # Восстанавливаем "="
    decoded_str = base64.urlsafe_b64decode(encoded + padding).decode()
    return json.loads(decoded_str)

def process_start_payload(payload: str, message) -> bool:
    try:
        data = decode_start_param(payload)

        if data.get("type") == 'feedback':
            url = settings.BASE_URL.rstrip('/') + reverse('vacancy:feedback', kwargs={'pk': data.get("vacancy_id")})
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    text=_('Open'),
                    web_app=WebAppInfo(url=url)
                )
            )
            get_bot().send_message(
                message.chat.id,
                text=_('Send feedback'),
                reply_markup=markup
            )
            return True

        elif data.get("type") == 'info':
            send_info(message)
            return True
        else:
            return False

    except Exception as e:
        return False

@bot.message_handler(commands=['start'])
@bot.callback_query_handler(func=F(CallbackStorage.menu.filter(name='start')))
@user_required
def start(query: Message | CallbackQuery, user: User, **kwargs: dict[str, Any]) -> None:
    if isinstance(query, CallbackQuery):
        message = query.message
    else:
        message = query

    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            result = process_start_payload(parts[1], message)
            if result:
                return

    if not user.phone_number:
        ask_phone(message, user=user)
    elif not user.work_profile.is_completed:
        fill_work_account(message, user=user)
    else:
        default_start(message, user=user)


@bot.message_handler(commands=['info'])
@bot.callback_query_handler(func=F(Storage.menu.filter()))
def send_info(message):
    if isinstance(message, CallbackQuery):
        message = message.message

    files = ['telegram/media/Договір оферти.docx', 'telegram/media/Політика конфіденційності.docx', ]
    for file_path in files:
        try:
            with open(file_path, 'rb') as f:

                bot.send_document(
                    chat_id=message.chat.id,
                    document=f,
                )
        except Exception as e:
            ...
```

> Важно: этот код в отчётах отмечен как проблемный, потому что использует `@bot...`, но в показанном `bot_instance.py` функции `get_bot()` вообще нет.

---

### 3.13. `telegram/handlers/contact/user_phone_number.py`
Последняя известная полная версия.

```python
from typing import Any
from django.utils.translation import gettext as _
from telebot import types
from telebot.types import ReplyKeyboardRemove

from telegram.handlers.bot_instance import bot
from telegram.handlers.messages.commands import start
from telegram.handlers.utils import user_required
from user.models import User


@bot.message_handler(content_types=['contact'])
@user_required
def contact(message: types.Message, user: User, **kwargs: dict[str, Any]) -> None:
    if message.contact and message.contact.phone_number:
        user.phone_number = f"+{message.contact.phone_number.lstrip('+')}"
        user.save(update_fields=['phone_number'])
        bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
        )
        bot.send_message(
            chat_id=message.chat.id,
            text=_('Phone number saved'),
            reply_markup=ReplyKeyboardRemove(),
        )
        start(message, user=user)
```

---

### 3.14. `telegram/admin_actions.py`
Последняя известная полная версия — из ветки восстановления запуска.

```python
from django.contrib import admin, messages
from django.core.handlers.wsgi import WSGIRequest
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from service.notifications import NotificationMethod
from service.telegram_strategy_factory import TelegramStrategyFactory
from telegram.handlers.bot_instance import get_bot
from telegram.models import Group, GroupMessage, Channel, ChannelMessage
from telegram.service.channel import ChannelService
from telegram.service.group import GroupService
from telegram.service.message_delete import MessageDeleter, MessageDeleteService, DeleteStats
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter


def display_delete_stats(request: WSGIRequest, stats: DeleteStats) -> None:
    if stats['deleted']:
        messages.success(request, _('вњ… Deleted: %(count)s message(s).') % {'count': stats['deleted']})
    if stats['failed']:
        messages.warning(request, _('вљ пёЏ Failed to delete: %(count)s message(s).') % {'count': stats['failed']})
    if stats['total'] == 0:
        messages.info(request, _('в„№пёЏ No messages to delete.'))


@admin.action(description=_('Delete messages in Telegram'))
def delete_messages_by_group_action(modeladmin, request: WSGIRequest, queryset: QuerySet[Group]):
    deleter = MessageDeleter(get_bot())
    service = MessageDeleteService(deleter)
    stats = service.delete_by_groups(queryset)

    display_delete_stats(request=request, stats=stats)


@admin.action(description=_('Delete messages in Telegram'))
def delete_messages_action(modeladmin, request: WSGIRequest, queryset: QuerySet[GroupMessage]):
    deleter = MessageDeleter(get_bot())
    service = MessageDeleteService(deleter)
    stats = service.delete_messages(queryset)

    display_delete_stats(request=request, stats=stats)

@admin.action(description=_('Update group invite link'))
def update_group_invite_link(modeladmin, request: WSGIRequest, queryset: QuerySet[Group]):
    for group in queryset:
        updated_group = GroupService.update_invite_link(group=group)
        if updated_group:
            messages.success(request, _('Updated invite link'))
        else:
            messages.warning(request, _('вљ пёЏ Failed to update invite link in %(group)s') % {'group': group.title})


@admin.action(description=_('Update channel invite link'))
def update_channel_invite_link(modeladmin, request: WSGIRequest, queryset: QuerySet[Channel]):
    for channel in queryset:
        updated_channel = ChannelService.update_invite_link(channel=channel)
        if updated_channel:
            messages.success(request, _('Updated invite link'))
        else:
            messages.warning(request, _('вљ пёЏ Failed to update invite link in %(channel)s') % {'channel': channel.title})

@admin.action(description=_('Kick users from groups'))
def kick_group_users(modeladmin, request: WSGIRequest, queryset: QuerySet[Group]):
    for group in queryset:
        GroupService.kick_all_users(group=group)

@admin.action(description=_('Set default permissions'))
def set_default_permissions(modeladmin, request: WSGIRequest, queryset: QuerySet[Group]):
    for group in queryset:
        GroupService.set_default_permissions(group=group)
```

---

### 3.15. `telegram/templates/telegram/check.html`
Последняя известная полная версия по develop-отчёту.

```html
{% extends 'base.html' %}
{% block body %}
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script>
document.addEventListener('DOMContentLoaded', () => {
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = tg ? tg.initData : "";
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next") || "/";

  // ВАЖНО: имя параметра должно совпадать с тем, что читает Django: init_data
  const url = "{% url 'telegram:telegram_authenticate_web_app' %}"
    + "?init_data=" + encodeURIComponent(initData)
    + "&next=" + encodeURIComponent(next);

  window.location.replace(url);
});
</script>
{% endblock %}
```

---

### 3.16. `work/urls.py`
Последняя известная полная версия.

```python
from django.urls import path
from django.contrib.auth.decorators import login_required

from work.views.work_profile import (
    questionnaire_redirect,
    ProfileWizard,
    work_profile_detail,
)

app_name = 'work'

urlpatterns = [
    path('profile/', work_profile_detail, name='work_profile_detail'),

    path('wizard/', questionnaire_redirect, name='wizard'),
    path('wizard/<step>/', login_required(ProfileWizard.as_view()), name='wizard_step'),
]
```

---

### 3.17. `work/views/work_profile.py`
Последняя известная полная версия.

```python
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from formtools.wizard.views import SessionWizardView
from django.utils.decorators import method_decorator


from telegram.service.common import get_payload_url
from work.forms import CityForm, ContactForm, CitySelectForm, RoleForm, AgreementForm
from work.models import UserWorkProfile, AgreementText
from work.service.events import WORK_PROFILE_COMPLETED
from work.service.subscriber_setup import work_publisher
from django.utils import timezone

FORMS = [
    ('role', RoleForm),
    ('city', CityForm),
    ('agreement', AgreementForm),
]

TEMPLATES = {
    'role': 'work/work_profile/step_city.html',
    'city': 'work/work_profile/step_city.html',
    'agreement': 'work/work_profile/step_agreement.html',
}

@method_decorator(login_required, name='dispatch')
class ProfileWizard(SessionWizardView):
    form_list = FORMS

    def get_template_names(self):
        return [TEMPLATES[self.steps.current]]

    def get_form_instance(self, step):
        if step == 'city':
            profile, _ = UserWorkProfile.objects.get_or_create(user=self.request.user)
            return profile
        return None

    def get_form_kwargs(self, step):
        return super().get_form_kwargs(step)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)

        if self.steps.current == 'agreement':
            profile, _ = UserWorkProfile.objects.get_or_create(user=self.request.user)
            agreement = AgreementText.objects.filter(role=profile.role).first()
            context['agreement'] = agreement

        return context

    def done(self, form_list, **kwargs):
        data = self.get_all_cleaned_data()
        user = self.request.user

        profile, _ = UserWorkProfile.objects.get_or_create(user=user)

        profile.role = data.get('role')
        profile.city = data.get('city')

        profile.agreement_accepted = True
        profile.agreement_accepted_at = timezone.now()

        profile.is_completed = True

        profile.save(update_fields=[
            'role', 'city',
            'agreement_accepted', 'agreement_accepted_at',
            'is_completed'
        ])

        work_publisher.notify(WORK_PROFILE_COMPLETED, data={'user': user})

        return redirect('work:work_profile_detail')


@login_required
def questionnaire_redirect(request):
    profile, _ = UserWorkProfile.objects.get_or_create(user=request.user)

    if not profile.role:
        return redirect('work:wizard_step', step='role')

    if not profile.city:
        return redirect('work:wizard_step', step='city')

    if not profile.agreement_accepted:
        return redirect('work:wizard_step', step='agreement')

    return redirect('work:work_profile_detail')


@login_required
def work_profile_detail(request):
    user = request.user
    profile, _ = UserWorkProfile.objects.get_or_create(user=user)

    city_form = CitySelectForm(request.POST, instance=profile, prefix='city')
    city_form.fields['city'].disabled = True

    if request.method == 'POST':
        contact_form = ContactForm(request.POST, user=user, prefix='contact')
        if city_form.is_valid() and contact_form.is_valid():
            city_form.save()
            contact_form.save()
            return redirect('work:work_profile_detail')
    else:
        contact_form = ContactForm(user=user, prefix='contact')

    return render(request, 'work/work_profile/work_profile.html', {
        'role': profile.get_role_display(),
        'city_form': city_form,
        'contact_form': contact_form,
    })
```

---

### 3.18. `work/forms.py`
Последняя известная полная версия.

```python
import datetime

from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from city.models import City
from user.choices import USER_GENDER_CHOICES
from .models import UserWorkProfile, WorkProfileRole

User = get_user_model()


class RoleForm(forms.ModelForm):
    ROLE_CHOICES = [
        (
            WorkProfileRole.EMPLOYER,
            _('Employer — looking for workers')
        ),
        (
            WorkProfileRole.WORKER,
            _('Worker — looking for job')
        ),
    ]

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        label=_('Role'),
        initial=WorkProfileRole.WORKER,
    )

    class Meta:
        model = UserWorkProfile
        fields = ['role']


class CityForm(forms.ModelForm):
    city = forms.ModelChoiceField(
        queryset=City.objects.all(),
        widget=forms.RadioSelect,
        label=_('City'),
    )

    class Meta:
        model = UserWorkProfile
        fields = ['city']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['city'].label_from_instance = (
            lambda obj: obj.safe_translation_getter('name', any_language=True)
        )

class CitySelectForm(CityForm):
    city = forms.ModelChoiceField(
        queryset=City.objects.all(),
        widget=forms.Select,
        label=_('City'),
    )


class AgreementForm(forms.Form):
    pass

class ContactForm(forms.Form):
    gender = forms.ChoiceField(
        choices=USER_GENDER_CHOICES,
        label=_('Gender'),
    )
    full_name = forms.CharField(
        max_length=150,
        label=_('How can I contact you?'),
        required=False,
        widget=forms.TextInput(attrs={'placeholder': ''}),
    )
    phone_number = forms.CharField(
        max_length=20,
        label=_('Contact phone number (+380 xx xxx xxxx)'),
        widget=forms.TextInput(
            attrs={
                'placeholder': '+380 00 000 0000',
                'pattern': r'\+380\s?\d{2}\s?\d{3}\s?\d{4}',
                'type': 'tel',
                'value': '+380'
            }
        ),
    )
    birth_year = forms.IntegerField(
        label=_('Year of birth'),
        min_value=1900,
        max_value=datetime.date.today().year,
        widget=forms.NumberInput(attrs={
            'placeholder': _('Enter your year of birth')
        })
    )


    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields['full_name'].initial = user.full_name
            self.fields['birth_year'].initial = user.birth_year
            profile, _ = UserWorkProfile.objects.get_or_create(user=user)
            self.fields['phone_number'].initial = profile.phone_number

    def clean_phone_number(self):
        pn = self.cleaned_data['phone_number'].strip()
        if not pn.startswith('+380'):
            raise forms.ValidationError(_('The number must start with +380'))
        return pn

    def save(self):
        user = self.user
        user.full_name = self.cleaned_data['full_name']
        user.birth_year = self.cleaned_data['birth_year']
        user.save(update_fields=['full_name', 'birth_year', ])

        profile, _ = UserWorkProfile.objects.get_or_create(user=user)
        profile.phone_number = self.cleaned_data['phone_number']
        profile.save(update_fields=['phone_number'])
        return profile
```

---

### 3.19. `work/templates/work/work_profile/step_city.html`
Последняя известная полная версия.

```html
{% extends 'work/work_profile/steps.html' %}
{% load i18n %}

{% block form %}
    <form method="post">
        {% csrf_token %}
        <div class="work_profile step city">
            {{ wizard.management_form }}
            {{ form.as_p }}
            <button type="submit">{% trans 'Continue' %}</button>
        </div>
        <a href="https://t.me/robochi_work_admin/" class="info">{% trans 'If your city is not on the list, write to the administrator' %}</a>
    </form>
{% endblock %}
```

---

### 3.20. `work/templates/work/work_profile/step_agreement.html`
Последняя известная полная версия.

```html
{% extends 'work/work_profile/steps.html' %}
{% load i18n %}

{% block form %}
<form method="post">
  {% csrf_token %}
  <div class="work_profile step agreement">
    {{ wizard.management_form }}

    <div class="info">
      {% if agreement %}
        <h3>{{ agreement.title }}</h3>
        <div class="agreement-text">
          {{ agreement.text|linebreaks }}
        </div>
      {% else %}
        <h3>{% trans "Agreement" %}</h3>
        <div class="agreement-text">
          {% trans "Agreement text is not configured in admin yet." %}
        </div>
      {% endif %}
    </div>

    <button type="submit">{% trans "Ï³äòâåðäæóþ" %}</button>
  </div>
</form>
{% endblock %}
```

---

### 3.21. `work/templates/work/work_profile/work_profile.html`
Последняя известная полная версия.

```html
{% extends 'base.html' %}
{% load i18n %}

{% block body %}
  {% block form %}
    <form method="post" class="work_profile main">
      {% csrf_token %}

      <fieldset>
        <legend>{% trans "Location and Role" %}</legend>
        <div>
          <div>{% trans "Role" %}:</div>
          {{ role }}
        </div>
        <div>
          {{ city_form.city.label_tag }}<br>
          {{ city_form.city }}
          {{ city_form.city.errors }}
          {% if city_form.fields.city.help_text %}
            <small>{{ city_form.fields.city.help_text }}</small>
          {% endif %}
        </div>
      </fieldset>

      <fieldset>
        <legend>{% trans "Contact Information" %}</legend>
        {{ contact_form.non_field_errors }}
        <div>
          {{ contact_form.full_name.label_tag }}<br>
          {{ contact_form.full_name }}
          {{ contact_form.full_name.errors }}
        </div>
        <div>
          {{ contact_form.birth_year.label_tag }}<br>
          {{ contact_form.birth_year }}
          {{ contact_form.birth_year.errors }}
        </div>
        <div>
          {{ contact_form.phone_number.label_tag }}<br>
          {{ contact_form.phone_number }}
          {{ contact_form.phone_number.errors }}
        </div>
      </fieldset>

      <button type="submit">{% trans "Save changes" %}</button>
    </form>
  {% endblock %}
{% endblock %}
```

---

### 3.22. `templates/base.html`
Последняя известная полная версия.

```html
{% load static %}
{% load i18n %}
<!DOCTYPE html>
<html lang="{% get_current_language as LANGUAGE_CODE %}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>{{ title|default:'' }}</title>
    <script src="https://telegram.org/js/telegram-web-app.js?56"></script>
    <script src="{% static 'js/telegram.js' %}" defer></script>
    <script src="{% static 'js/menu.js' %}" defer></script>
    <link href="{% static 'css/styles.css' %}" rel="stylesheet">
</head>
<body>
    {% block header %}
        {% include 'work/includes/header.html' %}
    {% endblock %}

    {% block body_messages %}
        {% include 'includes/messages.html' %}
    {% endblock %}

    {% block body %}
    {% endblock %}
</body>
</html>
```

---

### 3.23. `static/css/styles.css`
Ниже — **последняя подтверждённая полная версия из develop-отчёта**.

> Важно: позднее в другой ветке пользователь сообщил, что на сервере уже менялся фон mini app на градиентный,  
> но **полный итоговый файл после этой правки в отчётах не был показан**.  
> Поэтому как полный файл ниже приводится **последняя подтверждённая версия**.

```css
:root {
    --bg-color: #ffffff;
    --text-color: #000000;
    --accent-color: #007acc;

    --message-success-bg: #dfd;
    --message-warning-bg: #ffc;
    --message-error-bg: #ffefef;

    --default-margin: 10px;
    --default-padding: 10px;
    --default-border-radius: 10px;
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg-color: #121212;
        --text-color: #e0e0e0;
        --accent-color: #bb86fc;

        --message-success-bg: #006b1b;
        --message-warning-bg: #583305;
        --message-error-bg: #570808;
    }
}

* {
    color: var(--text-color);
    background-color: transparent;
    font-family: Arial, sans-serif;
}

body {
    padding: 0;
    margin: 0;
    background-color: var(--bg-color);
    font-family: Arial, sans-serif;
}

.work_profile {
    --padding: 10px;
    --border-radius: 10px;
    padding: var(--padding);

    & input, select {
        width: calc(100% - var(--padding));
        min-height: 30px;
        margin-bottom: 20px;
        border: 1px solid var(--text-color);
    }

    &.step {
        &.roles {

            & .item label {
                display: flex;
                align-items: center;
                flex-direction: row;
                margin-bottom: 20px;
                background-color: rgba(128, 128, 128, 0.5);
                border-radius: var(--border-radius);
                padding: 10px;

                & input {
                    width: auto;
                    margin: 0 10px 0 0;
                }
            }
        }

        &.city {
            input[type="text"],
            input[type="tel"],
            input[type="date"] {
                height: 30px;
                width: calc(100% - var(--padding));
            }

            & div {
                & label {
                    display: flex;
                    align-items: center;
                    margin-bottom: 20px;
                    background-color: rgba(128, 128, 128, 0.5);
                    border-radius: var(--border-radius);
                    padding: 10px;

                    & input {
                        width: auto;
                        margin: 0 10px 0 0;
                    }
                }
            }

        }

        &.contact {
            input[type="text"],
            input[type="tel"],
            input[type="date"] {
                height: 30px;
                margin-bottom: 0;
            }

            & p {
                display: flex;
                flex-direction: column;
                margin-bottom: 20px;
                border-radius: var(--border-radius);
                padding: 10px 0;

            }
        }

    }

    &.main {
        & fieldset {
            margin-bottom: 20px;
            border-radius: var(--border-radius);
            border: 1px solid var(--text-color);
        }
    }


    & button[type="submit"] {
        width: 100%;
        padding: 20px 0;
        text-align: center;
        font-size: 16px;
        font-weight: bold;
        border-radius: var(--border-radius);

        background-color: rgba(128, 128, 128, 0.5);
    }

}

header {
    display: flex;
    justify-content: space-between;
    padding: 30px 10px;
    background-color: rgba(128, 128, 128, 0.2);

    & a {
        text-decoration: none;
    }
    & .left {
        width: 100%;
    }
    & .right {
        width: 100%;
        display: flex;
        justify-content: end;
    }
}

.channel {
    &.preview {
        background-color: rgba(128, 128, 128, 0.2);
        border-radius: var(--default-border-radius);
        margin: var(--default-margin);
        padding: var(--default-padding);
        & .title {
            text-align: center;
            font-size: 18px;
            color: var(--text-color);
        }
        & button.open {
            width: 100%;
            height: 50px;
            border-radius: var(--default-border-radius);
            margin-top: var(--default-margin);
            text-align: center;
            text-decoration: none;
        }
    }
}

.page-block {
    background-color: rgba(128, 128, 128, 0.2);
    border-radius: var(--default-border-radius);
    margin: var(--default-margin);
    padding: var(--default-padding);
}
.menu {
    cursor: pointer;
}
#menu {
    display: none;
    max-width: 100%;
    margin: 0;
    padding: 0;
    flex-direction: column;
    & a {
        display: flex;
        align-items: center;
        justify-content: end;
        padding: 0 10px;
        width: calc(100% - 20px);
        min-height: 50px;
        background-color: rgba(128, 128, 128, 0.2);
        margin-top: 5px;
        text-decoration: none;
    }
}


.date-choice {
    width: max-content;
    & .option {
        display: flex;

        & label {
            width: 100%;
            display: flex;
            justify-content: space-between;

            & div:last-of-type {
                margin-left: 15px;
            }
        }
    }
}

.column {
    display: flex;
    flex-direction: column;
    margin-bottom: 20px;
}
```

#### 3.23.1. Последняя известная серверная правка по фону (не подтверждена полным файлом)
В отчётах позднее фигурировали такие варианты для замены базового фона:

**Вариант 1:**
```css
html, body {
  height: 100%;
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  background: linear-gradient(145deg, #a6a9ab, #6d7074);
  background-attachment: fixed;
  background-size: cover;      
  color: var(--text-color);
  overflow: auto;
}
```

**Вариант 2 (предложенный после просьбы сохранить тему Telegram):**
```css
html, body {
  height: 100%;
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  background: var(--bg-color), linear-gradient(145deg, #a6a9ab, #6d7074);
  background-attachment: fixed;
  background-size: cover;
  color: var(--text-color);
  overflow: auto;
}
```

> Какой из этих вариантов реально остался на сервере — **не могу подтвердить**.

---

### 3.24. `.env`
Последнее известное содержимое по отчётам. Значения отредактированы.

```dotenv
DJANGO_SECRET_KEY=[REDACTED]
POSTGRESQL_NAME=robochi
POSTGRESQL_USER=coin
POSTGRESQL_PASSWORD=[REDACTED]
POSTGRESQL_HOST=localhost
POSTGRESQL_PORT=5432

HOST=robochi.pp.ua
BASE_URL=https://robochi.pp.ua
DJANGO_SETTINGS_MODULE=config.django.production
TELEGRAM_WEBHOOK_SECRET=SZeEaNRelI
HOST=robochi.pp.ua
BASE_URL=https://robochi.pp.ua

TELEGRAM_BOT_TOKEN=[REDACTED]
PROVIDER_TOKEN=[REDACTED]

SENTRY_DSN=[REDACTED]
```

---

### 3.25. `.env.example`
Последняя известная полная версия.

```dotenv
DJANGO_SECRET_KEY=change-me
HOST=robochi.pp.ua
POSTGRESQL_NAME=robochi
POSTGRESQL_USER=postgres
POSTGRESQL_PASSWORD=change-me
POSTGRESQL_HOST=localhost
POSTGRESQL_PORT=5432
TELEGRAM_BOT_TOKEN=put-your-token-here
PROVIDER_TOKEN=put-provider-token-here
SENTRY_DSN=
TELEGRAM_WEBHOOK_SECRET=SZeEaNRelI
DJANGO_SETTINGS_MODULE=config.django.production
HOST=robochi.pp.ua
BASE_URL=https://robochi.pp.ua
```

---

### 3.26. `.env.local`
Последняя известная полная версия.

```dotenv
TELEGRAM_BOT_TOKEN=[REDACTED]
PROVIDER_TOKEN=[REDACTED]
TELEGRAM_WEBHOOK_SECRET=SZeEaNRelI
DJANGO_SETTINGS_MODULE=config.django.production
HOST=robochi.pp.ua
BASE_URL=https://robochi.pp.ua
```

---

### 3.27. `/etc/robochi_bot.env`
Последнее известное production-окружение по отчётам. Значения отредактированы.

```dotenv
DJANGO_SETTINGS_MODULE=config.django.production
HOST=robochi.pp.ua
BASE_URL=https://robochi.pp.ua
TELEGRAM_BOT_TOKEN=[REDACTED]
TELEGRAM_WEBHOOK_SECRET=SZeEaNRelI
PROVIDER_TOKEN=[REDACTED]
DJANGO_SECRET_KEY=[REDACTED]
POSTGRESQL_NAME=robochi
POSTGRESQL_USER=coin
POSTGRESQL_PASSWORD=[REDACTED]
POSTGRESQL_HOST=localhost
POSTGRESQL_PORT=5432
SENTRY_DSN=[REDACTED]
```

---

### 3.28. `/etc/systemd/system/gunicorn.service`
Последний известный фрагмент production unit-файла.

```ini
[Unit]
Description=Gunicorn daemon for robochi_bot
After=network.target

[Service]
User=webuser
Group=webuser
WorkingDirectory=/home/webuser/robochi_bot
EnvironmentFile=/etc/robochi_bot.env
WorkingDirectory=/home/webuser/robochi_bot
ExecStart=/home/webuser/robochi_bot/venv/bin/gunicorn config.wsgi:application \
  --bind unix:/home/webuser/robochi_bot/gunicorn.sock \
  --workers 1

[Install]
WantedBy=multi-user.target
```

---

## 4. Полный технический стек

Ниже — объединённый стек: **подтверждённый**, **используемый по коду**, и **запланированный**.

### 4.1. Backend
- Python
- Django
- Django Auth / Sessions / Admin / Templates
- django-formtools (`SessionWizardView`)
- django-parler
- WhiteNoise
- python-dotenv

### 4.2. Telegram
- Telegram Bot API
- `pyTelegramBotAPI` / `telebot`
- Telegram WebApp JS API
- Webhook-модель для получения update’ов

### 4.3. Database / async
- PostgreSQL
- Celery
- Redis **или** RabbitMQ как брокер Celery  
  Точное текущее значение в отчётах окончательно не подтверждено.

### 4.4. Production / infra
- Gunicorn
- Nginx
- systemd
- Linux VPS
- Fornex
- WinSCP / ручные правки на сервере

### 4.5. Frontend / templates
- Django templates
- CSS
- JavaScript
- Alpine.js — упоминался в проектном контексте, но по показанным файлам текущая степень использования не подтверждена

### 4.6. Наблюдаемость / вспомогательные компоненты
- Sentry
- логирование через Django logging
- `journalctl` / `systemctl` для production-диагностики

### 4.7. Платежи
- текущая тестовая Telegram payments логика считалась существующей / исторической;
- целевое решение по ТЗ — **monobank**;
- монобанк ещё не реализован;
- по рабочему коду платёжный слой в отчётах не подтверждён как завершённый.

---

## 5. Что реализовано и работает

Ниже — только то, что по отчётам было подтверждено как реализованное или частично работающее.

### 5.1. Реализовано в коде
1. Есть endpoint проверки / входа для Telegram WebApp:
   - `check-web-app/`
   - `authenticate-web-app/`

2. Есть серверная логика проверки `initData` и попытка логина пользователя по Telegram ID.

3. Есть webhook endpoint Telegram:
   - `telegram_webhook`

4. Есть базовый бот-сценарий:
   - `/start`
   - запрос телефона через `request_contact`
   - выдача кнопки WebApp
   - `/info`

5. Есть wizard в WebApp:
   - `role`
   - `city`
   - `agreement`

6. Есть страница личного кабинета профиля (`work_profile_detail`).

7. Есть production-схема через:
   - gunicorn
   - nginx
   - systemd

### 5.2. Что было подтверждено по факту запуска / логам
1. На одном из этапов был убран `502 Bad Gateway`.
2. `gunicorn` и `nginx` поднимались и принимали трафик.
3. Webhook реально доходил до Django:
   - в логах был `WEBHOOK HIT`.
4. Создание пользователя по Telegram ID минимум один раз подтверждалось логами.
5. `reverse('telegram:telegram_check_web_app')` возвращал `/telegram/check-web-app/` при корректном env.
6. Часовой пояс сервера был изменён на `Europe/Kyiv`.

### 5.3. Что согласовано на уровне ТЗ
1. Новый ТЗ собран до раздела 10 включительно.
2. Зафиксирована новая бизнес-логика mini app.
3. Зафиксировано, что:
   - сайт `robochi.work` не входит в архитектуру mini app;
   - все сервисные тексты идут через бота;
   - WebApp — для форм, ЛК, табличных интерфейсов;
   - оплату нужно переводить на monobank;
   - ротация — отдельный ключевой технический узел;
   - анкеты старого типа нужно убрать.
### 5.4. Исправлено в сессии 09.03.2026

1. Починены критические ошибки импортов в Telegram-части:
   - добавлена функция get_bot() в bot_instance.py,
   - убран импорт несуществующего модуля messages/info.py,
   - добавлен явный импорт bot в commands.py,
   - объединены дублирующие импорты в views.py,
   - убран дублирующий return в telegram_webhook.
   Ветка: fix/bot-imports — смержена в develop и main.

2. Исправлен deploy.sh:
   - git pull теперь тянет ветку develop вместо main,
   - все команды python и pip используют ./venv/bin/ вместо системного Python.
   Ветка: fix/deploy-sh — смержена в develop и main.

3. Добавлена переменная TELEGRAM_WEBHOOK_SECRET в /etc/robochi_bot.env —
   gunicorn теперь стартует без ValueError.

4. Исправлена кодировка telegram/templates/telegram/check.html —
   удалён комментарий в CP1251, файл пересоздан в чистом UTF-8.
   Ветка: fix/template-encoding — смержена в develop и main.

5. Мини-приложение открывается в браузере без ошибки 500.

---

## 6. Что не завершено

### 6.1. По продукту / ТЗ
1. **Раздел 8. Отзывы и рейтинги** — отложен.
2. **Раздел 11. Этапы реализации** — не написан.
3. Детализированная схема ротации:
   - статусы,
   - триггеры,
   - задачи Celery,
   - повторный поиск,
   - продление,
   - тайминги
   пока не собрана как отдельный технический раздел.
4. Полная новая модель БД под обновлённое ТЗ не собрана.

### 6.2. По коду
1. Не завершено удаление `ContactForm` / старой контактной анкеты из ЛК.
2. Не завершён рефакторинг:
   - `work/forms.py`
   - `work/views/work_profile.py`
   - `work_profile.html`
3. Не завершена миграция логики на новый UX:
   - `Role -> City -> Rules -> Dashboard`
4. Не реализована интеграция **monobank**.
5. Не подтверждено финальное исправление смешивания данных между аккаунтами на одном телефоне.
6. Не подтвержден финально рабочий сценарий:
   - `/start`
   - телефон
   - WebApp
   - `check-web-app`
   - `authenticate-web-app`
   - `login()`
   - `redirect(next)`

### 6.3. По infrastructure / deploy
1. Не завершено приведение `deploy.sh` к реальному production-сценарию.
2. Не решена окончательно стратегия веток:
   - `main`
   - `develop`
   - prod-first workflow
3. Не очищена до конца путаница systemd unit-файлов:
   - `gunicorn.service`
   - `robochi.service`
   - `robochi_site.service`
   - `robochi_bot.service`
4. Не унифицированы окончательно:
   - `.env`
   - `.env.example`
   - `.env.local`
   - `/etc/robochi_bot.env`

### 6.4. По качеству
1. Нет финального подтверждения тестами.
2. Нет полного аудита ORM-поисков:
   - везде ли профиль ищется строго по `user`;
   - нет ли поиска по телефону или другим косвенным полям.
3. Нет финального кодового аудита Telegram-части после ручных изменений на сервере.

---

## 7. Известные проблемы

### 7.1. Критические архитектурные проблемы
1. **Смешение двух деревьев настроек**
   - `config/django/*`
   - `config/settings/*`

2. **Противоречие между кодом и новым ТЗ**
   - по ТЗ анкеты надо убрать,
   - в коде `ContactForm` и контактный блок ЛК всё ещё есть.

3. **Противоречие между `User.id` и `User.telegram_id`**
   - в `telegram/views.py` комментарий говорит, что Telegram ID хранится в `User.telegram_id`;
   - в `telegram/utils.py` пользователь ищется через `User.objects.get(id=user_id)`.

   Это надо перепроверять по реальной модели `User`.

### 7.2. Критические проблемы Telegram-части
1. В develop-снимке `telegram/views.py` импортирует: [РЕШЕНО 09.03.2026]
   - `get_bot`
   - `bot`
   - `load_handlers_once`

   Но показанный поздний `bot_instance.py`: [РЕШЕНО 09.03.2026]
   - не содержит `get_bot()`;
   - импортирует `messages.info`, которого по отчёту нет.

2. В `commands.py` используются декораторы `@bot.message_handler`, а сам `bot` в этом файле явно не импортирован в показанном develop-варианте. [РЕШЕНО 09.03.2026]

3. При следующем рестарте production Telegram-часть может упасть из-за broken imports. [РЕШЕНО 09.03.2026]

4. В `telegram/utils.py` нет проверки `auth_date`, хотя она рекомендовалась как обязательная / желательная.

5. Подпись WebApp `initData` по отчётам реализована, но порядок вычисления `secret_key` вызывал сомнения и требовал перепроверки по реальному поведению.

### 7.3. Проблемы сессий и аккаунтов
1. На одном телефоне при переключении Telegram-аккаунтов у нового аккаунта могли подтягиваться:
   - роль,
   - город,
   - пол
   от предыдущего пользователя.

2. Было предложено решение через `request.session.flush()`, но полное устранение бага **не подтверждено**.

3. Если баг остаётся, проблема почти наверняка не только в сессии, но и в:
   - обходе `authenticate_web_app`,
   - использовании старого `request.user`,
   - неверном поиске профиля / заявок.

### 7.4. Проблемы production / deploy
1. `deploy.sh` тянет `main`, хотя реальная работа шла в `develop`.
2. В скрипте используется `python`, а на сервере по факту нужен `python3` / правильный interpreter из `venv`.
3. `webuser` не имеет прав на `systemctl restart`.
4. `sudo` на сервере отсутствовал / не использовался в нужной форме.
5. Без рестарта сервисов изменения кода на сервере не применяются.

### 7.5. Проблемы env
1. Переменные окружения дублировались в нескольких местах.
2. `gunicorn` через `systemd` видел env не так, как ручной shell.
3. Строгая проверка `PROVIDER_TOKEN` на старте всего приложения считалась ошибочной архитектурой.
4. `TELEGRAM_WEBHOOK_SECRET` при переходе на новую схему периодически валил старт из-за неполной env-настройки.

### 7.6. Проблемы статики и фронтенда
1. `.gitignore` глобально игнорирует `*.css` и `*.js`, из-за чего исходники статики могли не попадать в git.
2. В `templates/base.html` подключены файлы:
   - `js/telegram.js`
   - `js/menu.js`

   Но они могли отсутствовать в репозитории.
3. `static/css/styles.css` использует CSS nesting с `&`, что может быть проблемой, если это не проходит через корректную обработку.
4. Есть подтверждённые проблемы с кодировкой:
   - `Â...`
   - `Ï³äòâåðäæóþ`
   - битые переводы в admin actions и шаблонах.

### 7.7. Проблемы безопасности
1. Реальные секреты в ходе веток попадали в диалог.
2. После этого нужно считать скомпрометированными и перевыпустить минимум:
   - `TELEGRAM_BOT_TOKEN`
   - `PROVIDER_TOKEN` (если ещё используется)
   - возможно `DJANGO_SECRET_KEY`

---

## 8. Следующие шаги

Ниже — объединённый приоритетный план, исходя из всех веток.

### Шаг 1. Зафиксировать реальное текущее состояние кода
Сначала нужно снять **реальный снимок текущего репозитория / сервера**, потому что в отчётах есть противоречивые промежуточные версии.

Что проверить первым:
1. актуальный `telegram/views.py`;
2. актуальный `telegram/handlers/bot_instance.py`;
3. актуальный `telegram/handlers/messages/commands.py`;
4. актуальный `work/views/work_profile.py`;
5. актуальный `work/forms.py`;
6. актуальный `static/css/styles.css`;
7. актуальный `deploy.sh`;
8. актуальные env-файлы и systemd unit.

### Шаг 2. Стабилизировать production
Приоритет выше любой новой разработки.

Сделать:
1. привести к одному источнику env:
   - `/etc/robochi_bot.env` как production source of truth;
2. привести `deploy.sh` к реальному сценарию:
   - правильная ветка,
   - правильный interpreter,
   - понятная стратегия рестарта;
3. решить права на рестарт сервисов;
4. убрать исторический мусор unit-файлов и названий.

### Шаг 3. Починить Telegram import graph
Это критично, иначе следующий рестарт может уронить проект.

Нужно:
1. выбрать один подход:
   - либо глобальный `bot`,
   - либо `get_bot()` с ленивой инициализацией;
2. синхронизировать:
   - `telegram/views.py`
   - `bot_instance.py`
   - `commands.py`
   - `admin_actions.py`
3. убрать отсутствующие импорты типа `messages.info`, если файла реально нет.

### Шаг 4. Довести до конца WebApp auth
Нужно подтвердить полностью рабочую цепочку:

`/start -> request_contact -> webapp button -> check.html -> authenticate_web_app -> login -> redirect(next)`

Проверить:
1. реально ли вызывается `authenticate_web_app`;
2. что `initData` приходит;
3. что подпись проходит;
4. что логин создаёт именно нужного пользователя;
5. что redirect ведёт в нужную страницу;
6. добавить проверку `auth_date`.

### Шаг 5. Добить баг смешивания аккаунтов
После стабилизации auth-flow:

1. проверить реальный код `authenticate_web_app`;
2. проверить, везде ли сравнение идёт с корректным Telegram user;
3. вручную протестировать сценарий `A -> B -> A` на одном телефоне;
4. если баг остаётся — проверить ORM:
   - не ищутся ли профиль / заявки по телефону вместо `user`.

### Шаг 6. Синхронизировать код с новым ТЗ
После стабилизации production и auth:

1. убрать `ContactForm` из ЛК;
2. привести wizard к финальной логике:
   - роль
   - город
   - правила
   - кабинет
3. перевести сбор данных на минимальную модель;
4. исключить старые анкеты.

### Шаг 7. Спроектировать и реализовать ротацию
Это главный следующий бизнес-узел по ТЗ.

Нужно отдельно собрать:
1. статусы вакансии;
2. статусы участия;
3. таймеры;
4. celery-задачи;
5. триггеры повторного поиска;
6. продление на завтра;
7. связь с группами / каналами / перекличками.

### Шаг 8. После ротации вернуться к отложенным разделам
Далее:
1. раздел 8 ТЗ — отзывы и рейтинги;
2. раздел 11 ТЗ — этапы реализации;
3. финальная БД-схема;
4. monobank integration;
5. тесты;
6. нормализация кодировки и фронтенд-стилей.

---

## Итог в одном абзаце

Проект `robochi_bot` уже имеет основу Telegram-бота, WebApp-авторизацию, wizard-профиль и production-развёртывание на Django, но его текущее состояние остаётся переходным: новая продуктовая логика уже согласована в ТЗ, а фактический код и деплой ещё не доведены до этой модели. Главные ближайшие задачи — сначала стабилизировать production, env и Telegram auth-flow, затем устранить импортные конфликты и смешивание аккаунтов, и только после этого переводить личные кабинеты, ротацию и оплату на финальную архитектуру нового ТЗ.
