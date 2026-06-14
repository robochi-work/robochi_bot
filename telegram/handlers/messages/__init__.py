# ruff: noqa: I001, F401, F811
# ПОРЯДОК ВАЖЛИВИЙ: global_buttons + admin_reply ПЕРЕД worker_phone,
# щоб ловили текст reply-кнопок раніше за catch-all worker_phone.
from .commands import bot
from .group import bot
from .global_buttons import bot
from .admin_reply import bot
from .worker_phone import bot

__all__ = ["bot"]
