from typing import Iterable

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _, gettext

import vacancy
from telegram.choices import STATUS_PROCESS
from telegram.models import Channel, Payment
from vacancy.models import Vacancy, VacancyStatusHistory, VacancyUser, VacancyUserCall
from work.models import UserWorkProfile
from .choices import STATUS_APPROVED, STATUS_CHOICES, STATUS_PENDING
from .forms import VacancyAdminForm
from telegram.service.group import GroupService
from .services.invoice import send_vacancy_invoice
from .services.observers.approved_channel_observer import VacancyApprovedChannelObserver
from .services.observers.call_observer import VacancyBeforeCallObserver, VacancyStartCallObserver, \
    VacancyAfterStartCallObserver
from .services.observers.created_admin_observer import VacancyCreatedAdminObserver
from .services.observers.created_user_observer import VacancyCreatedUserObserver
from .services.observers.events import VACANCY_CREATED, VACANCY_APPROVED, VACANCY_BEFORE_CALL, VACANCY_START_CALL, \
    VACANCY_AFTER_START_CALL, VACANCY_DELETE, VACANCY_CLOSE, VACANCY_CLOSE_FORCIBLY
from .services.observers.member_observer import VacancyIsFullObserver
from .services.observers.subscriber_setup import telegram_notifier, vacancy_publisher
from .services.vacancy_status import update_vacancy_status
from .tasks.call import before_start_call, after_first_call_check, start_call_check, final_call_check, close_vacancy, \
    close_vacancy_task


class VacancyStatusHistoryInline(admin.TabularInline):
    model = VacancyStatusHistory
    extra = 0
    readonly_fields = ('changed_at', 'new_status', 'changed_by', 'comment')
    can_delete = False

class PaymentInline(admin.TabularInline):
    model = Payment
    fk_name = 'vacancy'
    fields = ('date', 'total_amount_display', 'currency', 'status')
    readonly_fields = fields
    extra = 0
    can_delete = False
    verbose_name = _('Payment')
    verbose_name_plural = _('Payments')

    @admin.display(description=_('Сумма'))
    def total_amount_display(self, obj):
        try:
            amount = obj.total_amount / 100
            return f"{amount:.2f}"
        except Exception:
            return '-'

class StatusDefaultFilter(admin.SimpleListFilter):
    title = _('Status')
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        qs = model_admin.get_queryset(request)
        total = qs.count()
        choices = [(
            'all',
            _('{label} ({count})').format(label=_('All'), count=total)
        )]
        # По каждому статусу
        for value, label in Vacancy._meta.get_field('status').choices:
            count = qs.filter(status=value).count()
            choices.append((
                value,
                _('{label} ({count})').format(label=label, count=count)
            ))
        return choices

    def queryset(self, request, queryset):
        val = self.value()
        if val is None or val == '':
            return queryset.filter(status='active')
        if val == 'all':
            return queryset
        return queryset.filter(status=val)

    def choices(self, changelist):
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == smart_str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }

@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ('owner', 'people_count', )
    form = VacancyAdminForm
    inlines = [PaymentInline, VacancyStatusHistoryInline]
    actions = [
        'notify_owner', 'notify_admins', 'send_to_channels', 'update_channel_message',
        'before_start_call_action','start_call_action', 'final_call_action', 'after_first_call_check_action',
        'send_start_call','send_final_call', 'close_vacancy_action', 'close_vacancy_forcibly_action', 'send_vacancy_invoice_action',
        'set_default_owner_group_permissions',
    ]

    list_filter = (StatusDefaultFilter,)

    def changelist_view(self, request, extra_context=None):
        if 'status' not in request.GET and 'status' not in request.POST:
            q = request.GET.copy()
            q['status'] = 'active'
            request.GET = q
            request.META['QUERY_STRING'] = request.GET.urlencode()
        return super().changelist_view(request, extra_context=extra_context)

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (_('Vacancy Info'), {
                'fields': ('owner', 'gender', 'people_count', 'has_passport')
            }),
            (_('Location and Time'), {
                'fields': ['address', 'date_choice', 'date', 'start_time', 'end_time']
            }),
            (_('Payment and Skills'), {
                'fields': ('payment_amount', 'payment_unit', 'payment_method', 'skills')
            }),
            (_('Status'), {
                'fields': ('channel', 'group', 'status',)
            }),
        ]

        if obj:
            for name, section in fieldsets:
                if 'address' in section['fields']:
                    idx = section['fields'].index('address')
                    section['fields'].insert(idx + 1, 'map_link')

        return fieldsets

    def save_model(self, request, obj: Vacancy, form, change):
        status_changed = 'status' in form.changed_data
        work_profile = UserWorkProfile.objects.get(user=obj.owner)
        obj.channel = Channel.objects.get(city=work_profile.city)

        if status_changed and obj.status == STATUS_APPROVED:
            if not obj.group:
                group = GroupService.get_available_group()
                if group:
                    obj.group = group
                    group.status = STATUS_PROCESS
                    group.save(update_fields=['status'])
                else:
                    obj.status = form.initial.get('status', STATUS_PENDING)
                    self.message_user(
                        request,
                        _("Status was not updated to ‘%(status)s’: no available group. Other changes were saved.") % {
                            'status': _("Approved")
                        },
                        level=messages.ERROR
                    )

        super().save_model(request, obj, form, change)
        update_vacancy_status(obj, new_status=obj.status, old_status=form.initial.get('status'), changed_by=request.user)


    def response_change(self, request, obj):
        if not getattr(self, '_should_save', True):
            opts = self.model._meta
            change_url = reverse(
                f'admin:{opts.app_label}_{opts.model_name}_change',
                args=[obj.pk]
            )
            return HttpResponseRedirect(change_url)
        return super().response_change(request, obj)

    @admin.action(description=_('Send notification about create the vacancy to owner'))
    def notify_owner(self, request, queryset):
        for vacancy in queryset:
            VacancyCreatedUserObserver(telegram_notifier).update(VACANCY_CREATED, data={'vacancy':vacancy,})
        self.message_user(
            request,
            gettext('Notification sent to owner(s).'),
            messages.SUCCESS
        )

    @admin.action(description=_('Update message in channel - vacancy is full'))
    def update_channel_message(self, request, queryset):
        for vacancy in queryset:
            VacancyIsFullObserver(telegram_notifier).update('test_event', data={'vacancy':vacancy,})
        self.message_user(
            request,
            gettext('Updated.'),
            messages.SUCCESS
        )

    @admin.action(description=_('Send notification about creation to admins'))
    def notify_admins(self, request, queryset):
        for vacancy in queryset:
            VacancyCreatedAdminObserver(telegram_notifier).update(VACANCY_CREATED, data={'vacancy':vacancy,})
        self.message_user(
            request,
            gettext('Notification sent to admin(s).'),
            messages.SUCCESS
        )
    @admin.action(description=_('Before start call to owner'))
    def before_start_call_action(self, request, queryset: Iterable[Vacancy]):
        before_start_call(queryset)
        self.message_user(
            request,
            gettext('call.'),
            messages.SUCCESS
        )
    @admin.action(description=_('start call to owner'))
    def start_call_action(self, request, queryset: Iterable[Vacancy]):
        for vacancy in queryset:
            VacancyStartCallObserver(notifier=telegram_notifier).update(VACANCY_START_CALL, data={'vacancy':vacancy,})
        self.message_user(
            request,
            gettext('call.'),
            messages.SUCCESS
        )

    @admin.action(description=_('final call for owner'))
    def final_call_action(self, request, queryset: Iterable[Vacancy]):
        for vacancy in queryset:
            VacancyAfterStartCallObserver(notifier=telegram_notifier).update(VACANCY_AFTER_START_CALL, data={'vacancy':vacancy,})
        self.message_user(
            request,
            gettext('call.'),
            messages.SUCCESS
        )

    @admin.action(description=_('After first call check'))
    def after_first_call_check_action(self, request, queryset):
        after_first_call_check(queryset)
        self.message_user(
            request,
            gettext('call.'),
            messages.SUCCESS
        )

    @admin.action(description=_('Send vacancies to channel (if not closed)'))
    def send_to_channels(self, request, queryset):
        for vacancy in queryset:
            if vacancy.group:
                if vacancy.group.invite_link:
                    VacancyApprovedChannelObserver(telegram_notifier).update(VACANCY_APPROVED, data={'vacancy':vacancy,})
                else:
                    self.message_user(
                        request,
                        gettext('The vacancy group does not have a invite link'),
                        messages.ERROR
                    )
            else:
                self.message_user(
                    request,
                    gettext('The vacancy does not have a group'),
                    messages.ERROR
                )
        self.message_user(
            request,
            gettext('Vacancies sent to channel(s).'),
            messages.SUCCESS
        )

    @admin.action(description=_('Check calls before start (20 min after first call)'))
    def check_before_20_start(self, request, queryset):
        for vacancy in queryset:
            VacancyBeforeCallObserver().check_before_20_start(vacancy=vacancy)

        self.message_user(
            request,
            gettext('Vacancies sent check to members.'),
            messages.SUCCESS
        )
    @admin.action(description=_('Send start call for owner (if dont sent in)'))
    def send_start_call(self, request, queryset):
        start_call_check(queryset)

        self.message_user(
            request,
            gettext('sent.'),
            messages.SUCCESS
        )
    @admin.action(description=_('Send final call for owner (if dont sent in)'))
    def send_final_call(self, request, queryset):
        final_call_check(queryset)

        self.message_user(
            request,
            gettext('sent.'),
            messages.SUCCESS
        )

    @admin.action(description=_('Close vacancies check'))
    def close_vacancy_action(self, request, queryset):
        for vacancy in queryset:
            close_vacancy(vacancy=vacancy)

        self.message_user(
            request,
            gettext('sent.'),
            messages.SUCCESS
        )

    @admin.action(description=_('Close vacancies forcibly'))
    def close_vacancy_forcibly_action(self, request, queryset):
        for vacancy in queryset:
            vacancy_publisher.notify(VACANCY_CLOSE, data={'vacancy': vacancy})
            vacancy_publisher.notify(VACANCY_CLOSE_FORCIBLY, data={'vacancy': vacancy})

        self.message_user(
            request,
            gettext('sent.'),
            messages.SUCCESS
        )

    @admin.action(description=_('Send vacancy invoice'))
    def send_vacancy_invoice_action(self, request, queryset: QuerySet[Vacancy]):

        for vacancy in queryset:
            send_vacancy_invoice(notifier=telegram_notifier, vacancy=vacancy)

        self.message_user(
            request,
            gettext('sent.'),
            messages.SUCCESS
        )
    @admin.action(description=_('Set default owner group permissions'))
    def set_default_owner_group_permissions(self, request, queryset: QuerySet[Vacancy]):

        for vacancy in queryset:
            if vacancy.group:
                GroupService.set_default_owner_permissions(
                    chat_id=vacancy.group.id,
                    user_id=vacancy.owner.id,
                )
                GroupService.set_admin_custom_title(
                    chat_id=vacancy.group.id,
                    user_id=vacancy.owner.id,
                    custom_title="роботодавець",
                )

        self.message_user(
            request,
            gettext('sent.'),
            messages.SUCCESS
        )


@admin.register(VacancyUser)
class VacancyUserAdmin(admin.ModelAdmin):
    list_display = ('vacancy', 'user', )
    list_filter = ('vacancy', 'status')

@admin.register(VacancyUserCall)
class VacancyUserCallAdmin(admin.ModelAdmin):
    list_display = ('vacancy_user', 'status', 'call_type', 'created_at',)
