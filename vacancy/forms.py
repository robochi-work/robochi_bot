import datetime as d
from datetime import date, timedelta, datetime
from typing import Optional, Literal, Iterable
from django.utils.safestring import mark_safe
from django import forms
from django.contrib.admin.widgets import AdminDateWidget
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.forms import Form
from django.utils.translation import gettext_lazy as _

from telegram.choices import CallType
from telegram.models import Channel
from user.models import User
from work.models import UserWorkProfile
from .choices import (
    DATE_TODAY, DATE_TOMORROW,
    GENDER_CHOICES,
    PAYMENT_UNIT_CHOICES, PAYMENT_SHIFT, PAYMENT_METHOD_CHOICES, GENDER_MALE, PAYMENT_CASH
)
from .models import Vacancy, VacancyUser


class VacancyAdminForm(forms.ModelForm):
    date = forms.DateField(required=False)
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time'}),
        label=_("Start Time")
    )
    end_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time'}),
        label=_("End Time")
    )


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['gender'].initial = 'A'
        self.fields['people_count'].initial = 1
        self.fields['has_passport'].initial = False
        self.fields['address'].initial = "тестовый адрес"
        self.fields['date'].initial = datetime.now().date() + timedelta(days=1)
        self.fields['start_time'].initial = d.time(7, 0)
        self.fields['end_time'].initial = d.time(16, 0)
        self.fields['payment_amount'].initial = 800
        self.fields['date_choice'].initial = 'today'
        self.fields['payment_unit'].initial = 'shift'
        self.fields['payment_method'].initial = 'cash'
        self.fields['skills'].initial = "Ответственность, пунктуальность"

    def clean_people_count(self) -> int:
        value = self.cleaned_data['people_count']
        if not (1 <= value <= 20):
            raise ValidationError(
                _("Number of people must be between 1 and 20."),
                code='invalid'
            )
        return value

    def clean_start_time(self) -> int:
        value = self.cleaned_data['start_time']

        return value

    class Meta:
        model = Vacancy
        fields = '__all__'
        widgets = {
            'date': AdminDateWidget(),
        }


class VacancyForm(forms.Form):
    date_choice = forms.ChoiceField(
        label=_('Preferred Date'),
        widget=forms.RadioSelect(attrs={"class": "date-choice"}),
    )

    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        label=_('Preferred Gender'),
        initial=GENDER_MALE,
    )

    people_count = forms.IntegerField(
        label=_('Number of People'),
        min_value=1,
        max_value=20,
    )
    has_passport = forms.BooleanField(required=False, label=_('Has Passport'))
    address = forms.CharField(
        min_length=4,
        max_length=255,
        label=_('Address')
    )
    map_link = forms.URLField(required=False, label=_('Map Link (is not required)'))
    start_time = forms.TimeField(label=_('Start Time'), widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time = forms.TimeField(label=_('End Time'), widget=forms.TimeInput(attrs={'type': 'time'}))
    payment_amount = forms.DecimalField(max_digits=8, decimal_places=2, label=_('Payment Amount'))
    payment_unit = forms.ChoiceField(
        choices=PAYMENT_UNIT_CHOICES,
        label=_('Payment Type'),
        initial=PAYMENT_SHIFT
    )
    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        label=_('Payment method'),
        initial=PAYMENT_CASH,
    )
    skills = forms.CharField(widget=forms.Textarea(attrs={'rows': 7}), label=_('What will they do'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = date.today()
        tomorrow_str = (today + timedelta(days=1)).strftime('%d.%m.%Y')
        self.fields['date_choice'].choices = [
            (DATE_TODAY, mark_safe(f"<div>{_('Today')}</div> <div>{today.strftime('%d.%m.%Y')}</div>")),
            (DATE_TOMORROW, mark_safe(f"<div>{_('Tomorrow')}</div> <div>{tomorrow_str}</div>")),
        ]
        self.fields['date_choice'].initial = tomorrow_str

    def clean_map_link(self):
        link = self.cleaned_data.get('map_link')
        if link:
            link = link.strip()
            if not link.startswith('https://maps.app'):
                raise forms.ValidationError(
                    _('The map link must start with https://maps.app')
                )
        return link

    def clean_date_choice(self):
        date_choice = self.cleaned_data.get('date_choice')

        try:
            if date_choice == DATE_TODAY:
                self.cleaned_data['date'] = date.today()
            elif date_choice == DATE_TOMORROW:
                self.cleaned_data['date'] = date.today() + timedelta(days=1)
            else:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValidationError(_('Invalid date format'))

        return date_choice

    def save(self, owner: User, status) -> Vacancy:
        data = self.cleaned_data
        work_profile = UserWorkProfile.objects.get(user=owner)

        return Vacancy.objects.create(
            owner=owner,
            status=status,

            date_choice=data.get('date_choice'),
            gender=data.get('gender'),
            people_count=data.get('people_count'),
            has_passport=data.get('has_passport'),
            address=data.get('address'),
            map_link=data.get('map_link'),
            date=data.get('date'),
            start_time=data.get('start_time'),
            end_time=data.get('end_time'),
            payment_amount=data.get('payment_amount'),
            payment_unit=data.get('payment_unit'),
            payment_method=data.get('payment_method'),
            skills=data.get('skills'),
            channel=Channel.objects.get(city=work_profile.city),
        )


CallTypes = Literal['start', 'after_start']
class VacancyCallForm(forms.Form):
    CALL_TYPE_CHOICES = (CallType.START[0], CallType.AFTER_START[0])
    users = forms.ModelMultipleChoiceField(
        queryset=VacancyUser.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Выберите пользователей"
    )
    call_type = forms.CharField(widget=forms.HiddenInput(), required=True)

    def __init__(
            self,
            *args,
            call_type: CallTypes | CallType,
            queryset: Optional[QuerySet[VacancyUser]]=None,
            **kwargs
    ):
        kwargs.setdefault('initial', {})['call_type'] = call_type
        if 'data' in kwargs and isinstance(kwargs['data'], dict):
            data = kwargs['data'].copy()
            if 'call_type' not in data:
                data['call_type'] = call_type
                kwargs['data'] = data

        super().__init__(*args, **kwargs)

        if queryset is not None:
            self.fields['users'].queryset = queryset
            self.fields['users'].label_from_instance = self.user_label_from_instance

    @staticmethod
    def user_label_from_instance(obj: VacancyUser):
        return f"{obj.user.full_name or f'Ім’я не визначене <{obj.user.id}>'} "

class VacancyUserFeedbackForm(forms.Form):
    vacancy = forms.IntegerField(widget=forms.HiddenInput)
    users = forms.ChoiceField(widget=forms.RadioSelect)
    text = forms.CharField(widget=forms.Textarea, required=True)

    def __init__(self, *args, vacancy: Vacancy, users: Iterable[User], **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vacancy"].initial = vacancy.pk
        self.fields["users"].choices = [(u.id, str(u.full_name)) for u in users]
        self.fields["users"].required = True
