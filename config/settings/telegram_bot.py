import os

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_BOT_ALLOWED_UPDATES = [
    'message',
    'edited_message',
    'callback_query',
    'pre_checkout_query',
    'successful_payment',
    'my_chat_member',
    'chat_member',
    'chat_join_request',
]
TELEGRAM_BOT_ALL_GROUP_CONTENT_TYPES = [
    'text', 'audio', 'document', 'photo', 'sticker',
    'video', 'video_note', 'voice', 'location', 'contact',
    'new_chat_members', 'left_chat_member',
    'new_chat_title', 'new_chat_photo', 'delete_chat_photo',
    'group_chat_created', 'supergroup_chat_created',
    'channel_chat_created', 'migrate_to_chat_id',
    'migrate_from_chat_id', 'pinned_message', 'poll',
    'new_chat_members', 'left_chat_member',
]
if not TELEGRAM_BOT_TOKEN:
    raise ValueError('Please set the TELEGRAM_BOT_TOKEN environment variable')

PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN')
if not PROVIDER_TOKEN:
    raise ValueError('Please set the PROVIDER_TOKEN environment variable')
