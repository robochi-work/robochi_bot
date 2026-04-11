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
                "start_time": last_vacancy.start_time,
                "end_time": last_vacancy.end_time,
                "payment_amount": last_vacancy.payment_amount,
                "payment_unit": last_vacancy.payment_unit,
                "payment_method": last_vacancy.payment_method,
                "skills": last_vacancy.skills,
                "contact_phone": last_vacancy.contact_phone,
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
        elif call_type == CallType.AFTER_START:
            vacancy.second_rollcall_passed = True
            vacancy.save(update_fields=["second_rollcall_passed"])

        if rejected_users > 0:
            if call_type == CallType.START:
                vacancy_publisher.notify(VACANCY_START_CALL_FAIL, data={"vacancy": vacancy})
            elif call_type == CallType.AFTER_START:
                vacancy_publisher.notify(VACANCY_AFTER_START_CALL_FAIL, data={"vacancy": vacancy})
        else:
            if call_type == CallType.AFTER_START:
                vacancy_publisher.notify(VACANCY_AFTER_START_CALL_SUCCESS, data={"vacancy": vacancy})

        return render(request, "vacancy/call_confirm.html", context={"form": form})
    return None


def vacancy_pre_call_check(request: WSGIRequest, pk: int, call_type: CallType):
    vacancy: Vacancy = get_object_or_404(Vacancy, pk=pk)
    users_queryset = vacancy.members
    if call_type == CallType.START:
        vacancy.extra["pre_call_start"] = True
        vacancy.save(update_fields=["extra"])

        if vacancy.extra.get("start_pre_call", "need") in ["need"]:
            can_request_find_users_again = users_queryset.count() < vacancy.people_count

            if can_request_find_users_again:
                return render(
                    request,
                    "vacancy/pre_call.html",
                    context={"pk": pk, "call_type": call_type, "members_count": users_queryset.count()},
                )

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

    return render(request, "vacancy/call.html", context={"form": form, "call_type": call_type})


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
    contact_phone = vacancy.contact_phone or getattr(vacancy.owner, "phone_number", None)

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

    statuses = [STATUS_PENDING, STATUS_APPROVED, STATUS_ACTIVE]
    vacancies = (
        Vacancy.objects.filter(owner=target_user, status__in=statuses)
        .select_related("group", "channel")
        .order_by("-date", "-start_time")
    )

    STATUS_LABELS = {
        STATUS_PENDING: "Очікує модерації",
        STATUS_APPROVED: "Активна (пошук)",
        STATUS_ACTIVE: "Йде зміна",
        "closed": "Завершена",
    }

    vacancy_list = []
    for v in vacancies:
        vacancy_list.append(
            {
                "vacancy": v,
                "status_label": STATUS_LABELS.get(v.status, v.get_status_display()),
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
        STATUS_APPROVED: "Активна (пошук)",
        STATUS_ACTIVE: "Йде зміна",
        STATUS_SEARCH_STOPPED: "Пошук зупинено",
        STATUS_AWAITING_PAYMENT: "Очікує оплати",
        STATUS_CLOSED: "Завершена",
    }

    members = vacancy.members.select_related("user")

    can_stop_search = vacancy.search_active and vacancy.status != "pending"
    can_resume_search = (
        vacancy.status == STATUS_SEARCH_STOPPED and not vacancy.first_rollcall_passed and vacancy.status != "pending"
    )
    can_close = (
        vacancy.status not in [STATUS_CLOSED, STATUS_PENDING, STATUS_AWAITING_PAYMENT] and vacancy.closed_at is None
    )
    show_start_rollcall = not vacancy.first_rollcall_passed and vacancy.status in [
        STATUS_APPROVED,
        STATUS_ACTIVE,
        STATUS_SEARCH_STOPPED,
    ]
    show_end_rollcall = vacancy.first_rollcall_passed and not vacancy.second_rollcall_passed
    rollcall_type = "start" if show_start_rollcall else ("after_start" if show_end_rollcall else None)
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
            "is_admin_view": is_admin_view,
        },
    )


@login_required
def vacancy_stop_search(request, pk):
    """Stop search: set STATUS_SEARCH_STOPPED, remove button from channel."""
    if request.method != "POST":
        return redirect("vacancy:detail", pk=pk)

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
        vacancy.save(update_fields=["status", "search_active", "search_stopped_at"])

    return redirect("vacancy:detail", pk=pk)


@login_required
def vacancy_resume_search(request, pk):
    """Resume search after stop: re-submit vacancy for moderation."""
    if request.user.is_staff:
        vacancy = get_object_or_404(Vacancy, pk=pk)
    else:
        vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)
    work_profile = getattr(request.user, "work_profile", None)

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
            text = VacancyTelegramTextFormatter(vacancy).for_channel(status="closed")
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

        vacancy.closed_at = timezone.now()
        vacancy.search_active = False
        vacancy.save(update_fields=["closed_at", "search_active"])

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

    from user.services import BlockService

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
            }
        )

    return render(
        request,
        "vacancy/vacancy_members.html",
        {
            "vacancy": vacancy,
            "members_list": members_list,
            "work_profile": getattr(request.user, "work_profile", None),
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
    phone = vacancy.contact_phone or getattr(vacancy.owner, "phone_number", None)
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


@login_required
def vacancy_reinvite_worker(request, pk, user_id):
    """Admin reinvites a kicked/blocked worker back to vacancy group."""
    if not request.user.is_staff:
        return redirect("vacancy:detail", pk=pk)

    if request.method != "POST":
        return redirect("vacancy:members", pk=pk)

    import logging

    from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

    from telegram.handlers.bot_instance import get_bot
    from user.models import User
    from user.services import BlockService

    vacancy = get_object_or_404(Vacancy, pk=pk)
    target_user = get_object_or_404(User, pk=user_id)

    # Remove active block if present
    active_block = BlockService.get_active_block(target_user)
    if active_block:
        BlockService.unblock_user(active_block.pk)

    # Send invite via bot
    try:
        bot = get_bot()
        invite_link = vacancy.group.invite_link if vacancy.group else None
        if invite_link:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("Приєднатися до групи", url=invite_link))
            bot.send_message(
                target_user.id,
                f"Адміністратор запрошує вас повернутися до вакансії: {vacancy.address}.\nНатисніть кнопку щоб приєднатися.",
                reply_markup=markup,
            )
    except Exception:
        import sentry_sdk

        sentry_sdk.capture_exception()

    logger = logging.getLogger(__name__)
    logger.info(
        "worker_reinvited",
        extra={
            "admin_id": request.user.id,
            "worker_id": target_user.id,
            "vacancy_id": vacancy.id,
        },
    )

    return redirect("vacancy:members", pk=pk)
