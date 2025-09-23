from telebot.types import ChatMemberUpdated, ChatPermissions, ChatJoinRequest

from telegram.models import Group, UserInGroup, Status
from telegram.handlers.bot_instance import bot
from telegram.service.group import GroupService
from user.models import User
from vacancy.choices import STATUS_APPROVED, STATUS_ACTIVE, GENDER_ANY
from vacancy.models import Vacancy, VacancyUser

from vacancy.services.observers import events
from vacancy.services.observers.subscriber_setup import vacancy_publisher


@bot.chat_join_request_handler(func=lambda c: True)
def auto_approve(req: ChatJoinRequest):
    try:
        user, created = User.objects.update_or_create(
            id=req.from_user.id,
            defaults={
                'username': req.from_user.username,
            }
        )

        if user.is_staff:
            bot.approve_chat_join_request(req.chat.id, req.from_user.id)
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

        if not user.is_active:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
            return

        group, _ = Group.objects.update_or_create(
            id=req.chat.id,
            defaults={
                'title': req.chat.title or '',
            }
        )
        vacancy = Vacancy.objects.get(
            status__in=[STATUS_APPROVED, STATUS_ACTIVE],
            group=group,
        )

        filters = [
            vacancy.members.count() < vacancy.people_count,
            (vacancy.gender == user.gender) or vacancy.gender == GENDER_ANY,
        ]

        if all(filters) or vacancy.owner == user:
            bot.approve_chat_join_request(req.chat.id, req.from_user.id)
        else:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)

    except Exception as e:
        try:
            bot.decline_chat_join_request(req.chat.id, req.from_user.id)
        except Exception as ex:
            ...

@bot.chat_member_handler()
def handle_user_status_change(event: ChatMemberUpdated):
    user_data = event.new_chat_member.user
    if user_data.is_bot:
        return
    if event.old_chat_member.status in ['kicked', 'left'] and event.new_chat_member.status in ['kicked', 'left']:
        return
    if event.new_chat_member.status in [Status.ADMINISTRATOR.value]:
        return

    group, _ = Group.objects.update_or_create(
        id=event.chat.id,
        defaults={
            'title': event.chat.title or '',
        }
    )

    user, created = User.objects.update_or_create(
        id=user_data.id,
        defaults={
            'username': user_data.username,
        }
    )

    vacancy = Vacancy.objects.get(
        status__in=[STATUS_APPROVED, STATUS_ACTIVE],
        group=group,
    )

    status = event.new_chat_member.status
    if status not in ['kicked', 'left',]:

        if not status in Status.values:
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


        UserInGroup.objects.update_or_create(
            user=user,
            group=group,
            defaults={'status': status}
        )
        VacancyUser.objects.update_or_create(
            user=user,
            vacancy=vacancy,
            status=status,
        )

        vacancy_publisher.notify(events.VACANCY_NEW_MEMBER, data={'vacancy': vacancy, })
    else:
        UserInGroup.objects.filter(user=user, group=group).delete()
        VacancyUser.objects.filter(user=user, vacancy=vacancy).update(status=Status.LEFT)
        GroupService.kick_user(
            chat_id=event.chat.id,
            user_id=event.new_chat_member.user.id,
        )

        if not vacancy.owner == user and not user.is_staff:
            vacancy_publisher.notify(events.VACANCY_LEFT_MEMBER, data={'vacancy': vacancy, })
