"""Сервіс «Допомога Адміністратора»: формування картки, відправка, стани."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from telebot.types import Message

    from user.models import User

logger = logging.getLogger(__name__)

PENDING_TTL = 600  # 10 хвилин
CACHE_KEY = "admin_help_pending:{user_id}"
ADMIN_DEEPLINK = "https://t.me/robochi_work_admin"


def _admin_chat_id() -> int | None:
    val = getattr(settings, "ADMIN_HELP_CHAT_ID", None)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


class AdminHelpService:
    @staticmethod
    def _get_bot():
        from telegram.handlers.bot_instance import get_bot

        return get_bot()

    @classmethod
    def is_pending_by_id(cls, user_id: int) -> bool:
        return bool(cache.get(CACHE_KEY.format(user_id=user_id)))

    @classmethod
    def is_pending(cls, user: User) -> bool:
        return cls.is_pending_by_id(user.id)

    @classmethod
    def start_request(cls, user: User, source: str = "private") -> None:
        from user.models import AdminHelpRequest

        AdminHelpRequest.objects.filter(user=user, status=AdminHelpRequest.STATUS_PENDING).update(
            status=AdminHelpRequest.STATUS_TIMEOUT, closed_at=timezone.now()
        )

        req = AdminHelpRequest.objects.create(user=user, status=AdminHelpRequest.STATUS_PENDING)
        cache.set(CACHE_KEY.format(user_id=user.id), req.id, timeout=PENDING_TTL)

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(_("❌ Cancel"), callback_data=f"adminhelp:cancel:{req.id}"))
        text = _(
            "📝 Опишіть вашу проблему одним повідомленням "
            "(можна додати фото або відео).\n"
            "Воно буде передано адміністратору разом з вашими даними.\n\n"
            "⏱ Маєте 10 хвилин."
        )
        try:
            cls._get_bot().send_message(user.id, text, reply_markup=markup)
        except Exception as e:
            logger.warning(f"admin_help.start_request: send to user {user.id} failed: {e}")

    @classmethod
    def cancel_request(cls, user: User, req_id: int) -> None:
        from user.models import AdminHelpRequest

        cache.delete(CACHE_KEY.format(user_id=user.id))
        AdminHelpRequest.objects.filter(id=req_id, user=user, status=AdminHelpRequest.STATUS_PENDING).update(
            status=AdminHelpRequest.STATUS_CLOSED, closed_at=timezone.now()
        )

    @classmethod
    def submit_request(cls, user: User, message: Message) -> None:
        from user.models import AdminHelpRequest

        bot = cls._get_bot()
        chat_id = _admin_chat_id()
        if chat_id is None:
            logger.error("ADMIN_HELP_CHAT_ID не налаштовано")
            return

        req_id = cache.get(CACHE_KEY.format(user_id=user.id))
        if not req_id:
            return
        try:
            req = AdminHelpRequest.objects.get(id=req_id, status=AdminHelpRequest.STATUS_PENDING)
        except AdminHelpRequest.DoesNotExist:
            cache.delete(CACHE_KEY.format(user_id=user.id))
            return

        text_msg = message.text or message.caption or ""
        card_text = cls._build_card(user, text_msg)
        markup = InlineKeyboardMarkup()
        base = settings.BASE_URL.rstrip("/")
        admin_url = f"{base}/taya-panel/user/user/{user.id}/change/"
        markup.row(
            InlineKeyboardButton(text=_("🔗 Admin"), url=admin_url),
            InlineKeyboardButton(text=_("💬 DM user"), url=f"tg://user?id={user.id}"),
        )
        markup.add(InlineKeyboardButton(text=_("✅ Close request"), callback_data=f"adminhelp:close:{req.id}"))

        try:
            sent = bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="HTML")
            req.admin_chat_message_id = sent.message_id
        except Exception as e:
            logger.exception(f"admin_help.submit: send card failed: {e}")
            return

        media_ids: list[int] = []
        if message.content_type in ("photo", "video", "voice", "video_note"):
            try:
                fwd = bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=user.id,
                    message_id=message.message_id,
                )
                media_ids.append(fwd.message_id)
            except Exception as e:
                logger.warning(f"admin_help: forward media failed: {e}")

        req.media_message_ids = media_ids
        req.message_text = text_msg
        req.status = AdminHelpRequest.STATUS_OPEN
        req.save()
        cache.delete(CACHE_KEY.format(user_id=user.id))

        confirm_markup = InlineKeyboardMarkup()
        confirm_markup.add(InlineKeyboardButton(text=_("💬 Direct DM admin"), url=ADMIN_DEEPLINK))
        try:
            bot.send_message(
                user.id,
                _(
                    "✅ Ваше звернення прийнято.\n"
                    "Адміністратор отримав ваше повідомлення "
                    "та зв'яжеться з вами найближчим часом."
                ),
                reply_markup=confirm_markup,
            )
        except Exception:
            pass

    @classmethod
    def close_request(cls, req_id: int, by_user: User) -> None:
        from user.models import AdminHelpRequest

        try:
            req = AdminHelpRequest.objects.get(id=req_id)
        except AdminHelpRequest.DoesNotExist:
            return
        if req.status == AdminHelpRequest.STATUS_CLOSED:
            return
        req.status = AdminHelpRequest.STATUS_CLOSED
        req.closed_at = timezone.now()
        req.closed_by = by_user
        req.save()
        chat_id = _admin_chat_id()
        if chat_id and req.admin_chat_message_id:
            try:
                new_card = cls._build_card(req.user, req.message_text, closed=True)
                cls._get_bot().edit_message_text(
                    chat_id=chat_id,
                    message_id=req.admin_chat_message_id,
                    text=new_card,
                    parse_mode="HTML",
                )
            except Exception:
                pass

    @staticmethod
    def _build_card(user: User, message_text: str, *, closed: bool = False) -> str:
        from vacancy.choices import (
            STATUS_APPROVED,
            STATUS_AWAITING_PAYMENT,
            STATUS_CLOSED,
            STATUS_PENDING,
            STATUS_SEARCH_STOPPED,
        )
        from vacancy.models import Vacancy, VacancyUser

        wp = getattr(user, "work_profile", None)
        role_label = "—"
        city_label = "—"
        if wp:
            try:
                role_label = wp.get_role_display() if wp.role else "—"
            except Exception:
                role_label = str(wp.role or "—")
            try:
                if wp.city:
                    city_label = wp.city.name
            except Exception:
                pass

        rating_str = "—"
        try:
            from user.rating import get_bayesian_rating

            r = get_bayesian_rating(user)
            if r:
                rating_str = f"{r:.2f}"
        except Exception:
            pass

        try:
            from user.choices import BlockType
            from user.models import UserBlock

            active_blocks = UserBlock.objects.filter(
                user=user,
                block_type__in=[BlockType.TEMPORARY, BlockType.PERMANENT],
            ).count()
        except Exception:
            active_blocks = 0
        block_str = "немає" if active_blocks == 0 else f"{active_blocks}"

        active_statuses = [
            STATUS_PENDING,
            STATUS_APPROVED,
            STATUS_SEARCH_STOPPED,
            STATUS_AWAITING_PAYMENT,
            STATUS_CLOSED,
        ]
        lines_vac = []
        try:
            if wp and wp.role == "employer":
                vacs = Vacancy.objects.filter(owner=user, status__in=active_statuses).select_related("city")[:10]
                for v in vacs:
                    title = (v.title or "")[:40]
                    city = v.city.name if v.city_id else "?"
                    lines_vac.append(f"  • #{v.id} «{title}» ({city}) — {v.status}")
            elif wp and wp.role == "worker":
                from telegram.models import Status

                vus = VacancyUser.objects.filter(
                    user=user,
                    status__in=[Status.MEMBER.value, Status.PENDING_CONFIRM.value],
                ).select_related("vacancy", "vacancy__city")[:10]
                for vu in vus:
                    v = vu.vacancy
                    title = (v.title or "")[:40]
                    city = v.city.name if v.city_id else "?"
                    lines_vac.append(f"  • #{v.id} «{title}» ({city}) — {vu.status}")
        except Exception:
            logger.exception("admin_help.card: vacancy block failed")

        vacancies_block = "\n".join(lines_vac) if lines_vac else "  немає"
        username_str = f"@{user.username}" if user.username else "(без username)"
        full_name = user.full_name or "—"
        phone = user.phone_number or "—"
        registered = user.date_joined.strftime("%d.%m.%Y") if user.date_joined else "—"
        prefix = "<b>✅ ЗАКРИТО</b>\n\n" if closed else ""
        return (
            f"{prefix}"
            f"👤 <b>{full_name}</b> ({username_str})\n"
            f"🆔 TG ID: <code>{user.id}</code>\n"
            f"🏷️ Роль: {role_label}\n"
            f"🏙️ Місто: {city_label}\n"
            f"📞 Тел: <code>{phone}</code>\n"
            f"⭐ Рейтинг: {rating_str}\n"
            f"🚫 Блокування: {block_str}\n"
            f"📅 Зареєстрований: {registered}\n\n"
            f"📋 Активні вакансії:\n{vacancies_block}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"📝 Повідомлення:\n"
            f"{message_text or '(порожнє)'}\n"
            f"━━━━━━━━━━━━━━"
        )
