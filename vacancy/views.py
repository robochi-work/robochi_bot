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
    for v in Vacancy.objects.filter(owner=request.user, second_rollcall_passed=True).exclude(status=STATUS_CLOSED):
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
            from vacancy.services.auto_approve import try_auto_approve

            if try_auto_approve(new_vacancy):
                from vacancy.services.observers.events import VACANCY_APPROVED

                vacancy_publisher.notify(VACANCY_APPROVED, data={"vacancy": new_vacancy})
            else:
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

        create_vacancy_call(vacancy=vacancy, call_type=call_type, status=CallStatus.CREATED)
        selected_users = list(form.cleaned_data.get("users", []))
        vacancy_users_call = VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=call_type)
        vacancy_users_call.filter(vacancy_user__in=selected_users).update(status=CallStatus.CONFIRM)

        if call_type == CallType.START:
            vacancy.extra["start_pre_call"] = "continue"
            (
                VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=CallType.BEFORE_START)
                .filter(vacancy_user__in=selected_users)
                .update(status=CallStatus.CONFIRM)
            )

        rejected_users: int = vacancy_users_call.exclude(vacancy_user__in=selected_users).update(
            status=CallStatus.REJECT
        )
        extra_calls = vacancy.extra.get("calls", defaultdict(dict))
        extra_calls[call_type] = [i.user.id for i in selected_users]
        vacancy.extra.update({"calls": extra_calls})
        vacancy.save(update_fields=["extra"])

        # Mark rollcall as passed — stops reminder task
        if call_type == CallType.START:
            vacancy.first_rollcall_passed = True
            vacancy.save(update_fields=["first_rollcall_passed"])
            # Save snapshot of confirmed workers for the 2nd rollcall
            from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot

            save_first_rollcall_snapshot(vacancy, [vu.user_id for vu in selected_users])
        # AFTER_START: second_rollcall_passed set only on success (see else branch below)

        all_unchecked = len(selected_users) == 0 and users_queryset.exists()
        no_workers_ever = len(selected_users) == 0 and not users_queryset.exists()

        if no_workers_ever:
            # No workers existed at all — just close vacancy
            from vacancy.services.observers.events import VACANCY_CLOSE

            vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
        elif call_type == CallType.AFTER_START and (all_unchecked or rejected_users > 0):
            # === Disputed 2nd rollcall: Scenario Б (partial uncheck) or В (full uncheck) ===
            from service.broadcast_service import TelegramBroadcastService
            from service.notifications_impl import TelegramNotifier
            from telegram.handlers.bot_instance import bot as _bot
            from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
            from vacancy.services.call_markup import get_admin_check_rollcall_markup
            from vacancy.services.disputed_rollcall import mark_disputed
            from vacancy.services.rollcall_snapshot import get_snapshot_user_ids

            selected_ids = [vu.user_id for vu in selected_users]
            snapshot_ids = get_snapshot_user_ids(vacancy) or [vu.user_id for vu in vacancy.members]
            rejected_ids = [uid for uid in snapshot_ids if uid not in set(selected_ids)]

            mark_disputed(
                vacancy,
                first_count=len(snapshot_ids),
                selected_user_ids=selected_ids,
                rejected_user_ids=rejected_ids,
                is_full_uncheck=all_unchecked,
            )

            if all_unchecked:
                # Scenario В: kick employer + block + replace bot message with 'Ви заблоковані!'
                if vacancy.group:
                    try:
                        from telegram.service.group import GroupService

                        GroupService.kick_user(chat_id=vacancy.group.id, user_id=vacancy.owner.id)
                    except Exception:
                        import sentry_sdk

                        sentry_sdk.capture_exception()
                from user.services import BlockService

                BlockService.auto_block_employer_rollcall_fail(user=vacancy.owner)

                # Delete the old 'final_call' message (now obsolete)
                old_msg_id = (vacancy.extra or {}).get("final_call_msg_id")
                if old_msg_id:
                    try:
                        _bot.delete_message(chat_id=vacancy.owner.id, message_id=old_msg_id)
                    except Exception:
                        pass
                # Send new 'blocked' message with 2 buttons
                try:
                    from django.conf import settings
                    from django.urls import reverse
                    from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

                    detail_url = (
                        settings.BASE_URL.rstrip("/") + reverse("vacancy:detail", args=[vacancy.id]) + "?focus=rollcall"
                    )
                    kb = InlineKeyboardMarkup()
                    kb.row(InlineKeyboardButton("До переклички", web_app=WebAppInfo(url=detail_url)))
                    kb.row(InlineKeyboardButton("Зв'язатися з адміністратором", url="https://t.me/robochi_work_admin"))
                    sent = _bot.send_message(
                        chat_id=vacancy.owner.id,
                        text=(
                            "Ви заблоковані! Пройдіть другу перекличку повторно "
                            "або зв'яжіться з Адміністратором для розблокування."
                        ),
                        reply_markup=kb,
                    )
                    if sent and hasattr(sent, "message_id"):
                        vacancy.extra["final_call_msg_id"] = sent.message_id
                        vacancy.save(update_fields=["extra"])
                except Exception:
                    import sentry_sdk

                    sentry_sdk.capture_exception()
            else:
                # Scenario Б: employer not touched; remind via Celery task (3.C)
                pass

            # Notify admins (both scenarios) — FIX 500: pass notifier to broadcast service
            broadcast = TelegramBroadcastService(notifier=TelegramNotifier(_bot))
            broadcast.admin_broadcast(
                text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_after_start_call_fail_detailed(),
                parse_mode="HTML",
                reply_markup=get_admin_check_rollcall_markup(vacancy),
            )
        elif all_unchecked:
            # START rollcall: kick employer + notify admin (existing behavior)
            from service.broadcast_service import TelegramBroadcastService
            from service.notifications_impl import TelegramNotifier
            from telegram.handlers.bot_instance import bot as _bot
            from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
            from vacancy.services.call_markup import get_admin_check_rollcall_markup

            if vacancy.group:
                try:
                    from telegram.service.group import GroupService

                    GroupService.kick_user(chat_id=vacancy.group.id, user_id=vacancy.owner.id)
                except Exception:
                    import sentry_sdk

                    sentry_sdk.capture_exception()
            broadcast = TelegramBroadcastService(notifier=TelegramNotifier(_bot))
            broadcast.admin_broadcast(
                text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_all_unchecked(CallType.START),
                parse_mode="HTML",
                reply_markup=get_admin_check_rollcall_markup(vacancy, CallType.START),
            )
            vacancy_publisher.notify(VACANCY_START_CALL_FAIL, data={"vacancy": vacancy})
        elif rejected_users > 0:
            if call_type == CallType.START:
                vacancy_publisher.notify(VACANCY_START_CALL_FAIL, data={"vacancy": vacancy})
        else:
            if call_type == CallType.AFTER_START:
                if is_repeat_after_start:
                    from user.services import BlockService

                    BlockService.unblock_employer_rollcall_fail(user=vacancy.owner)
                vacancy.second_rollcall_passed = True
                vacancy.save(update_fields=["second_rollcall_passed"])
                vacancy_publisher.notify(VACANCY_AFTER_START_CALL_SUCCESS, data={"vacancy": vacancy})

                # Scenario B: not enough workers after confirmed rollcall
        if call_type == CallType.START and len(selected_users) < vacancy.people_count:
            try:
                from service.broadcast_service import TelegramBroadcastService
                from service.notifications_impl import TelegramNotifier
                from telegram.handlers.bot_instance import bot as _bot_b
                from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

                broadcast = TelegramBroadcastService(notifier=TelegramNotifier(_bot_b))
                broadcast.admin_broadcast(
                    text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_scenario_b(
                        confirmed=len(selected_users),
                        needed=vacancy.people_count,
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
        # Send bot notification about rollcall result
        try:
            from telegram.handlers.bot_instance import bot as _bot

            _confirmed = len(selected_users)
            _text = f"Перекличку пройдено. Підтверджено працівників: {_confirmed}."
            _bot.send_message(chat_id=vacancy.owner.id, text=_text)
        except Exception:
            pass
        return render(request, "vacancy/call_confirm.html", context={"form": form, "vacancy": vacancy})
    return None


def vacancy_pre_call_check(request: WSGIRequest, pk: int, call_type: CallType):
    return redirect("vacancy:detail", pk=pk)


def vacancy_start_refind(request: WSGIRequest, pk: int):
    vacancy = get_object_or_404(Vacancy, pk=pk)
    vacancy.extra["start_pre_call"] = "need"
    vacancy.save(update_fields=["extra"])

    vacancy_publisher.notify(VACANCY_REFIND, data={"vacancy": vacancy})
    return render(request, "vacancy/refind_start.html")


def vacancy_call(request: WSGIRequest, pk: int, call_type: CallType) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)
    # 2nd rollcall uses snapshot from the 1st rollcall (workers who left are still shown)
    if call_type == CallType.AFTER_START:
        from vacancy.services.rollcall_snapshot import get_snapshot_vacancy_users

        users_queryset = get_snapshot_vacancy_users(vacancy)
    else:
        users_queryset = vacancy.members
    form = VacancyCallForm(request.POST, queryset=users_queryset, call_type=call_type)

    if request.method == "POST":
        call_answer = vacancy_check_call(request=request, form=form, vacancy=vacancy, call_type=call_type)
        if call_answer:
            return call_answer
    else:
        any_records_exist = VacancyUserCall.objects.filter(
            vacancy_user__in=users_queryset, call_type=call_type
        ).exists()
        if call_type == CallType.AFTER_START or (call_type == CallType.START and not any_records_exist):
            # Default all checkboxes to checked
            form = VacancyCallForm(
                queryset=users_queryset, call_type=call_type, initial={"users": list(users_queryset)}
            )
        else:
            initial_calls = VacancyUserCall.objects.filter(
                vacancy_user__in=users_queryset, status=CallStatus.CONFIRM, call_type=call_type
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

    # Check if user already left feedback for this person on this vacancy
    already_exists = UserFeedback.objects.filter(
        owner=request.user,
        user=target_user,
        is_auto=False,
        extra__vacancy_id=vacancy.pk,
    ).exists()

    if request.method == "POST":
        if already_exists:
            messages.error(request, _("Ви вже залишили відгук цьому користувачу."))
            return redirect("vacancy:detail", pk=pk)
        form = VacancyUserFeedbackForm(request.POST)
        if form.is_valid():
            rating = form.cleaned_data.get("rating") or "none"
            text = form.cleaned_data.get("text", "")
            feedback = UserFeedback.objects.create(
                owner=request.user, user=target_user, text=text, rating=rating, extra={"vacancy_id": vacancy.pk}
            )
            vacancy_publisher.notify(VACANCY_NEW_FEEDBACK, data={"vacancy": vacancy, "feedback": feedback})
            messages.success(request, _("Feedback has been sent."))
            return redirect("vacancy:detail", pk=pk)
    else:
        form = VacancyUserFeedbackForm()

    work_profile = getattr(request.user, "work_profile", None)
    user_role = work_profile.role if work_profile else None

    return render(
        request,
        "vacancy/vacancy_feedback.html",
        context={
            "form": form,
            "vacancy": vacancy,
            "target_user": target_user,
            "user_role": user_role,
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

    from user.rating import bayesian_rating

    rating_percent = bayesian_rating(likes, dislikes)

    work_profile = getattr(request.user, "work_profile", None)
    user_role = work_profile.role if work_profile else None

    return render(
        request,
        "vacancy/vacancy_user_reviews.html",
        context={
            "vacancy": vacancy,
            "target_user": target_user,
            "feedbacks": feedbacks,
            "likes": likes,
            "dislikes": dislikes,
            "rating_percent": rating_percent,
            "user_role": user_role,
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
        STATUS_SEARCH_STOPPED: "Пошук зупинено",
        STATUS_AWAITING_PAYMENT: "Сплатити рахунок",
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


def _build_members_context(vacancy, request):
    """Build context for members section embedded in vacancy detail."""
    from datetime import timedelta

    from django.utils import timezone

    from telegram.choices import CallStatus, CallType
    from user.models import UserFeedback
    from user.services import BlockService
    from vacancy.forms import VacancyCallForm
    from vacancy.models import VacancyContactPhone, VacancyUserCall
    from vacancy.tasks.call import _get_start_aware

    now = timezone.now()
    start_aware = _get_start_aware(vacancy)
    rollcall_time_reached = now >= start_aware or vacancy.extra.get("sent_start_call", False)

    is_start_rollcall = (
        not vacancy.first_rollcall_passed
        and vacancy.status in [STATUS_APPROVED, STATUS_SEARCH_STOPPED]
        and rollcall_time_reached
    )
    is_end_rollcall = (
        vacancy.first_rollcall_passed
        and not vacancy.second_rollcall_passed
        and vacancy.status != STATUS_CLOSED
        and vacancy.extra.get("sent_final_call", False)
    )
    is_rollcall_mode = is_start_rollcall or is_end_rollcall

    call_type = None
    if is_start_rollcall:
        call_type = CallType.START
    elif is_end_rollcall:
        call_type = CallType.AFTER_START

    members_qs = vacancy.members
    m_members_count = members_qs.count()
    m_people_count = vacancy.people_count

    # For the 2nd rollcall use snapshot from the 1st rollcall so that
    # workers who left/were kicked between rollcalls are still shown.
    if call_type == CallType.AFTER_START:
        from vacancy.services.rollcall_snapshot import get_snapshot_vacancy_users

        rollcall_qs = get_snapshot_vacancy_users(vacancy)
    else:
        rollcall_qs = members_qs

    scenario = None
    can_search_members = False
    if is_start_rollcall:
        search_deadline = start_aware + timedelta(hours=2)
        can_search_members = now < search_deadline
        if m_members_count == 0:
            scenario = "A"
        elif m_members_count < m_people_count:
            scenario = "B"
        else:
            scenario = "C"

    if is_rollcall_mode:
        if call_type == CallType.AFTER_START:
            all_users_qs = rollcall_qs.order_by("-created_at")
        else:
            all_users_qs = (
                VacancyUser.objects.filter(vacancy=vacancy, status="member")
                .select_related("user")
                .order_by("-created_at")
            )
        if not request.user.is_staff:
            all_users_qs = all_users_qs.exclude(user=vacancy.owner)
    else:
        all_users_qs = VacancyUser.objects.filter(vacancy=vacancy).select_related("user").order_by("-created_at")
        if not request.user.is_staff:
            all_users_qs = all_users_qs.exclude(user=vacancy.owner)

    contact_phones = dict(VacancyContactPhone.objects.filter(vacancy=vacancy).values_list("user_id", "phone"))

    from user.rating import bayesian_rating

    members_list = []
    for vu in all_users_qs:
        likes = UserFeedback.objects.filter(user=vu.user, rating="like").count()
        dislikes = UserFeedback.objects.filter(user=vu.user, rating="dislike").count()
        is_user_blocked = BlockService.is_blocked(vu.user)
        members_list.append(
            {
                "vacancy_user": vu,
                "user": vu.user,
                "status": vu.get_status_display(),
                "is_member": vu.status == "member",
                "is_blocked": is_user_blocked,
                "rating_percent": bayesian_rating(likes, dislikes),
                "contact_phone": contact_phones.get(vu.user_id, ""),
            }
        )

    rollcall_form = None
    if is_rollcall_mode and scenario in ("B", "C", None) and call_type:
        any_records_exist = VacancyUserCall.objects.filter(vacancy_user__in=rollcall_qs, call_type=call_type).exists()
        if call_type == CallType.AFTER_START or not any_records_exist:
            rollcall_form = VacancyCallForm(
                queryset=rollcall_qs, call_type=call_type, initial={"users": list(rollcall_qs)}
            )
        else:
            initial_calls = VacancyUserCall.objects.filter(
                vacancy_user__in=rollcall_qs, status=CallStatus.CONFIRM, call_type=call_type
            )
            rollcall_form = VacancyCallForm(
                queryset=rollcall_qs, call_type=call_type, initial={"users": list(initial_calls)}
            )

    # Attach checkbox HTML to each member for unified rollcall cards
    if rollcall_form and is_rollcall_mode:
        checkbox_map = {}
        for bound_cb in rollcall_form["users"]:
            vu_pk = bound_cb.data["value"]
            checkbox_map[int(str(vu_pk))] = bound_cb.tag()
        for item in members_list:
            vu_pk = item["vacancy_user"].pk
            item["checkbox_tag"] = checkbox_map.get(vu_pk, "")

    return {
        "is_rollcall_mode": is_rollcall_mode,
        "is_start_rollcall": is_start_rollcall,
        "is_end_rollcall": is_end_rollcall,
        "m_call_type": call_type,
        "scenario": scenario,
        "can_search_members": can_search_members,
        "rollcall_form": rollcall_form,
        "members_list": members_list,
        "m_members_count": m_members_count,
        "m_people_count": m_people_count,
        "work_time_started": rollcall_time_reached,
    }


@login_required
def vacancy_detail(request, pk):
    """Detail page for a single vacancy with management buttons and members section."""
    from vacancy.forms import VacancyCallForm

    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)
    is_admin_view = request.user.is_staff and vacancy.owner_id != request.user.id

    # Build members context (rollcall, members list, etc.)
    mc = _build_members_context(vacancy, request)

    # Handle POST for rollcall form
    if request.method == "POST" and mc["is_rollcall_mode"] and mc["m_call_type"]:
        form = VacancyCallForm(request.POST, queryset=vacancy.members, call_type=mc["m_call_type"])
        call_answer = vacancy_check_call(request=request, form=form, vacancy=vacancy, call_type=mc["m_call_type"])
        if call_answer:
            return call_answer
        # Rebuild context after POST processing
        mc = _build_members_context(vacancy, request)

    STATUS_LABELS = {
        STATUS_PENDING: "Очікує модерації",
        STATUS_APPROVED: "Активна",
        STATUS_SEARCH_STOPPED: "Пошук зупинено",
        STATUS_AWAITING_PAYMENT: "Сплатити рахунок",
        STATUS_CLOSED: "Закрита",
        STATUS_PAID: "Сплачено",
    }

    members = vacancy.members.select_related("user")

    can_stop_search = vacancy.search_active and vacancy.status != "pending"
    can_resume_search = (
        vacancy.status == STATUS_SEARCH_STOPPED and not vacancy.first_rollcall_passed and vacancy.status != "pending"
    )
    can_close = (
        vacancy.status not in [STATUS_CLOSED, STATUS_PENDING, STATUS_AWAITING_PAYMENT]
        and vacancy.closed_at is None
        and not mc["is_rollcall_mode"]
    )
    is_closed_lifecycle = vacancy.status == STATUS_CLOSED or vacancy.closed_at is not None
    is_paid = vacancy.extra.get("is_paid", False)
    show_payment = vacancy.second_rollcall_passed and not is_paid and vacancy.status != STATUS_PAID

    # Is the owner currently inside the vacancy's telegram group?
    # Used to hide the 'group invite' button if the owner was kicked.
    owner_in_group = False
    if vacancy.group:
        from telegram.choices import Status as _TgStatus
        from telegram.models import UserInGroup

        owner_in_group = UserInGroup.objects.filter(
            user=vacancy.owner, group=vacancy.group, status=_TgStatus.MEMBER
        ).exists()

    context = {
        "vacancy": vacancy,
        "status_label": STATUS_LABELS.get(vacancy.status, vacancy.get_status_display()),
        "members": members,
        "members_count": members.count(),
        "work_profile": getattr(request.user, "work_profile", None),
        "can_stop_search": can_stop_search,
        "can_resume_search": can_resume_search,
        "can_close": can_close,
        "is_closed_lifecycle": is_closed_lifecycle,
        "is_paid": is_paid,
        "show_payment": show_payment,
        "owner_in_group": owner_in_group,
        "channel_invite_link": vacancy.channel.invite_link if vacancy.channel else None,
        "channel_title": vacancy.channel.title if vacancy.channel else "",
        "is_pending": vacancy.status == "pending",
        "is_admin_view": is_admin_view,
    }
    context.update(mc)

    return render(request, "vacancy/vacancy_detail.html", context)


@login_required
def vacancy_stop_search(request, pk):
    """Stop search: set STATUS_SEARCH_STOPPED, remove button from channel."""
    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    if vacancy.status == STATUS_APPROVED:
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
                ChannelMessage.objects.filter(channel_id=vacancy.channel.id, extra__vacancy_id=vacancy.id)
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

    # 1. Auto-adjust start_time ONLY if work time has already passed.
    #    Before work start: keep original time, just re-publish search.
    #    After work start: original time is in the past, shift to now + 1h.
    now = _tz.localtime(_tz.now())
    start_naive = _dt.combine(vacancy.date, vacancy.start_time)
    start_aware = _tz.make_aware(start_naive, _tz.get_current_timezone())
    work_time_passed = now >= start_aware

    if work_time_passed:
        new_start = now + _td(hours=1)
        # Round to next 15 min
        minute = (new_start.minute // 15 + 1) * 15
        if minute >= 60:
            new_start = (new_start + _td(hours=1)).replace(minute=0, second=0, microsecond=0)
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

    # 3. Re-activate search + reset rollcall flags for new cycle
    from vacancy.choices import STATUS_APPROVED

    vacancy.status = STATUS_APPROVED
    vacancy.search_active = True
    vacancy.search_stopped_at = None
    vacancy.first_rollcall_passed = False
    vacancy.second_rollcall_passed = False

    # Clean rollcall keys from extra so Celery starts fresh
    for key in [
        "sent_start_call",
        "sent_final_call",
        "start_call_sent_at",
        "final_call_sent_at",
        "start_call_reminders",
        "final_call_reminders",
        "start_call_escalated",
        "final_call_escalated",
        "start_call_msg_id",
        "final_call_msg_id",
    ]:
        vacancy.extra.pop(key, None)

    # Delete old rollcall records so new cycle starts clean
    VacancyUserCall.objects.filter(vacancy_user__vacancy=vacancy).delete()

    vacancy.save(
        update_fields=[
            "start_time",
            "end_time",
            "date",
            "status",
            "search_active",
            "search_stopped_at",
            "first_rollcall_passed",
            "second_rollcall_passed",
            "extra",
        ]
    )

    # 4. Republish in channel
    from vacancy.services.observers.events import VACANCY_APPROVED
    from vacancy.services.observers.subscriber_setup import vacancy_publisher as _vp

    _vp.notify(VACANCY_APPROVED, data={"vacancy": vacancy})

    # 5. Send bot message
    try:
        from telegram.handlers.bot_instance import bot

        bot.send_message(chat_id=vacancy.owner.id, text=f"Повторний пошук розпочато. Адреса: {vacancy.address}")
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
            # Scenario B: not enough workers after auto-confirmed rollcall
            if members.count() < vacancy.people_count:
                try:
                    from service.broadcast_service import TelegramBroadcastService
                    from service.notifications_impl import TelegramNotifier
                    from telegram.handlers.bot_instance import bot as _bot_b
                    from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

                    broadcast = TelegramBroadcastService(notifier=TelegramNotifier(_bot_b))
                    broadcast.admin_broadcast(
                        text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_scenario_b(
                            confirmed=members.count(),
                            needed=vacancy.people_count,
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

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
                    vacancy=vacancy, user=request.user, defaults={"phone": _edit_phone}
                )
            print(f"RESUME_SEARCH: saving vacancy pk={vacancy.pk} id={vacancy.id} status={vacancy.status}")
            vacancy.search_stopped_at = None  # reset stop timer
            # New cycle begins: clear pre_call_done, re-anchor original_start_datetime.
            from vacancy.services.call import reset_before_start_cycle as _reset_pre_call_resume

            _reset_pre_call_resume(vacancy)
            from vacancy.services.auto_approve import try_auto_approve

            if try_auto_approve(vacancy):
                vacancy_publisher.notify(events.VACANCY_APPROVED, data={"vacancy": vacancy})
            else:
                vacancy.status = STATUS_PENDING
                vacancy.search_active = False
                vacancy.save()
                vacancy_publisher.notify(events.VACANCY_CREATED, data={"vacancy": vacancy, "request": request})
            return redirect("vacancy:detail", pk=pk)
    else:
        # Use original times if available, otherwise current
        orig_start = vacancy.extra.get("original_start_time")
        orig_end = vacancy.extra.get("original_end_time")
        if orig_start:
            import datetime as _dt

            orig_start = _dt.time(*[int(x) for x in orig_start.split(":")])
        if orig_end:
            import datetime as _dt

            orig_end = _dt.time(*[int(x) for x in orig_end.split(":")])

        initial = {
            "gender": vacancy.gender,
            "people_count": vacancy.people_count,
            "has_passport": vacancy.has_passport,
            "address": vacancy.address,
            "map_link": vacancy.map_link,
            "start_time": orig_start or vacancy.start_time,
            "end_time": orig_end or vacancy.end_time,
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
                ChannelMessage.objects.filter(channel_id=vacancy.channel.id, extra__vacancy_id=vacancy.id)
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

        # Check if rollcall passed and workers exist — force payment instead of close
        members_in_group = list(vacancy.members.values_list("user_id", flat=True))
        if vacancy.first_rollcall_passed and len(members_in_group) > 0:
            # Save workers as after_start call data for invoice calculation
            if "calls" not in vacancy.extra:
                vacancy.extra["calls"] = {}
            vacancy.extra["calls"]["after_start"] = members_in_group
            vacancy.extra["cancel_requested"] = True
            vacancy.status = STATUS_AWAITING_PAYMENT
            vacancy.search_active = False
            vacancy.save(update_fields=["status", "search_active", "extra"])

            # Send invoice and block employer
            try:
                from vacancy.services.invoice import send_vacancy_invoice

                notifier = TelegramNotifier(bot)
                send_vacancy_invoice(notifier=notifier, vacancy=vacancy)
            except Exception as e:
                import logging

                logging.warning(f"Failed to send invoice on close: {e}")

            # Notify admins
            try:
                notifier = TelegramNotifier(bot)
                from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

                broadcast = TelegramBroadcastService(notifier=notifier)
                broadcast.admin_broadcast(
                    text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_employer_closed_invoice(
                        len(members_in_group)
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                import logging

                logging.warning(f"Failed to notify admins on vacancy close: {e}")
        else:
            vacancy.status = STATUS_CLOSED
            vacancy.closed_at = timezone.now()
            vacancy.search_active = False
            vacancy.extra["cancel_requested"] = True
            vacancy.save(update_fields=["status", "closed_at", "search_active", "extra"])

            # Notify admins about manual close
            try:
                notifier = TelegramNotifier(bot)
                from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

                broadcast = TelegramBroadcastService(notifier=notifier)
                broadcast.admin_broadcast(
                    text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_employer_closed_no_workers(),
                    parse_mode="HTML",
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
        or MonobankPayment.objects.filter(vacancy=vacancy, status=MonobankPayment.Status.SUCCESS).exists()
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
    """Redirect to vacancy detail page (members section is now embedded there)."""
    return redirect("vacancy:detail", pk=pk)


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
        return redirect("vacancy:detail", pk=pk)
    return redirect("work:worker_my_work")


@login_required
def vacancy_kick_member(request, pk, user_id):
    """Kick a worker from vacancy group."""
    if request.method != "POST":
        return redirect("vacancy:detail", pk=pk)

    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    from telegram.choices import Status
    from telegram.service.group import GroupService

    if vacancy.group:
        GroupService.kick_user(chat_id=vacancy.group.id, user_id=user_id)

    # Update VacancyUser status so kicked worker can still see vacancy for 1 hour
    from django.utils import timezone as kick_tz

    from vacancy.models import VacancyUser

    VacancyUser.objects.filter(vacancy=vacancy, user_id=user_id).update(status=Status.KICKED, updated_at=kick_tz.now())

    return redirect("vacancy:detail", pk=pk)


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
