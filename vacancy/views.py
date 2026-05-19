from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from telegram.choices import CallStatus, CallType
from user.models import User, UserFeedback
from vacancy.choices import (
    STATUS_ACTIVE,
    STATUS_APPROVED,
    STATUS_AWAITING_PAYMENT,
    STATUS_CLOSED,
    STATUS_PAID,
    STATUS_PENDING,
    STATUS_SEARCH_STOPPED,
)
from vacancy.forms import VacancyCallForm, VacancyForm, VacancyUserFeedbackForm
from vacancy.models import Vacancy, VacancyUser, VacancyUserCall
from vacancy.services.call import create_vacancy_call
from vacancy.services.observers import events
from vacancy.services.observers.events import (
    VACANCY_AFTER_START_CALL_FAIL,
    VACANCY_AFTER_START_CALL_SUCCESS,
    VACANCY_NEW_FEEDBACK,
    VACANCY_REFIND,
    VACANCY_START_CALL_FAIL,
)
from vacancy.services.observers.subscriber_setup import vacancy_publisher


def vacancy_create(request):
    from user.services import BlockService

    if BlockService.is_blocked(request.user):
        return redirect("index")

    # Block new vacancy creation if employer has an unpaid completed vacancy
    for v in Vacancy.objects.filter(
        owner=request.user,
        second_rollcall_passed=True,
    ).exclude(status=STATUS_CLOSED):
        if not v.extra.get("is_paid"):
            messages.warning(request, "Спершу оплатіть попередню вакансію.")
            return redirect("vacancy:payment", pk=v.pk)

    work_profile = getattr(request.user, "work_profile", None)
    if request.method == "POST":
        vacancy_form = VacancyForm(request.POST, work_profile=work_profile)
        if vacancy_form.is_valid():
            # Защита от двойного создания: проверяем дубль за последние 60 секунд
            recent = Vacancy.objects.filter(
                owner=request.user,
                status=STATUS_PENDING,
                address=vacancy_form.cleaned_data.get("address", ""),
                date=vacancy_form.cleaned_data.get("date") or vacancy_form.cleaned_data.get("date_choice"),
                start_time=vacancy_form.cleaned_data.get("start_time"),
            ).first()
            if recent:
                return redirect("index")
            new_vacancy = vacancy_form.save(owner=request.user, status=STATUS_PENDING)
            vacancy_publisher.notify(events.VACANCY_CREATED, data={"vacancy": new_vacancy, "request": request})
            return redirect("index")

    else:
        # Pre-fill form from last vacancy as template (except date_choice)
        initial = {}
        last_vacancy = Vacancy.objects.filter(owner=request.user).order_by("-id").first()
        if last_vacancy:
            initial = {
                "gender": last_vacancy.gender,
                "people_count": last_vacancy.people_count,
                "has_passport": last_vacancy.has_passport,
                "address": last_vacancy.address,
                "map_link": last_vacancy.map_link,
                "payment_amount": last_vacancy.payment_amount,
                "payment_unit": last_vacancy.payment_unit,
                "payment_method": last_vacancy.payment_method,
                "skills": last_vacancy.skills,
                "contact_phone": request.user.contact_phone or last_vacancy.contact_phone,
            }
        # Auto-set start_time to now+1h (rounded to 15min) for today
        import datetime as d
        from datetime import datetime, timedelta

        from django.utils import timezone

        now = timezone.localtime(timezone.now())
        min_start = now + timedelta(hours=1)
        # Round up to nearest 15 minutes
        minute = min_start.minute
        rounded = ((minute + 14) // 15) * 15
        if rounded >= 60:
            min_start = min_start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            min_start = min_start.replace(minute=rounded, second=0, microsecond=0)

        min_start_time = d.time(min_start.hour, min_start.minute)

        # Read date choice from query param (for page reload on date switch)
        date_param = request.GET.get("date", "now")
        if date_param not in ("now", "tomorrow"):
            date_param = "now"
        initial["date_choice"] = date_param

        # Auto-adjust start_time if today and not set or too early
        if date_param == "now":
            current_start = initial.get("start_time")
            if not current_start or (isinstance(current_start, d.time) and current_start < min_start_time):
                initial["start_time"] = min_start_time

        # Auto-adjust end_time: must be start + 3h minimum (only for today)
        if date_param == "now":
            current_end = initial.get("end_time")
            start_for_end = initial.get("start_time", min_start_time)
            if isinstance(start_for_end, d.time):
                min_end_dt = datetime.combine(datetime.today(), start_for_end) + timedelta(hours=3)
                min_end_time = min_end_dt.time()
                if not current_end or (isinstance(current_end, d.time) and current_end <= start_for_end):
                    initial["end_time"] = min_end_time

        # For tomorrow: default start/end to 00:00 if coming from last vacancy with old times
        if date_param == "tomorrow":
            initial.setdefault("start_time", d.time(0, 0))
            initial.setdefault("end_time", d.time(0, 0))

        vacancy_form = VacancyForm(initial=initial, work_profile=work_profile)

    # First visit = employer has never created any vacancy
    is_first_visit = not Vacancy.objects.filter(owner=request.user).exists()
    return render(
        request,
        "vacancy/vacancy_form_page.html",
        {
            "form": vacancy_form,
            "is_first_visit": is_first_visit,
            "work_profile": work_profile,
        },
    )


def vacancy_check_call(request: WSGIRequest, form: VacancyCallForm, vacancy: Vacancy, call_type: CallType):
    if form.is_valid():
        users_queryset = form.fields["users"].queryset

        # Detect repeat attempt for AFTER_START before creating new records
        is_repeat_after_start = (
            call_type == CallType.AFTER_START
            and VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=CallType.AFTER_START).exists()
        )

        create_vacancy_call(
            vacancy=vacancy,
            call_type=call_type,
            status=CallStatus.CREATED,
        )
        selected_users = list(form.cleaned_data.get("users", []))
        vacancy_users_call = VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=call_type)
        vacancy_users_call.filter(vacancy_user__in=selected_users).update(
            status=CallStatus.CONFIRM,
        )

        if call_type == CallType.START:
            vacancy.extra["start_pre_call"] = "continue"
            (
                VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=CallType.BEFORE_START)
                .filter(vacancy_user__in=selected_users)
                .update(
                    status=CallStatus.CONFIRM,
                )
            )

        rejected_users: int = vacancy_users_call.exclude(vacancy_user__in=selected_users).update(
            status=CallStatus.REJECT,
        )
        extra_calls = vacancy.extra.get("calls", defaultdict(dict))
        extra_calls[call_type] = [i.user.id for i in selected_users]
        vacancy.extra.update({"calls": extra_calls})
        vacancy.save(update_fields=["extra"])

        # Mark rollcall as passed — stops reminder task
        if call_type == CallType.START:
            vacancy.first_rollcall_passed = True
            vacancy.save(update_fields=["first_rollcall_passed"])
        # AFTER_START: second_rollcall_passed set only on success (see else branch below)

        all_unchecked = len(selected_users) == 0 and users_queryset.exists()
        no_workers_ever = len(selected_users) == 0 and not users_queryset.exists()

        if no_workers_ever:
            # No workers existed at all — just close vacancy
            from vacancy.services.observers.events import VACANCY_CLOSE

            vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
        elif all_unchecked:
            if call_type == CallType.AFTER_START:
                # Don't kick employer; block them and send detailed admin notification
                from service.broadcast_service import TelegramBroadcastService
                from user.services import BlockService
                from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
                from vacancy.services.call_markup import get_admin_check_rollcall_markup

                BlockService.auto_block_employer_rollcall_fail(user=vacancy.owner)
                try:
                    from telegram.handlers.bot_instance import bot as _bot

                    _bot.send_message(
                        chat_id=vacancy.owner.id,
                        text="Друга перекличка не пройдена— Вас заблоковано! Зв'яжіться з Адміністратором для вирішення проблеми! @robochi_work_admin",
                    )
                except Exception:
                    pass
                broadcast = TelegramBroadcastService()
                broadcast.admin_broadcast(
                    text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_after_start_call_fail_detailed(),
                    parse_mode="HTML",
                    reply_markup=get_admin_check_rollcall_markup(vacancy),
                )
                vacancy_publisher.notify(VACANCY_AFTER_START_CALL_FAIL, data={"vacancy": vacancy})
            else:
                # START: kick employer + notify admin (existing behavior)
                from service.broadcast_service import TelegramBroadcastService
                from vacancy.models import VacancyContactPhone
                from vacancy.services.call_markup import get_admin_check_rollcall_markup

                if vacancy.group:
                    try:
                        from telegram.service.group import GroupService

                        GroupService.kick_user(chat_id=vacancy.group.id, user_id=vacancy.owner.id)
                    except Exception:
                        import sentry_sdk

                        sentry_sdk.capture_exception()
                owner = vacancy.owner
                cp = VacancyContactPhone.objects.filter(vacancy=vacancy, user=owner).first()
                owner_phone = cp.phone if cp else "—"
                username_line = f"<b>Username:</b> @{owner.username}\n" if owner.username else "<b>Username:</b> —\n"
                employer_block = (
                    f"<b>ID:</b> <code>{owner.pk}</code>\n"
                    f"<b>Ім'я:</b> {owner.full_name or '—'}\n" + username_line + f"<b>Телефон:</b> {owner_phone}\n"
                )
                invite_line = (
                    f"\nГрупа вакансії: {vacancy.group.invite_link}"
                    if vacancy.group and vacancy.group.invite_link
                    else ""
                )
                admin_text = (
                    f"ЗАКРИТИ ВАКАНСІЮ\n"
                    f"Замовник зняв усі відмітки на перекличці\n"
                    f"Вакансія: {vacancy.address}\n\n"
                    f"{employer_block}{invite_line}"
                )
                broadcast = TelegramBroadcastService()
                broadcast.admin_broadcast(
                    text=admin_text,
                    parse_mode="HTML",
                    reply_markup=get_admin_check_rollcall_markup(vacancy, CallType.START),
                )
                vacancy_publisher.notify(VACANCY_START_CALL_FAIL, data={"vacancy": vacancy})
        elif rejected_users > 0:
            if call_type == CallType.START:
                vacancy_publisher.notify(VACANCY_START_CALL_FAIL, data={"vacancy": vacancy})
            elif call_type == CallType.AFTER_START:
                from user.services import BlockService

                BlockService.auto_block_employer_rollcall_fail(user=vacancy.owner)
                try:
                    from telegram.handlers.bot_instance import bot as _bot

                    _bot.send_message(
                        chat_id=vacancy.owner.id,
                        text="Друга перекличка не пройдена— Вас заблоковано! Зв'яжіться з Адміністратором для вирішення проблеми! @robochi_work_admin",
                    )
                except Exception:
                    pass
                vacancy_publisher.notify(VACANCY_AFTER_START_CALL_FAIL, data={"vacancy": vacancy})
        else:
            if call_type == CallType.AFTER_START:
                if is_repeat_after_start:
                    from user.services import BlockService

                    BlockService.unblock_employer_rollcall_fail(user=vacancy.owner)
                vacancy.second_rollcall_passed = True
                vacancy.save(update_fields=["second_rollcall_passed"])
                vacancy_publisher.notify(VACANCY_AFTER_START_CALL_SUCCESS, data={"vacancy": vacancy})

        # Send bot notification about rollcall result
        try:
            from telegram.handlers.bot_instance import bot as _bot

            _confirmed = len(selected_users)
            _text = f"Перекличку пройдено. Підтверджено працівників: {_confirmed}."
            _bot.send_message(chat_id=vacancy.owner.id, text=_text)
        except Exception:
            pass
        return render(request, "vacancy/call_confirm.html", context={"form": form})
    return None


def vacancy_pre_call_check(request: WSGIRequest, pk: int, call_type: CallType):
    vacancy: Vacancy = get_object_or_404(Vacancy, pk=pk)
    members = vacancy.members
    members_count = members.count()
    people_count = vacancy.people_count

    if call_type == CallType.START:
        vacancy.extra["pre_call_start"] = True
        vacancy.save(update_fields=["extra"])

    # Check if continued search is still available (2h after start_time)
    from datetime import timedelta

    from django.utils import timezone

    from vacancy.tasks.call import _get_start_aware

    start_aware = _get_start_aware(vacancy)
    search_deadline = start_aware + timedelta(hours=2)
    can_search = timezone.now() < search_deadline and call_type == CallType.START

    # Scenario A: no workers at all
    if members_count == 0 and call_type == CallType.START:
        return render(
            request,
            "vacancy/pre_call.html",
            context={
                "pk": pk,
                "call_type": call_type,
                "scenario": "A",
                "vacancy": vacancy,
                "members_count": 0,
                "can_search": can_search,
            },
        )

    # Scenario B: workers exist but less than needed
    if members_count < people_count and call_type == CallType.START:
        form = VacancyCallForm(queryset=members, call_type=call_type, initial={"users": list(members)})
        return render(
            request,
            "vacancy/pre_call.html",
            context={
                "pk": pk,
                "call_type": call_type,
                "scenario": "B",
                "vacancy": vacancy,
                "members_count": members_count,
                "people_count": people_count,
                "can_search": can_search,
                "form": form,
            },
        )

    # Scenario C: enough workers — go straight to rollcall
    return redirect("vacancy:call", pk=pk, call_type=call_type)


def vacancy_start_refind(request: WSGIRequest, pk: int):
    vacancy = get_object_or_404(Vacancy, pk=pk)
    vacancy.extra["start_pre_call"] = "need"
    vacancy.save(update_fields=["extra"])

    vacancy_publisher.notify(VACANCY_REFIND, data={"vacancy": vacancy})
    return render(request, "vacancy/refind_start.html")


def vacancy_call(request: WSGIRequest, pk: int, call_type: CallType) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)
    users_queryset = vacancy.members
    form = VacancyCallForm(request.POST, queryset=users_queryset, call_type=call_type)

    if request.method == "POST":
        call_answer = vacancy_check_call(request=request, form=form, vacancy=vacancy, call_type=call_type)
        if call_answer:
            return call_answer
    else:
        any_records_exist = VacancyUserCall.objects.filter(
            vacancy_user__in=users_queryset,
            call_type=call_type,
        ).exists()
        if call_type == CallType.AFTER_START or (call_type == CallType.START and not any_records_exist):
            # Default all checkboxes to checked
            form = VacancyCallForm(
                queryset=users_queryset,
                call_type=call_type,
                initial={"users": list(users_queryset)},
            )
        else:
            initial_calls = VacancyUserCall.objects.filter(
                vacancy_user__in=users_queryset,
                status=CallStatus.CONFIRM,
                call_type=call_type,
            )
            form = VacancyCallForm(
                queryset=users_queryset,
                call_type=call_type,
                initial={"users": [user_call.vacancy_user for user_call in initial_calls]},
            )

    return render(
        request,
        "vacancy/call.html",
        context={
            "form": form,
            "call_type": call_type,
            "vacancy": vacancy,
            "second_rollcall_passed": vacancy.second_rollcall_passed,
        },
    )


def vacancy_user_feedback(request: WSGIRequest, pk: int, user_id: int) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = VacancyUserFeedbackForm(request.POST)
        if form.is_valid():
            rating = form.cleaned_data.get("rating") or "none"
            text = form.cleaned_data.get("text", "")
            feedback = UserFeedback.objects.create(
                owner=request.user,
                user=target_user,
                text=text,
                rating=rating,
                extra={"vacancy_id": vacancy.pk},
            )
            vacancy_publisher.notify(VACANCY_NEW_FEEDBACK, data={"vacancy": vacancy, "feedback": feedback})
            messages.success(request, _("Feedback has been sent."))
            return redirect("index")
    else:
        form = VacancyUserFeedbackForm()

    return render(
        request,
        "vacancy/vacancy_feedback.html",
        context={
            "form": form,
            "vacancy": vacancy,
            "target_user": target_user,
        },
    )


def vacancy_user_list(request: WSGIRequest, pk: int) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)

    all_users = [vm.user for vm in vacancy.members.select_related("user")]
    if vacancy.owner_id != request.user.id:
        all_users.append(vacancy.owner)
    users = [u for u in all_users if u.id != request.user.id]

    work_profile = getattr(request.user, "work_profile", None)
    user_role = work_profile.role if work_profile else None
    from vacancy.models import VacancyContactPhone

    _cp = VacancyContactPhone.objects.filter(vacancy=vacancy, user=vacancy.owner).first()
    contact_phone = _cp.phone if _cp else vacancy.contact_phone

    return render(
        request,
        "vacancy/vacancy_user_list.html",
        context={
            "vacancy": vacancy,
            "users": users,
            "user_role": user_role,
            "contact_phone": contact_phone,
        },
    )


def vacancy_user_reviews(request: WSGIRequest, pk: int, user_id: int) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)
    target_user = get_object_or_404(User, pk=user_id)

    feedbacks = UserFeedback.objects.filter(user=target_user).select_related("owner").order_by("-created_at")
    likes = feedbacks.filter(rating="like").count()
    dislikes = feedbacks.filter(rating="dislike").count()

    return render(
        request,
        "vacancy/vacancy_user_reviews.html",
        context={
            "vacancy": vacancy,
            "target_user": target_user,
            "feedbacks": feedbacks,
            "likes": likes,
            "dislikes": dislikes,
        },
    )


def vacancy_test_task(request):
    return HttpResponse(status=200)


@login_required
def vacancy_my_list(request):
    """List of all employer's vacancies with statuses."""
    target_user = request.user
    is_admin_view = False
    active_block = None

    if request.user.is_staff:
        for_user_id = request.GET.get("for_user")
        if for_user_id:
            target_user = get_object_or_404(User, pk=for_user_id)
            is_admin_view = True
            from user.services import BlockService

            active_block = BlockService.get_active_block(target_user)

    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone as _tz

    statuses = [
        STATUS_PENDING,
        STATUS_APPROVED,
        STATUS_ACTIVE,
        STATUS_SEARCH_STOPPED,
        STATUS_AWAITING_PAYMENT,
        STATUS_PAID,
    ]
    threshold_3h = _tz.now() - timedelta(hours=3)

    vacancies = (
        Vacancy.objects.filter(owner=target_user)
        .filter(
            Q(status__in=statuses)
            | Q(status=STATUS_CLOSED, closed_at__gte=threshold_3h)
            | Q(status=STATUS_CLOSED, extra__is_paid=True, closed_at__gte=threshold_3h)
        )
        .select_related("group", "channel")
        .order_by("-date", "-start_time")
    )

    STATUS_LABELS = {
        STATUS_PENDING: "Очікує модерації",
        STATUS_APPROVED: "Активна",
        STATUS_ACTIVE: "Активна",
        STATUS_SEARCH_STOPPED: "Пошук зупинено",
        STATUS_AWAITING_PAYMENT: "Очікує оплати",
        STATUS_CLOSED: "Закрита",
        STATUS_PAID: "Сплачено",
    }

    vacancy_list = []
    for v in vacancies:
        label = STATUS_LABELS.get(v.status, v.get_status_display())
        vacancy_list.append(
            {
                "vacancy": v,
                "status_label": label,
                "members_count": v.members.count(),
            }
        )

    return render(
        request,
        "vacancy/vacancy_my_list.html",
        {
            "vacancy_list": vacancy_list,
            "work_profile": getattr(request.user, "work_profile", None),
            "is_admin_view": is_admin_view,
            "target_user": target_user if is_admin_view else None,
            "active_block": active_block,
        },
    )


@login_required
def vacancy_detail(request, pk):
    """Detail page for a single vacancy with management buttons."""
    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)
    is_admin_view = request.user.is_staff and vacancy.owner_id != request.user.id

    STATUS_LABELS = {
        STATUS_PENDING: "Очікує модерації",
        STATUS_APPROVED: "Активна",
        STATUS_ACTIVE: "Активна",
        STATUS_SEARCH_STOPPED: "Пошук зупинено",
        STATUS_AWAITING_PAYMENT: "Очікує оплати",
        STATUS_CLOSED: "Закрита",
        STATUS_PAID: "Сплачено",
    }

    members = vacancy.members.select_related("user")

    can_stop_search = vacancy.search_active and vacancy.status != "pending"
    can_resume_search = (
        vacancy.status == STATUS_SEARCH_STOPPED and not vacancy.first_rollcall_passed and vacancy.status != "pending"
    )
    can_close = (
        vacancy.status not in [STATUS_CLOSED, STATUS_PENDING, STATUS_AWAITING_PAYMENT] and vacancy.closed_at is None
    )
    has_workers = members.count() > 0
    show_start_rollcall = (
        not vacancy.first_rollcall_passed
        and vacancy.status in [STATUS_APPROVED, STATUS_ACTIVE, STATUS_SEARCH_STOPPED]
        and has_workers
    )
    show_end_rollcall = (
        vacancy.first_rollcall_passed
        and not vacancy.second_rollcall_passed
        and vacancy.status != STATUS_CLOSED
        and has_workers
    )
    rollcall_type = "start" if show_start_rollcall else ("after_start" if show_end_rollcall else None)

    # Check if work time has started (for rollcall time gate)
    from datetime import datetime as _dt

    from django.utils import timezone as _tz

    _now = _tz.now()
    _start_naive = _dt.combine(vacancy.date, vacancy.start_time)
    _start_aware = _tz.make_aware(_start_naive, _tz.get_current_timezone())
    rollcall_time_reached = _now >= _start_aware or vacancy.extra.get("sent_start_call", False)
    is_closed_lifecycle = vacancy.status == STATUS_CLOSED or vacancy.closed_at is not None
    is_paid = vacancy.extra.get("is_paid", False)
    show_payment = vacancy.second_rollcall_passed and not is_paid

    return render(
        request,
        "vacancy/vacancy_detail.html",
        {
            "vacancy": vacancy,
            "status_label": STATUS_LABELS.get(vacancy.status, vacancy.get_status_display()),
            "members": members,
            "members_count": members.count(),
            "work_profile": getattr(request.user, "work_profile", None),
            "can_stop_search": can_stop_search,
            "can_resume_search": can_resume_search,
            "can_close": can_close,
            "show_start_rollcall": show_start_rollcall,
            "show_end_rollcall": show_end_rollcall,
            "rollcall_type": rollcall_type,
            "is_closed_lifecycle": is_closed_lifecycle,
            "is_paid": is_paid,
            "show_payment": show_payment,
            "channel_invite_link": vacancy.channel.invite_link if vacancy.channel else None,
            "channel_title": vacancy.channel.title if vacancy.channel else "",
            "is_pending": vacancy.status == "pending",
            "rollcall_time_reached": rollcall_time_reached,
            "has_workers": has_workers,
            "is_admin_view": is_admin_view,
        },
    )


@login_required
def vacancy_stop_search(request, pk):
    """Stop search: set STATUS_SEARCH_STOPPED, remove button from channel."""
    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    if vacancy.status in [STATUS_APPROVED, STATUS_ACTIVE]:
        from django.utils import timezone

        from service.notifications import NotificationMethod
        from service.telegram_strategy_factory import TelegramStrategyFactory
        from telegram.handlers.bot_instance import bot
        from telegram.models import ChannelMessage
        from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

        # Update channel message to "Пошук завершено" (no button)
        if vacancy.channel:
            text = VacancyTelegramTextFormatter(vacancy).for_channel(status="full")
            channel_message = (
                ChannelMessage.objects.filter(
                    channel_id=vacancy.channel.id,
                    extra__vacancy_id=vacancy.id,
                )
                .order_by("-id")
                .first()
            )
            if channel_message:
                strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
                try:
                    strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)
                except Exception as e:
                    import logging

                    logging.warning(f"Failed to update channel message: {e}")

        vacancy.status = STATUS_SEARCH_STOPPED
        vacancy.search_active = False
        vacancy.search_stopped_at = timezone.now()
        vacancy.extra["cancel_requested"] = True
        vacancy.save(update_fields=["status", "search_active", "search_stopped_at", "extra"])

    return redirect("vacancy:detail", pk=pk)


@login_required
def vacancy_continue_search(request, pk):
    """Quick resume search: auto-adjust time, republish in channel, no moderation."""
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from django.utils import timezone as _tz

    vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    # Auto-confirm rollcall if requested
    if request.GET.get("confirm_rollcall") == "1" and not vacancy.first_rollcall_passed:
        members = vacancy.members
        if members.exists():
            from vacancy.services.call import create_vacancy_call

            create_vacancy_call(vacancy=vacancy, call_type=CallType.START, status=CallStatus.CREATED)
            VacancyUserCall.objects.filter(vacancy_user__in=members, call_type=CallType.START).update(
                status=CallStatus.CONFIRM
            )
            vacancy.first_rollcall_passed = True
            vacancy.save(update_fields=["first_rollcall_passed"])

    # 1. Auto-adjust start_time
    now = _tz.localtime(_tz.now())
    new_start = now + _td(hours=1)
    # Round to next 15 min
    minute = (new_start.minute // 15 + 1) * 15
    if minute >= 60:
        new_start = new_start.replace(hour=new_start.hour + 1, minute=0, second=0, microsecond=0)
    else:
        new_start = new_start.replace(minute=minute, second=0, microsecond=0)

    vacancy.start_time = new_start.time()
    vacancy.date = now.date()

    # 2. Ensure minimum 3h shift
    end_naive = _dt.combine(vacancy.date, vacancy.end_time)
    end_aware = _tz.make_aware(end_naive, _tz.get_current_timezone())
    if vacancy.end_time < vacancy.start_time:
        end_aware += _td(days=1)
    diff = end_aware - _tz.make_aware(_dt.combine(vacancy.date, vacancy.start_time), _tz.get_current_timezone())
    if diff < _td(hours=3):
        new_end = _tz.make_aware(_dt.combine(vacancy.date, vacancy.start_time), _tz.get_current_timezone()) + _td(
            hours=3
        )
        vacancy.end_time = _tz.localtime(new_end).time()

    # 3. Re-activate search
    from vacancy.choices import STATUS_APPROVED

    vacancy.status = STATUS_APPROVED
    vacancy.search_active = True
    vacancy.search_stopped_at = None
    vacancy.save(update_fields=["start_time", "end_time", "date", "status", "search_active", "search_stopped_at"])

    # 4. Republish in channel
    from vacancy.services.observers.events import VACANCY_APPROVED
    from vacancy.services.observers.subscriber_setup import vacancy_publisher as _vp

    _vp.notify(VACANCY_APPROVED, data={"vacancy": vacancy})

    # 5. Send bot message
    try:
        from telegram.handlers.bot_instance import bot

        bot.send_message(
            chat_id=vacancy.owner.id,
            text=f"Повторний пошук розпочато. Адреса: {vacancy.address}",
        )
    except Exception:
        pass

    return redirect("vacancy:detail", pk=pk)


def vacancy_resume_search(request, pk):
    """Resume search after stop: re-submit vacancy for moderation."""
    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)
    work_profile = getattr(request.user, "work_profile", None)

    # Auto-confirm rollcall if coming from pre_call "Продовжити пошук"
    if request.GET.get("confirm_rollcall") == "1" and not vacancy.first_rollcall_passed:
        members = vacancy.members
        if members.exists():
            from vacancy.models import VacancyUserCall
            from vacancy.services.call import create_vacancy_call

            create_vacancy_call(vacancy=vacancy, call_type=CallType.START, status=CallStatus.CREATED)
            VacancyUserCall.objects.filter(vacancy_user__in=members, call_type=CallType.START).update(
                status=CallStatus.CONFIRM
            )
            vacancy.extra["start_pre_call"] = "continue"
            extra_calls = vacancy.extra.get("calls", {})
            extra_calls[CallType.START] = [m.user.id for m in members]
            vacancy.extra["calls"] = extra_calls
            vacancy.first_rollcall_passed = True
            vacancy.save(update_fields=["extra", "first_rollcall_passed"])

    if request.method == "POST":
        form = VacancyForm(request.POST, work_profile=work_profile, resume_mode=True)
        if form.is_valid():
            from datetime import timedelta

            from django.utils import timezone

            data = form.cleaned_data
            is_renewal = vacancy.extra.get("renewal_accepted", False)
            # address and map_link are readonly in resume_mode — preserve originals
            vacancy.gender = data["gender"]
            vacancy.people_count = data["people_count"]
            vacancy.has_passport = data["has_passport"]
            vacancy.date_choice = data.get("date_choice", vacancy.date_choice)
            if is_renewal:
                # Force date to tomorrow, reset rollcall state for the new day
                vacancy.date = timezone.localdate() + timedelta(days=1)
                vacancy.first_rollcall_passed = False
                vacancy.second_rollcall_passed = False
                vacancy.extra["pending_worker_renewal"] = True
            elif data.get("date"):
                vacancy.date = data["date"]
            vacancy.start_time = data["start_time"]
            vacancy.end_time = data["end_time"]
            vacancy.payment_amount = data["payment_amount"]
            vacancy.payment_unit = data["payment_unit"]
            vacancy.payment_method = data["payment_method"]
            vacancy.skills = data["skills"]
            vacancy.contact_phone = data.get("contact_phone", "")
            # Update VacancyContactPhone for employer
            _edit_phone = data.get("contact_phone", "")
            if _edit_phone:
                from vacancy.models import VacancyContactPhone

                VacancyContactPhone.objects.update_or_create(
                    vacancy=vacancy,
                    user=request.user,
                    defaults={"phone": _edit_phone},
                )
            print(f"RESUME_SEARCH: saving vacancy pk={vacancy.pk} id={vacancy.id} status={vacancy.status}")
            vacancy.status = STATUS_PENDING
            vacancy.search_active = False
            vacancy.search_stopped_at = None  # reset stop timer
            vacancy.save()
            vacancy_publisher.notify(events.VACANCY_CREATED, data={"vacancy": vacancy, "request": request})
            return redirect("vacancy:detail", pk=pk)
    else:
        initial = {
            "gender": vacancy.gender,
            "people_count": vacancy.people_count,
            "has_passport": vacancy.has_passport,
            "address": vacancy.address,
            "map_link": vacancy.map_link,
            "start_time": vacancy.start_time,
            "end_time": vacancy.end_time,
            "payment_amount": vacancy.payment_amount,
            "payment_unit": vacancy.payment_unit,
            "payment_method": vacancy.payment_method,
            "skills": vacancy.skills,
            "contact_phone": vacancy.contact_phone,
        }

        # Adjust start_time for continued search after work has started
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        from django.utils import timezone as _tz

        _now = _tz.localtime(_tz.now())
        _start_naive = _dt.combine(vacancy.date, vacancy.start_time)
        _start_aware = _tz.make_aware(_start_naive, _tz.get_current_timezone())
        if _now >= _start_aware:
            _min_start = _now + _td(hours=1)
            _minute = (_min_start.minute // 15 + 1) * 15
            if _minute >= 60:
                _min_start = _min_start.replace(hour=_min_start.hour + 1, minute=0, second=0, microsecond=0)
            else:
                _min_start = _min_start.replace(minute=_minute, second=0, microsecond=0)
            initial["start_time"] = _min_start.time()
            _orig_end = _dt.combine(vacancy.date, vacancy.end_time)
            _orig_end_aware = _tz.make_aware(_orig_end, _tz.get_current_timezone())
            if vacancy.end_time < vacancy.start_time:
                _orig_end_aware += _td(days=1)
            _new_end = _min_start + _td(hours=3)
            if _orig_end_aware > _new_end:
                pass  # keep original end_time
            else:
                initial["end_time"] = _new_end.time()

        form = VacancyForm(initial=initial, work_profile=work_profile, resume_mode=True)

    return render(
        request,
        "vacancy/vacancy_form_page.html",
        {
            "form": form,
            "resume_mode": True,
            "vacancy": vacancy,
            "work_profile": work_profile,
        },
    )


@login_required
def vacancy_close_lifecycle(request, pk):
    """Start vacancy close: set closed_at timer (Celery will kick users after 3h)."""
    if request.method != "POST":
        return redirect("vacancy:detail", pk=pk)

    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    if vacancy.status not in [STATUS_CLOSED, STATUS_PENDING, STATUS_AWAITING_PAYMENT]:
        from django.utils import timezone

        from service.broadcast_service import TelegramBroadcastService
        from service.notifications import NotificationMethod
        from service.notifications_impl import TelegramNotifier
        from service.telegram_strategy_factory import TelegramStrategyFactory
        from telegram.handlers.bot_instance import bot
        from telegram.models import ChannelMessage
        from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

        # Update channel message to remove button
        if vacancy.channel:
            text = VacancyTelegramTextFormatter(vacancy).for_channel(status="full")
            channel_message = (
                ChannelMessage.objects.filter(
                    channel_id=vacancy.channel.id,
                    extra__vacancy_id=vacancy.id,
                )
                .order_by("-id")
                .first()
            )
            if channel_message:
                strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
                try:
                    strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)
                except Exception as e:
                    import logging

                    logging.warning(f"Failed to update channel message on close: {e}")

        vacancy.status = STATUS_CLOSED
        vacancy.closed_at = timezone.now()
        vacancy.search_active = False
        vacancy.extra["cancel_requested"] = True
        vacancy.save(update_fields=["status", "closed_at", "search_active", "extra"])

        # Notify admins about manual close
        try:
            notifier = TelegramNotifier(bot)
            broadcast = TelegramBroadcastService(notifier=notifier)
            group_link = vacancy.group.invite_link if vacancy.group and vacancy.group.invite_link else "—"
            broadcast.admin_broadcast(
                text=(
                    f"\U0001f4cb Замовник закрив вакансію #{vacancy.pk}\n"
                    f"\U0001f4cd {vacancy.address}\n"
                    f"\U0001f464 {vacancy.owner.first_name} (@{vacancy.owner.username or chr(8212)})\n"
                    f"\U0001f4ac Група: {group_link}\n"
                    f"\u23f3 Групу буде розпущено через 3 години."
                ),
            )
        except Exception as e:
            import logging

            logging.warning(f"Failed to notify admins on vacancy close: {e}")

    return redirect("vacancy:detail", pk=pk)


@login_required
def vacancy_payment(request, pk):
    """Invoice creation and payment page for vacancy owner."""
    from payment.models import MonobankPayment
    from vacancy.services.invoice import get_vacancy_invoice_amount

    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)
    amount = get_vacancy_invoice_amount(vacancy)  # UAH
    workers_count = len(vacancy.extra.get("calls", {}).get("after_start", []))

    is_paid = (
        vacancy.extra.get("is_paid")
        or MonobankPayment.objects.filter(
            vacancy=vacancy,
            status=MonobankPayment.Status.SUCCESS,
        ).exists()
    )

    if request.method == "POST" and not is_paid:
        from payment.services import create_invoice

        try:
            payment = create_invoice(
                user=request.user,
                vacancy=vacancy,
                amount_kopecks=amount * 100,
                description=f"Оплата за вакансію #{vacancy.pk} — {vacancy.address}",
            )
            return redirect(payment.page_url)
        except Exception as e:
            import logging

            logging.warning(f"Monobank invoice creation failed for vacancy {vacancy.pk}: {e}")
            return render(
                request,
                "vacancy/vacancy_payment.html",
                {
                    "vacancy": vacancy,
                    "amount": amount,
                    "workers_count": workers_count,
                    "is_paid": False,
                    "error": "Помилка створення рахунку. Спробуйте пізніше.",
                },
            )

    return render(
        request,
        "vacancy/vacancy_payment.html",
        {
            "vacancy": vacancy,
            "amount": amount,
            "workers_count": workers_count,
            "is_paid": is_paid,
        },
    )


@login_required
def vacancy_members(request, pk):
    """Page showing all users who joined the vacancy group."""
    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    all_users = VacancyUser.objects.filter(vacancy=vacancy).select_related("user").order_by("-created_at")
    if not request.user.is_staff:
        all_users = all_users.exclude(user=vacancy.owner)

    user_role = "admin" if request.user.is_staff else ("employer" if request.user == vacancy.owner else None)

    from user.services import BlockService
    from vacancy.models import VacancyContactPhone

    # Build contact phone lookup for this vacancy
    contact_phones = dict(VacancyContactPhone.objects.filter(vacancy=vacancy).values_list("user_id", "phone"))

    members_list = []
    for vu in all_users:
        feedbacks = UserFeedback.objects.filter(user=vu.user).count()
        is_user_blocked = BlockService.is_blocked(vu.user)
        members_list.append(
            {
                "vacancy_user": vu,
                "user": vu.user,
                "status": vu.get_status_display(),
                "is_member": vu.status == "member",
                "is_blocked": is_user_blocked,
                "feedbacks_count": feedbacks,
                "contact_phone": contact_phones.get(vu.user_id, ""),
            }
        )

    return render(
        request,
        "vacancy/vacancy_members.html",
        {
            "vacancy": vacancy,
            "members_list": members_list,
            "work_profile": getattr(request.user, "work_profile", None),
            "user_role": user_role,
        },
    )


@login_required
def vacancy_send_contact(request: WSGIRequest, pk: int) -> JsonResponse:
    """Send vacancy owner's contact phone to the worker via bot."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)

    work_profile = getattr(request.user, "work_profile", None)
    if not work_profile or work_profile.role != "worker":
        return JsonResponse({"ok": False, "error": "Only workers can request contacts"}, status=403)

    vacancy = get_object_or_404(Vacancy, pk=pk)

    from vacancy.models import VacancyContactPhone

    contact = VacancyContactPhone.objects.filter(vacancy=vacancy, user=vacancy.owner).first()
    phone = contact.phone if contact else None
    if not phone:
        return JsonResponse({"ok": False, "error": "Телефон замовника не вказано"})

    try:
        from telegram.handlers.bot_instance import bot

        text = f"Контактний телефон замовника за вакансією {vacancy.address}: {phone}"
        bot.send_message(chat_id=request.user.telegram_id, text=text)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})

    return JsonResponse({"ok": True})


@login_required
def vacancy_feedback_redirect(request, pk):
    """Entry point from group 'Відгуки/Контакти' button. Routes by role."""
    vacancy = get_object_or_404(Vacancy, pk=pk)
    if request.user.is_staff or request.user == vacancy.owner:
        return redirect("vacancy:members", pk=pk)
    return redirect("work:worker_my_work")


@login_required
def vacancy_kick_member(request, pk, user_id):
    """Kick a worker from vacancy group."""
    if request.method != "POST":
        return redirect("vacancy:members", pk=pk)

    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    from telegram.service.group import GroupService

    if vacancy.group:
        GroupService.kick_user(chat_id=vacancy.group.id, user_id=user_id)

    return redirect("vacancy:members", pk=pk)


def vacancy_members_json(request, pk):
    """JSON endpoint for auto-refresh: returns members count and list."""
    from django.http import JsonResponse

    vacancy = get_object_or_404(Vacancy, pk=pk)
    members = vacancy.members.select_related("user")
    data = {
        "members_count": members.count(),
        "people_count": vacancy.people_count,
        "members": [{"id": m.user.id, "name": m.user.full_name or f"ID {m.user.id}"} for m in members],
        "first_rollcall_passed": vacancy.first_rollcall_passed,
        "second_rollcall_passed": vacancy.second_rollcall_passed,
        "status": vacancy.status,
    }
    return JsonResponse(data)
