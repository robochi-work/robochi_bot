import os

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
if ":" not in TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing or invalid (must contain a colon)")

PROVIDER_TOKEN = (os.getenv("PROVIDER_TOKEN") or "").strip()

TELEGRAM_BOT_ALL_GROUP_CONTENT_TYPES = [
    'text', 'photo', 'video', 'document', 'audio',
    'voice', 'sticker', 'location', 'contact',
]

# ��������� ����� ��� webhook URL (�� �� ������)
TELEGRAM_WEBHOOK_SECRET = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
if not TELEGRAM_WEBHOOK_SECRET:
    raise ValueError("TELEGRAM_WEBHOOK_SECRET is not set")
TELEGRAM_BOT_ALLOWED_UPDATES = [
    'message',
    'callback_query',
    'my_chat_member',
    'chat_member',
    'chat_join_request',
]
