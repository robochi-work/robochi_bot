import logging
import time
from collections.abc import Iterable

import sentry_sdk
from django.db.models import F, QuerySet
from telebot.types import ChatPermissions

from telegram.choices import STATUS_AVAILABLE, STATUS_PROCESS, Status
from telegram.handlers.bot_instance import bot
from telegram.models import Group, UserInGroup
from vacancy.models import Vacancy

logger = logging.getLogger(__name__)


class GroupService:
    @classmethod
    def update_invite_link(cls, group: Group) -> Group:
        """No-op: invite links are managed manually via Django admin, not by the bot."""
        logger.info("update_invite_link is no-op, links managed via admin", extra={"group_id": group.id})
        return group

    @classmethod
    def get_available_group(cls) -> Group | None:
        from django.db.models import Count, Q

        return (
            Group.objects.filter(status=STATUS_AVAILABLE, is_active=True, invite_link__isnull=False)
            .annotate(
                active_users=Count(
                    "user_links",
                    filter=Q(user_links__status__in=[Status.MEMBER, Status.OWNER]),
                ),
            )
            .filter(active_users=0)
            .order_by(F("last_used_at").asc(nulls_first=True))
            .first()
        )

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
        user_ids = list(users.values_list("user_id", flat=True))
        for uid in user_ids:
            cls.kick_user(chat_id=group.id, user_id=uid)

        group.user_links.filter(user_id__in=user_ids).delete()

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
                can_restrict_members=False,
                can_delete_messages=False,
                can_pin_messages=False,
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

    @classmethod
    def set_member_tag(cls, chat_id: int, user_id: int, tag: str) -> None:
        try:
            bot.set_chat_member_tag(chat_id=chat_id, user_id=user_id, tag=tag)
            logger.info("member_tag_set", extra={"user_id": user_id, "group_id": chat_id, "tag": tag})
        except Exception as e:
            logger.warning(f"Failed to set tag for {user_id=} in {chat_id=}: {e}")

    @classmethod
    def reset_group(cls, group: Group) -> None:
        """Full group reset: delete messages, kick everyone (except bot & creator), reset permissions."""
        chat_id = group.id

        try:
            bot_id = bot.get_me().id
        except Exception:
            bot_id = None

        # 1. Get pinned message ID BEFORE unpinning (to know max message range)
        max_msg_id = 0
        try:
            chat = bot.get_chat(chat_id)
            if chat.pinned_message:
                max_msg_id = chat.pinned_message.message_id
        except Exception as e:
            logger.warning(f"reset_group: get_chat failed: {e}")

        # Also check GroupMessage DB
        from telegram.models import GroupMessage

        db_max = (
            GroupMessage.objects.filter(group=group)
            .order_by("-message_id")
            .values_list("message_id", flat=True)
            .first()
        )
        if db_max:
            max_msg_id = max(max_msg_id, db_max)

        # Fallback: if we still don't know max ID, use a reasonable default
        if max_msg_id == 0:
            max_msg_id = 500

        # 2. Unpin all messages
        try:
            bot.unpin_all_chat_messages(chat_id=chat_id)
            logger.info("reset_group: unpinned all", extra={"group_id": chat_id})
        except Exception as e:
            logger.warning(f"reset_group: unpin failed: {e}")

        # 3. Delete ALL messages one by one (skip ID=1 — undeletable group creation msg)
        upper = max_msg_id + 100
        deleted_count = 0
        for msg_id in range(2, upper + 1):
            try:
                bot.delete_message(chat_id=chat_id, message_id=msg_id)
                deleted_count += 1
            except Exception:
                pass
        logger.info(
            f"reset_group: deleted {deleted_count} messages (range 2..{upper})",
            extra={"group_id": chat_id},
        )

        # 4. Get ALL admins from Telegram API (not from our DB)
        creator_id = None
        telegram_admin_ids = []
        try:
            admins = bot.get_chat_administrators(chat_id)
            for admin in admins:
                if admin.user.is_bot:
                    continue
                if admin.status == "creator":
                    creator_id = admin.user.id
                    continue
                telegram_admin_ids.append(admin.user.id)
        except Exception as e:
            logger.warning(f"reset_group: get_chat_administrators failed: {e}")

        # 5. Demote and kick admins (from Telegram API)
        for uid in telegram_admin_ids:
            try:
                bot.promote_chat_member(
                    chat_id=chat_id,
                    user_id=uid,
                    can_promote_members=False,
                    can_edit_messages=False,
                    can_delete_messages=False,
                    can_pin_messages=False,
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
            except Exception as e:
                logger.warning(f"reset_group: demote admin {uid} failed: {e}")
            try:
                bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=uid,
                    revoke_messages=False,
                    until_date=int(time.time()) + 1,
                )
            except Exception as e:
                logger.warning(f"reset_group: ban admin {uid} failed: {e}")
            try:
                bot.unban_chat_member(chat_id=chat_id, user_id=uid, only_if_banned=True)
            except Exception as e:
                logger.warning(f"reset_group: unban admin {uid} failed: {e}")

        # 6. Kick regular users from UserInGroup (workers, employers)
        all_uig = UserInGroup.objects.filter(group=group)
        for uig in all_uig:
            if uig.user_id == bot_id or uig.user_id == creator_id:
                continue
            if uig.user_id in telegram_admin_ids:
                continue  # already handled above
            try:
                bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=uig.user_id,
                    revoke_messages=False,
                    until_date=int(time.time()) + 1,
                )
            except Exception as e:
                logger.warning(f"reset_group: kick user {uig.user_id} failed: {e}")
            try:
                bot.unban_chat_member(chat_id=chat_id, user_id=uig.user_id, only_if_banned=True)
            except Exception:
                pass

        # 7. Delete ALL UserInGroup records
        all_uig.delete()
        logger.info("reset_group: UserInGroup cleaned", extra={"group_id": chat_id})

        # 8. Reset group permissions
        try:
            cls.set_default_permissions(group)
            logger.info("reset_group: permissions reset", extra={"group_id": chat_id})
        except Exception as e:
            logger.warning(f"reset_group: permissions reset failed: {e}")

        # 9. Clean GroupMessage DB records
        GroupMessage.objects.filter(group=group).delete()
