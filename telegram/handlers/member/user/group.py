import logging
import time

import sentry_sdk
from telebot.types import ChatJoinRequest, ChatMemberUpdated

from telegram.choices import CallStatus, CallType
from telegram.handlers.bot_instance import bot
from telegram.models import Group, Status, UserInGroup
from telegram.service.group import GroupService
from user.models import User
from user.services import BlockService
from vacancy.choices import GENDER_ANY, STATUS_ACTIVE, STATUS_APPROVED
from vacancy.models import Vacancy, VacancyUser, VacancyUserCall
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
from vacancy.services.call_markup import get_worker_join_confirm_markup
from vacancy.services.observers import events
from vacancy.services.observers.subscriber_setup import vacancy_publisher

logger = logging.getLogger(__name__)


@bot.chat_join_request_handler(func=lambda c: True)
def auto_approve(req: ChatJoinRequest):
    logger.info("join_request", extra={"user_id": req.from_user.id, "group_id": req.chat.id})
    if req.chat.type != "supergroup":
        return
    try:
        user, created = User.objects.update_or_create(
            id=req.from_user.id,
            defaults={
                "username": req.from_user.username,
            },
        )

        # Admins always pass
        if user.is_staff:
            bot.approve_chat_join_request(req.chat.id, req.from_user.id)
            logger.info(
                "join_approved", extra={"user_id": req.from_user.id, "group_id": req.chat.id, "vacancy_id": None}
            )
            GroupService.set_default_admin_permissions(
                chat_id=req.chat.id,
                user_id=req.from_user.id,
            )
            GroupService.set_admin_custom_title(
                chat_id=req.chat.id,
                user_id=req.from_user.id,
                custom_title="Адміністратор",
            )
            return

        # Blocked users
        if BlockService.is_permanently_blocked(user):
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "permanently_blocked"})
            bot.send_message(
                req.from_user.id,
                text=CallVacancyTelegramTextFormatter.auto_block_message(reason="постійне блокування"),
            )
            return
        elif BlockService.is_temporarily_blocked(user):
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "temporarily_blocked"})
            bot.send_message(
                req.from_user.id,
                text="Ви не можете брати участь у вакансіях. Ви заблоковані.",
            )
            return
        elif not user.is_active:
            # Legacy fallback: is_active=False without UserBlock record
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "not_active"})
            bot.send_message(
                req.from_user.id,
                text="Ви не можете брати участь у вакансіях. Ви заблоковані.",
            )
            return

        # Unregistered user — no work_profile or no role
        work_profile = getattr(user, "work_profile", None)
        if not work_profile or not work_profile.role:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "not_registered"})
            try:
                bot.send_message(
                    req.from_user.id,
                    "Щоб приєднатися до вакансії, спочатку зареєструйтесь у боті.\n"
                    "Натисніть /start для початку реєстрації.",
                )
            except Exception:
                sentry_sdk.capture_exception()
            return

        group, _ = Group.objects.update_or_create(
            id=req.chat.id,
            defaults={
                "title": req.chat.title or "",
            },
        )
        vacancy = Vacancy.objects.get(
            status__in=[STATUS_APPROVED, STATUS_ACTIVE],
            group=group,
        )

        # Vacancy owner always passes
        if vacancy.owner == user:
            bot.approve_chat_join_request(req.chat.id, req.from_user.id)
            logger.info(
                "join_approved", extra={"user_id": req.from_user.id, "group_id": req.chat.id, "vacancy_id": vacancy.id}
            )
            time.sleep(1)
            GroupService.set_default_owner_permissions(
                chat_id=req.chat.id,
                user_id=req.from_user.id,
            )
            GroupService.set_admin_custom_title(
                chat_id=req.chat.id,
                user_id=req.from_user.id,
                custom_title="Роботодавець",
            )
            return

        # Employer cannot join another employer's vacancy group
        if work_profile and work_profile.role == "employer":
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "employer_not_owner"})
            try:
                bot.send_message(
                    req.from_user.id,
                    "Ви роботодавець. Ви не можете приєднатися до чужої вакансії.",
                )
            except Exception:
                sentry_sdk.capture_exception()
            return

        # Check: already in another active vacancy
        already_in_vacancy = (
            VacancyUser.objects.filter(
                user=user,
                status=Status.MEMBER,
                vacancy__status__in=[STATUS_APPROVED, STATUS_ACTIVE],
            )
            .exclude(vacancy=vacancy)
            .exists()
        )

        if already_in_vacancy:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "already_in_vacancy"})
            bot.send_message(
                req.from_user.id, text="Ви вже берете участь в іншій вакансії. Спочатку завершіть поточну."
            )
            return

        # Check: group is full
        if vacancy.members.count() >= vacancy.people_count:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "group_full"})
            bot.send_message(req.from_user.id, text="На жаль, всі місця за цією вакансією вже зайняті.")
            return

        # Check: gender filter
        if vacancy.gender != GENDER_ANY:
            if not user.gender:
                bot.decline_chat_join_request(req.chat.id, req.from_user.id)
                logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "gender_not_set"})
                bot.send_message(
                    req.from_user.id, text="Ваша стать не вказана в профілі. Зверніться до адміністратора."
                )
                return
            if vacancy.gender != user.gender:
                bot.decline_chat_join_request(req.chat.id, req.from_user.id)
                logger.warning("join_declined", extra={"user_id": req.from_user.id, "reason": "gender_mismatch"})
                bot.send_message(req.from_user.id, text="Ця вакансія призначена для іншої статі.")
                return

        # All checks passed
        bot.approve_chat_join_request(req.chat.id, req.from_user.id)
        logger.info(
            "join_approved", extra={"user_id": req.from_user.id, "group_id": req.chat.id, "vacancy_id": vacancy.id}
        )

    except Vacancy.DoesNotExist:
        try:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
        except Exception:
            sentry_sdk.capture_exception()
    except Exception:
        sentry_sdk.capture_exception()
        try:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
        except Exception:
            sentry_sdk.capture_exception()


@bot.chat_member_handler()
def handle_user_status_change(event: ChatMemberUpdated):
    user_data = event.new_chat_member.user
    if user_data.is_bot:
        return
    if event.old_chat_member.status in ["kicked", "left"] and event.new_chat_member.status in ["kicked", "left"]:
        return
    if event.new_chat_member.status in [Status.ADMINISTRATOR.value]:
        return
    if event.chat.type != "supergroup":
        return

    group, _ = Group.objects.update_or_create(
        id=event.chat.id,
        defaults={
            "title": event.chat.title or "",
        },
    )

    user, created = User.objects.update_or_create(
        id=user_data.id,
        defaults={
            "username": user_data.username,
        },
    )

    vacancy = Vacancy.objects.get(
        status__in=[STATUS_APPROVED, STATUS_ACTIVE],
        group=group,
    )

    status = event.new_chat_member.status
    if status not in ["kicked", "left"]:
        if status not in Status.values:
            status = Status.MEMBER.value
        if event.new_chat_member.user.id == vacancy.owner.id:
            status = Status.OWNER.value
            GroupService.set_default_owner_permissions(
                chat_id=event.chat.id,
                user_id=event.new_chat_member.user.id,
            )
            GroupService.set_admin_custom_title(
                chat_id=event.chat.id,
                user_id=event.new_chat_member.user.id,
                custom_title="Роботодавець",
            )
        if user.is_staff:
            status = Status.ADMINISTRATOR.value

        UserInGroup.objects.update_or_create(user=user, group=group, defaults={"status": status})
        VacancyUser.objects.update_or_create(
            user=user,
            vacancy=vacancy,
            status=status,
        )

        vacancy_publisher.notify(events.VACANCY_NEW_MEMBER, data={"vacancy": vacancy})

        # Send join-confirm request to the worker (not owner, not staff)
        if not vacancy.owner == user and not user.is_staff:
            vacancy_user = VacancyUser.objects.filter(user=user, vacancy=vacancy).first()
            if vacancy_user:
                from django.utils import timezone

                VacancyUserCall.objects.update_or_create(
                    vacancy_user=vacancy_user,
                    call_type=CallType.WORKER_JOIN_CONFIRM.value,
                    defaults={
                        "status": CallStatus.SENT.value,
                        "created_at": timezone.now(),
                    },
                )
                try:
                    bot.send_message(
                        chat_id=user.id,
                        text=CallVacancyTelegramTextFormatter(vacancy).worker_join_confirm(),
                        reply_markup=get_worker_join_confirm_markup(vacancy),
                    )
                except Exception as e:
                    import logging

                    logging.warning(f"Failed to send join-confirm to user {user.id}: {e}")
    else:
        logger.info("member_left_group", extra={"user_id": user_data.id, "group_id": event.chat.id})
        UserInGroup.objects.filter(user=user, group=group).delete()
        VacancyUser.objects.filter(user=user, vacancy=vacancy).update(status=Status.LEFT)
        GroupService.kick_user(
            chat_id=event.chat.id,
            user_id=event.new_chat_member.user.id,
        )

        if not vacancy.owner == user and not user.is_staff:
            vacancy_publisher.notify(events.VACANCY_LEFT_MEMBER, data={"vacancy": vacancy})
