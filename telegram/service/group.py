import logging
import time
from collections.abc import Iterable

import sentry_sdk
from django.db.models import QuerySet
from telebot.types import ChatPermissions

from telegram.choices import STATUS_AVAILABLE, STATUS_PROCESS, Status
from telegram.handlers.bot_instance import bot
from telegram.models import Group, UserInGroup
from vacancy.models import Vacancy

logger = logging.getLogger(__name__)


class GroupService:
    @classmethod
    def update_invite_link(cls, group: Group) -> Group:
        """Read the existing primary invite link from Telegram (do NOT create a new one)."""
        chat = bot.get_chat(group.id)
        if chat.invite_link:
            group.invite_link = chat.invite_link
            group.save(update_fields=["invite_link"])
        else:
            logger.warning("group_no_invite_link", extra={"group_id": group.id})
        return group

    @classmethod
    def get_available_group(cls) -> Group | None:
        return Group.objects.filter(status=STATUS_AVAILABLE, is_active=True, invite_link__isnull=False).first()

    @classmethod
    def find_and_set_group(cls, vacancy: Vacancy) -> Group | None:
        group = cls.get_available_group()
        if group:
            vacancy.group = group
            vacancy.save()
            group.status = STATUS_PROCESS
            group.save()
            logger.info("group_assigned", extra={"group_id": group.id, "vacancy_id": vacancy.id})
            return group
        return None

    @classmethod
    def kick_user(cls, chat_id: int, user_id: int) -> None:
        try:
            bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                revoke_messages=False,
                until_date=int(time.time()) + 1,
            )
            logger.info("user_kicked", extra={"user_id": user_id, "group_id": chat_id})
        except Exception as e:
            logger.error("kick_failed", extra={"user_id": user_id, "group_id": chat_id, "error": str(e)})
        finally:
            try:
                bot.unban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    only_if_banned=True,
                )
            except Exception as e:
                logger.warning(f"Failed to unban {user_id=} from {chat_id=}: {e=}")

    @classmethod
    def kick_all_users(cls, group: Group, statuses: Iterable[str] | None = None) -> None:
        if not statuses:
            statuses = [Status.MEMBER, Status.OWNER]

        users: QuerySet[UserInGroup] = group.user_links.filter(status__in=statuses)
        for user_in_group in users:
            cls.kick_user(chat_id=group.id, user_id=user_in_group.user.id)
            user_in_group.status = Status.KICKED

        UserInGroup.objects.bulk_update(users, ["status"])

    @classmethod
    def set_default_permissions(cls, group: Group) -> bool:
        return bot.set_chat_permissions(
            chat_id=group.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
                can_manage_topics=False,
            ),
        )

    @classmethod
    def set_default_owner_permissions(cls, chat_id: int, user_id: int):
        try:
            bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_promote_members=False,
                can_restrict_members=True,
                can_delete_messages=True,
                can_pin_messages=True,
                can_invite_users=False,
                can_change_info=False,
                can_post_messages=False,
                can_edit_messages=False,
                is_anonymous=False,
                can_manage_chat=False,
                can_manage_video_chats=False,
                can_manage_voice_chats=False,
                can_manage_topics=False,
                can_post_stories=False,
                can_edit_stories=False,
                can_delete_stories=False,
            )
        except Exception as e:
            import logging

            logging.warning(f"Failed to promote owner {user_id=} in {chat_id=}: {e}")

    @classmethod
    def set_default_admin_permissions(cls, chat_id: int, user_id: int):
        try:
            bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_promote_members=True,
                can_edit_messages=True,
                can_delete_messages=True,
                can_pin_messages=True,
                can_change_info=False,
                can_post_messages=False,
                can_invite_users=False,
                can_restrict_members=False,
                is_anonymous=False,
                can_manage_chat=False,
                can_manage_video_chats=False,
                can_manage_voice_chats=False,
                can_manage_topics=False,
                can_post_stories=False,
                can_edit_stories=False,
                can_delete_stories=False,
            )
            logger.info("admin_promoted", extra={"user_id": user_id, "group_id": chat_id})
        except Exception:
            sentry_sdk.capture_exception()

    @classmethod
    def set_admin_custom_title(cls, chat_id: int, user_id: int, custom_title: str) -> None:
        try:
            bot.set_chat_administrator_custom_title(
                chat_id=chat_id,
                user_id=user_id,
                custom_title=custom_title,
            )
        except Exception:
            sentry_sdk.capture_exception()
