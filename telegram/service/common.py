import base64
import json

from telegram.handlers.bot_instance import bot


def get_payload_url(payload: dict) -> str:
    json_str = json.dumps(payload, ensure_ascii=False)
    encoded_payload = base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")
    url = f'https://t.me/{bot.get_me().username}?start={encoded_payload}'
    return url