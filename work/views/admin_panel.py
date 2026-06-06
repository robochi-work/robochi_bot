import logging

import sentry_sdk
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from city.models import City
from user.models import User
from vacancy.choices import (
    STATUS_APPROVED,
    STATUS_AWAITING_PAYMENT,
    STATUS_CLOSED,
    STATUS_PENDING,
    STATUS_SEARCH_STOPPED,
)
from vacancy.forms import VacancyForm
from vacancy.models import Vacancy
from vacancy.services.observers.events import VACANCY_APPROVED as VACANCY_APPROVED_EVENT
from vacancy.services.observers.subscriber_setup import vacancy_publisher
from work.choices import WorkProfileRole

logger = logging.getLogger(__name__)


def staff_required(view_func):
    """Decorator: login_required + is_staff check."""

    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise Http404
        return view_func(request, *args, **kwargs)

    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


@staff_required
def admin_dashboard(request):
    """Main admin dashboard page with filter tabs."""
    cities = City.objects.all()
    return render(
        request,
        "work/admin_dashboard.html",
        {
            "cities": cities,
            "roles": WorkProfileRole.choices,
            "work_profile": getattr(request.user, "work_profile", None),
        },
    )


@staff_required
def admin_search_users(request):
    """Search users by filters from tab."""
    qs = User.objects.select_related("work_profile", "work_profile__city").all()

    q = request.GET.get("q", "").strip()
    if q:
        filters = Q(full_name__icontains=q) | Q(username__icontains=q) | Q(phone_number__icontains=q)
        if q.isdigit():
            filters |= Q(id=int(q))
        qs = qs.filter(filters)

    city_ids = request.GET.getlist("city")
    if city_ids:
        qs = qs.filter(work_profile__city_id__in=city_ids)

    roles = request.GET.getlist("role")
    if roles:
        qs = qs.filter(work_profile__role__in=roles)

    if request.GET.get("blocked"):
        qs = qs.filter(blocks__is_active=True).distinct()
    qs = qs.order_by("-date_joined")[:100]

    from user.models import UserBlock

    users_list = list(qs)
    for u in users_list:
        block = UserBlock.objects.filter(user=u, is_active=True).order_by("-created_at").first()
        u.active_block_id = block.pk if block else None
        u.active_block_type = block.block_type if block else None

    response = render(
        request,
        "work/admin_search_results.html",
        {
            "users": users_list,
            "search_type": "users",
            "work_profile": getattr(request.user, "work_profile", None),
        },
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@staff_required
def admin_search_vacancies(request):
    """Search employers by vacancy filters."""
    qs = User.objects.select_related("work_profile", "work_profile__city").filter(
        work_profile__role=WorkProfileRole.EMPLOYER
    )

    city_ids = request.GET.getlist("city")
    if city_ids:
        qs = qs.filter(work_profile__city_id__in=city_ids)

    status_filters = Q()
    has_status_filter = False

    if request.GET.get("pending"):
        status_filters |= Q(vacancies__status=STATUS_PENDING)
        has_status_filter = True

    if request.GET.get("in_work"):
        status_filters |= Q(vacancies__status=STATUS_APPROVED)
        has_status_filter = True

    if request.GET.get("to_pay"):
        status_filters |= Q(
            vacancies__status__in=[STATUS_AWAITING_PAYMENT, STATUS_CLOSED],
            vacancies__extra__sent_final_call=True,
            vacancies__extra__is_paid=False,
        )
        has_status_filter = True

    if request.GET.get("cancelled"):
        from datetime import timedelta

        from django.utils import timezone as _tz

        threshold_3h = _tz.now() - timedelta(hours=3)
        status_filters |= Q(vacancies__status=STATUS_SEARCH_STOPPED) | Q(
            vacancies__status=STATUS_CLOSED, vacancies__closed_at__gte=threshold_3h
        )
        has_status_filter = True

    if request.GET.get("paid"):
        status_filters |= Q(vacancies__status=STATUS_CLOSED, vacancies__extra__is_paid=True)
        has_status_filter = True

    if has_status_filter:
        qs = qs.filter(status_filters).distinct()

    qs = qs.order_by("-date_joined")[:100]

    from user.models import UserBlock

    users_list = list(qs)
    for u in users_list:
        block = UserBlock.objects.filter(user=u, is_active=True).order_by("-created_at").first()
        u.active_block_id = block.pk if block else None
        u.active_block_type = block.block_type if block else None

    response = render(
        request,
        "work/admin_search_results.html",
        {
            "users": users_list,
            "search_type": "vacancies",
            "work_profile": getattr(request.user, "work_profile", None),
        },
    )
    return response


@staff_required
def admin_vacancy_card(request, user_id):
    """Vacancy card page for a specific employer."""
    from user.services import BlockService

    target_user = get_object_or_404(User, pk=user_id)
    profile = getattr(target_user, "work_profile", None)

    vacancies = (
        Vacancy.objects.filter(owner=target_user, status__in=[STATUS_PENDING, STATUS_APPROVED])
        .select_related("group", "channel", "channel__city")
        .order_by("-date", "-start_time")
    )

    cities_vacancies = {}
    for v in vacancies:
        city_name = "Bez mista"
        if v.channel and v.channel.city:
            city_name = v.channel.city.safe_translation_getter("name", any_language=True)
        cities_vacancies.setdefault(city_name, []).append(v)

    return render(
        request,
        "work/admin_vacancy_card.html",
        {
            "target_user": target_user,
            "target_profile": profile,
            "cities_vacancies": cities_vacancies,
            "active_block": BlockService.get_active_block(target_user),
            "work_profile": getattr(request.user, "work_profile", None),
        },
    )


@staff_required
def admin_moderate_vacancy(request, vacancy_id):
    """Moderation form for a single vacancy."""
    vacancy = get_object_or_404(Vacancy, pk=vacancy_id)
    work_profile = getattr(request.user, "work_profile", None)

    if request.method == "POST" and vacancy.status != STATUS_PENDING:
        return redirect("work:admin_dashboard")

    if request.method == "POST":
        owner_profile = getattr(vacancy.owner, "work_profile", None)
        form = VacancyForm(request.POST, work_profile=owner_profile, resume_mode=True)
        if form.is_valid():
            try:
                data = form.cleaned_data
                vacancy.gender = data["gender"]
                vacancy.people_count = data["people_count"]
                vacancy.has_passport = data["has_passport"]
                vacancy.address = data["address"]
                vacancy.map_link = data.get("map_link", vacancy.map_link)
                vacancy.date_choice = data["date_choice"]
                vacancy.date = data.get("date", vacancy.date)
                vacancy.start_time = data["start_time"]
                vacancy.end_time = data["end_time"]
                vacancy.payment_amount = data["payment_amount"]
                vacancy.payment_unit = data["payment_unit"]
                vacancy.payment_method = data["payment_method"]
                vacancy.skills = data["skills"]
                vacancy.contact_phone = data.get("contact_phone", "")
                # Update channel based on selected city
                selected_city = data.get("city")
                if selected_city:
                    from telegram.models import Channel

                    try:
                        vacancy.channel = Channel.objects.get(city=selected_city)
                    except Channel.DoesNotExist:
                        form.add_error(None, f"Канал для міста {selected_city} не знайдено.")
                        return render(
                            request,
                            "work/admin_moderate_vacancy.html",
                            {
                                "form": form,
                                "vacancy": vacancy,
                                "target_user": vacancy.owner,
                                "work_profile": work_profile,
                            },
                        )
                # Assign group from pool (same logic as Django Admin save_model)
                if not vacancy.group:
                    from telegram.choices import STATUS_PROCESS
                    from telegram.service.group import GroupService

                    group = GroupService.get_available_group()
                    if group:
                        vacancy.group = group
                        group.status = STATUS_PROCESS
                        group.save(update_fields=["status"])
                    else:
                        form.add_error(None, "Немає вільних груп для вакансії. Спробуйте пізніше.")
                        return render(
                            request,
                            "work/admin_moderate_vacancy.html",
                            {
                                "form": form,
                                "vacancy": vacancy,
                                "target_user": vacancy.owner,
                                "work_profile": work_profile,
                            },
                        )

                vacancy.status = STATUS_APPROVED
                vacancy.save()
                # New cycle: admin moderation may have changed start_time; re-anchor.
                from vacancy.services.call import reset_before_start_cycle as _reset_pre_call_adm

                _reset_pre_call_adm(vacancy)
                logger.info("moderation_approved", extra={"admin_id": request.user.id, "vacancy_id": vacancy.id})
                # Delete admin moderation messages from bot
                admin_msgs = vacancy.extra.get("admin_moderation_messages", {}) if vacancy.extra else {}
                if admin_msgs:
                    from telegram.handlers.bot_instance import get_bot

                    bot = get_bot()
                    for admin_chat_id, msg_id in admin_msgs.items():
                        try:
                            bot.delete_message(int(admin_chat_id), msg_id)
                        except Exception:
                            logger.debug("Could not delete moderation msg for admin %s", admin_chat_id)
                    vacancy.extra.pop("admin_moderation_messages", None)
                    vacancy.save(update_fields=["extra"])
                vacancy_publisher.notify(VACANCY_APPROVED_EVENT, {"vacancy": vacancy, "request": request})
                return redirect("work:admin_dashboard")
            except Exception as e:
                form.add_error(None, str(e))
    else:
        initial = {
            "city": vacancy.channel.city_id if vacancy.channel else None,
            "date_choice": vacancy.date_choice,
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
        owner_profile = getattr(vacancy.owner, "work_profile", None)
        form = VacancyForm(initial=initial, work_profile=owner_profile)

    return render(
        request,
        "work/admin_moderate_vacancy.html",
        {
            "form": form,
            "vacancy": vacancy,
            "target_user": vacancy.owner,
            "work_profile": work_profile,
        },
    )


@staff_required
@require_POST
def admin_close_vacancy(request, vacancy_id):
    """Force-close a vacancy and release its group."""
    from vacancy.services.observers.events import VACANCY_CLOSE
    from vacancy.services.observers.subscriber_setup import vacancy_publisher

    vacancy = get_object_or_404(Vacancy, pk=vacancy_id)
    if vacancy.status != STATUS_CLOSED:
        vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
    elif vacancy.group:
        # Already closed but group stuck — release it
        from telegram.choices import STATUS_AVAILABLE as GROUP_AVAILABLE

        vacancy.group.status = GROUP_AVAILABLE
        vacancy.group.save(update_fields=["status"])
        vacancy.group = None
        vacancy.save(update_fields=["group"])

    referer = request.headers.get("referer", "")
    if referer:
        return redirect(referer)
    return redirect("work:admin_vacancy_card", user_id=vacancy.owner_id)


@staff_required
@require_POST
def admin_delete_vacancy(request, vacancy_id):
    """Delete vacancy completely (same as Django admin delete)."""
    vacancy = get_object_or_404(Vacancy, pk=vacancy_id)

    vacancy_id_log = vacancy.id

    # Release group back to pool if assigned
    if vacancy.group:
        from telegram.choices import STATUS_FREE

        group = vacancy.group
        group.status = STATUS_FREE
        group.save(update_fields=["status"])

    # Delete admin moderation messages from bot
    admin_msgs = vacancy.extra.get("admin_moderation_messages", {}) if vacancy.extra else {}
    if admin_msgs:
        from telegram.handlers.bot_instance import get_bot

        bot = get_bot()
        for admin_chat_id, msg_id in admin_msgs.items():
            try:
                bot.delete_message(int(admin_chat_id), msg_id)
            except Exception:
                logger.debug("Could not delete moderation msg for admin %s", admin_chat_id)

    vacancy.delete()
    logger.info("moderation_deleted", extra={"admin_id": request.user.id, "vacancy_id": vacancy_id_log})
    return redirect("work:admin_dashboard")


@staff_required
def admin_block_user(request, user_id):
    """Block/unblock a user."""
    logger.warning(f"BLOCK VIEW HIT: user_id={user_id} method={request.method} POST={dict(request.POST)}")
    from datetime import timedelta

    from django.utils import timezone

    from user.services import BlockService

    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "block":
            block_type = request.POST.get("block_type", "temporary")
            reason = request.POST.get("reason", "manual")
            comment = request.POST.get("comment", "")
            duration_days = request.POST.get("duration_days")

            blocked_until = None
            if block_type == "temporary" and duration_days:
                blocked_until = timezone.now() + timedelta(days=int(duration_days))

            BlockService.block_user(
                user=target_user,
                block_type=block_type,
                reason=reason,
                blocked_by=request.user,
                blocked_until=blocked_until,
                comment=comment,
            )
            logger.info(
                "user_blocked",
                extra={
                    "admin_id": request.user.id,
                    "target_user_id": target_user.id,
                    "block_type": block_type,
                    "reason": reason,
                },
            )

            try:
                from telegram.handlers.bot_instance import get_bot

                if block_type == "permanent":
                    text = "Вас заблоковано у сервісі robochi.work !\nДля розблокування зверніться до Адміністратора- @robochi_work_admin"
                else:
                    text = "Увага! Вас обмежено у користуванні сервісом robochi.work !\nДля розблокування зверніться до Адміністратора- @robochi_work_admin"
                get_bot().send_message(target_user.id, text)
            except Exception:
                sentry_sdk.capture_exception()

            if block_type == "permanent":
                try:
                    from telegram.handlers.bot_instance import get_bot
                    from telegram.models import Channel, Group

                    _bot = get_bot()
                    profile = getattr(target_user, "work_profile", None)

                    # Кикаем из всех групп где состоит
                    active_groups = Group.objects.filter(useringroup__user=target_user).distinct()
                    for group in active_groups:
                        try:
                            _bot.ban_chat_member(group.id, target_user.id)
                            _bot.unban_chat_member(group.id, target_user.id)
                        except Exception:
                            sentry_sdk.capture_exception()

                    # Кикаем из каналов города без бана
                    if profile and profile.city:
                        channels = Channel.objects.filter(city=profile.city)
                        for channel in channels:
                            try:
                                _bot.ban_chat_member(channel.id, target_user.id)
                                _bot.unban_chat_member(channel.id, target_user.id)
                            except Exception:
                                sentry_sdk.capture_exception()
                except Exception:
                    sentry_sdk.capture_exception()

        elif action == "unblock":
            from user.models import UserBlock
            from user.services import admin_mark_vacancies_paid

            had_unpaid_block = UserBlock.objects.filter(user=target_user, is_active=True, reason="unpaid").exists()

            BlockService.unblock_user_all(target_user)
            logger.info("user_unblocked", extra={"admin_id": request.user.id, "target_user_id": target_user.id})

            if had_unpaid_block:
                paid = admin_mark_vacancies_paid(user=target_user, admin_user=request.user)
                logger.info("unblock_marked_paid", extra={"count": paid, "user_id": target_user.id})

            try:
                from telegram.handlers.bot_instance import get_bot

                get_bot().send_message(target_user.id, "Вас розблоковано. Ви знову можете користуватися сервісом.")
            except Exception:
                sentry_sdk.capture_exception()

    from django.http import HttpResponseRedirect

    referer = request.headers.get("referer", "")
    logger.warning(f"BLOCK REDIRECT: referer={referer}")
    if referer and "/block/" not in referer:
        return HttpResponseRedirect(referer)
    return redirect("work:admin_dashboard")


@staff_required
def admin_moderate_rollcall(request, vacancy_id, call_type):
    """Stage 4: admin form for finalizing a disputed 2nd rollcall.

    The admin can ADD checkboxes (over the employer's last selection).
    Unchecking is allowed only when the original dispute was full-uncheck
    (Scenario В) — otherwise the admin can only widen the confirmed set.

    Submitting calls finalize_rollcall(...) and clears the disputed state.
    """
    from telegram.choices import CallType as _CallType
    from vacancy.forms import VacancyCallForm
    from vacancy.models import Vacancy
    from vacancy.services.disputed_rollcall import (
        disable_admin_buttons,
        finalize_rollcall,
        get_disputed,
        is_disputed,
    )
    from vacancy.services.rollcall_snapshot import get_snapshot_vacancy_users

    vacancy = get_object_or_404(Vacancy, pk=vacancy_id)

    # Normalize call_type
    try:
        ct = _CallType(call_type)
    except ValueError:
        return redirect("work:admin_dashboard")
    if ct != _CallType.AFTER_START:
        return redirect("work:admin_dashboard")

    if not is_disputed(vacancy):
        # Already resolved (employer self-submitted or another admin acted)
        return redirect("work:admin_dashboard")

    state = get_disputed(vacancy)
    is_full_uncheck = bool(state.get("is_full_uncheck"))
    prev_selected_ids = set(state.get("selected_ids") or [])

    rollcall_qs = get_snapshot_vacancy_users(vacancy)

    if request.method == "POST":
        form = VacancyCallForm(request.POST, queryset=rollcall_qs, call_type=ct)
        if form.is_valid():
            selected = list(form.cleaned_data.get("users", []))
            new_ids = {vu.user_id for vu in selected}

            # Admin can only ADD checkboxes — unless Scenario В (full uncheck) allows zero/edit
            if not is_full_uncheck:
                removed = prev_selected_ids - new_ids
                if removed:
                    form.add_error(
                        "users",
                        "Адміністратор може лише додавати чекбокси, не знімати.",
                    )
                    return render(
                        request,
                        "work/admin_moderate_rollcall.html",
                        {"form": form, "vacancy": vacancy, "is_full_uncheck": is_full_uncheck},
                    )

            disable_admin_buttons(vacancy)
            finalize_rollcall(vacancy, final_selected_user_ids=list(new_ids), finalized_by="admin")
            return redirect("work:admin_dashboard")
    else:
        # Pre-fill with employer's last selection
        initial_qs = rollcall_qs.filter(user_id__in=prev_selected_ids)
        form = VacancyCallForm(queryset=rollcall_qs, call_type=ct, initial={"users": list(initial_qs)})

    return render(
        request,
        "work/admin_moderate_rollcall.html",
        {
            "form": form,
            "vacancy": vacancy,
            "rollcall_qs": rollcall_qs,
            "is_full_uncheck": is_full_uncheck,
            "prev_count": state.get("first_count", 0),
            "prev_selected": state.get("second_count", 0),
        },
    )
